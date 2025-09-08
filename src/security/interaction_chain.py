# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
"""Chainable interaction helper for Discord UI components.

Provides a tiny builder for creating a one-shot interaction message with either
an action button or a select. When the user interacts, the provided callback is
invoked and the controls are removed (or disabled) from the message so it can't
be used again.

This mirrors the scheduler flow style, but keeps it generic and chainable to
reuse across commands.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, List, Optional
import uuid

import discord

from .interaction import safe_send, safe_defer


InteractionCallback = Callable[[discord.Interaction, Any], Awaitable[None]]


@dataclass(slots=True)
class _StepConfig:
    kind: str  # "button" | "select"
    label: str | None = None
    options: List[discord.SelectOption] | None = None
    placeholder: str | None = None
    style: discord.ButtonStyle = discord.ButtonStyle.primary
    callback: Optional[InteractionCallback] = None


class _OneShotView(discord.ui.View):
    """Internal View that hosts a single interactive component.

    Disables itself after the first successful invocation.
    """

    def __init__(self, *, step: _StepConfig, restrict_user_id: int | None, remove_on_use: bool, one_shot: bool, timeout: float | None):
        super().__init__(timeout=timeout)
        self._step = step
        self._restrict_user_id = restrict_user_id
        self._remove_on_use = remove_on_use
        self._one_shot = one_shot
        self._used = False

        if step.kind == "button":
            assert step.label, "Button requires label"
            # Stable custom id mainly for diagnostics; discord requires it to identify components.
            custom_id = f"chain_btn_{uuid.uuid4().hex}"
            button = discord.ui.Button(label=step.label, style=step.style, custom_id=custom_id)

            async def _on_click(interaction: discord.Interaction):  # type: ignore[no-redef]
                await self._handle_invoke(interaction, None)

            button.callback = _on_click  # type: ignore[method-assign]
            self.add_item(button)  # type: ignore[arg-type]

        elif step.kind == "select":
            assert step.options, "Select requires options"
            select = discord.ui.Select(
                min_values=1,
                max_values=1,
                options=step.options,
                custom_id=f"chain_sel_{uuid.uuid4().hex}",
                placeholder=step.placeholder or "Select an option",
            )

            async def _on_select(interaction: discord.Interaction):  # type: ignore[no-redef]
                value = select.values[0] if select.values else None
                await self._handle_invoke(interaction, value)

            select.callback = _on_select  # type: ignore[method-assign]
            self.add_item(select)  # type: ignore[arg-type]
        else:
            raise ValueError(f"Unsupported step kind: {step.kind}")

    async def _handle_invoke(self, interaction: discord.Interaction, value: Any) -> None:
        if self._used:
            # Ignore duplicate clicks/selects once used.
            return
        if self._restrict_user_id is not None and getattr(getattr(interaction, "user", None), "id", None) != self._restrict_user_id:
            await safe_send(interaction, "You're not allowed to use this control.")
            return

        if not self._one_shot:
            # Multi-use: just acknowledge without changing components and call the callback.
            await safe_defer(interaction, ephemeral=True, thinking=False)
            if self._step.callback is not None:
                await self._step.callback(interaction, value)
            return

        # Mark used first to avoid races in one-shot mode.
        self._used = True

        # Acknowledge by editing the message (disable/remove controls), then call the callback.
        try:
            if self._remove_on_use:
                await interaction.response.edit_message(view=None)
            else:
                for item in self.children:
                    try:
                        item.disabled = True  # type: ignore[attr-defined]
                    except Exception:
                        pass
                await interaction.response.edit_message(view=self)
        except Exception:
            pass

        # If for any reason the interaction wasn't acknowledged yet, ensure we defer
        # so the subsequent callback can safely send a followup.
        try:
            if not interaction.response.is_done():
                await safe_defer(interaction, ephemeral=True, thinking=False)
        except Exception:
            pass

        if self._step.callback is not None:
            await self._step.callback(interaction, value)


class ChainInteraction:
    """Chainable builder for one-shot interaction messages.

    Typical usage:
        builder = ChainInteraction(description="Click to confirm").with_button("Confirm").on_invoke(async_fn)
        await builder.send(interaction)
    """

    def __init__(self, description: str):
        self._description = description
        self._step: _StepConfig | None = None
        self._restrict_user_id: int | None = None
        self._one_shot = True  # one-shot behavior is always on; default disables controls
        self._remove_on_use = False  # by default, do not remove; disable instead
        self._timeout: float | None = 180.0

    def restrict_to_user(self, user_id: int) -> "ChainInteraction":
        """Restrict interactions to a specific user id."""
        self._restrict_user_id = int(user_id)
        return self

    def with_button(self, label: str, *, style: discord.ButtonStyle = discord.ButtonStyle.primary) -> "ChainInteraction":
        """Use a single button as the control."""
        self._step = _StepConfig(kind="button", label=label, style=style)
        return self

    def with_select(self, options: Iterable[str] | Iterable[discord.SelectOption], *, placeholder: str | None = None) -> "ChainInteraction":
        """Use a single-select dropdown as the control.

        Args:
            options: Either strings (become label=value) or prebuilt SelectOption.
            placeholder: Optional placeholder text shown before selection.
        """
        norm: list[discord.SelectOption] = []
        for o in options:
            if isinstance(o, discord.SelectOption):
                norm.append(o)
            else:
                s = str(o)
                norm.append(discord.SelectOption(label=s, value=s))
        self._step = _StepConfig(kind="select", options=norm, placeholder=placeholder)
        return self

    def on_invoke(self, callback: InteractionCallback) -> "ChainInteraction":
        """Assign the callback to invoke when the control is used."""
        if not self._step:
            raise RuntimeError("Define a control (with_button/with_select) before on_invoke().")
        self._step.callback = callback
        return self

    def one_shot(self, enabled: bool = True) -> "ChainInteraction":
        """Whether to perform one-shot behavior after first use (default True).

        One-shot means the controls become unusable after the first interaction.
        By default, the controls are disabled (not removed). Use remove_on_use()
        to remove the controls entirely instead.
        """
        self._one_shot = bool(enabled)
        return self

    def remove_on_use(self, enabled: bool = True) -> "ChainInteraction":
        """Configure one-shot to remove controls entirely after use (default False)."""
        self._remove_on_use = bool(enabled)
        return self

    def timeout(self, seconds: float | None) -> "ChainInteraction":
        """Set view timeout (auto-disposes). None disables timeout."""
        self._timeout = seconds
        return self

    def build_view(self) -> discord.ui.View:
        """Build and return the underlying discord View for advanced usage."""
        if not self._step:
            raise RuntimeError("No control configured.")
        return _OneShotView(
            step=self._step,
            restrict_user_id=self._restrict_user_id,
            remove_on_use=self._remove_on_use,
            one_shot=self._one_shot,
            timeout=self._timeout,
        )

    async def send(self, interaction: discord.Interaction, *, ephemeral: bool = True) -> None:
        """Send the chainable interaction message to Discord.

        Args:
            interaction: The Discord interaction to respond to.
            ephemeral: Whether the message should be ephemeral (default True).
        """
        view = self.build_view()
        # Be robust to already-acknowledged interactions.
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(self._description, view=view, ephemeral=ephemeral)
            else:
                await interaction.followup.send(self._description, view=view, ephemeral=ephemeral)
        except Exception:
            # Fallback: try followup one more time without raising upstream.
            try:
                await interaction.followup.send(self._description, view=view, ephemeral=ephemeral)
            except Exception:
                # Final fallback: send text-only message so user still sees a response
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(self._description, ephemeral=ephemeral)
                    else:
                        await interaction.followup.send(self._description, ephemeral=ephemeral)
                except Exception:
                    pass


def Chain(description: str) -> ChainInteraction:
    """Convenience factory.

    Returns:
        ChainInteraction: Builder to configure and send a one-shot interaction.
    """
    return ChainInteraction(description)


# Pythonic alias
def chain(description: str) -> ChainInteraction:
    return ChainInteraction(description)
