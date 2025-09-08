from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.security.interaction_chain import Chain, chain


class _Resp:
    def __init__(self) -> None:
        self._done = False
        self.last_sent: dict[str, Any] | None = None
        self.last_edit: dict[str, Any] | None = None

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, content: str, *, view: Any | None = None, ephemeral: bool = True) -> None:  # type: ignore[override]
        self._done = True
        self.last_sent = {"content": content, "view": view, "ephemeral": ephemeral}

    async def edit_message(self, *, view: Any | None = None) -> None:  # type: ignore[override]
        self.last_edit = {"view": view}


class _Followup:
    def __init__(self) -> None:
        self.last_sent: dict[str, Any] | None = None

    async def send(self, content: str, *, view: Any | None = None, ephemeral: bool = True) -> None:  # type: ignore[override]
        self.last_sent = {"content": content, "view": view, "ephemeral": ephemeral}


class _User:
    def __init__(self, uid: int) -> None:
        self.id = uid


class _Interaction:
    def __init__(self, user_id: int = 1) -> None:
        self.user = _User(user_id)
        self.response = _Resp()
        self.followup = _Followup()

    async def edit_original_response(self, *, view: Any | None = None) -> None:  # type: ignore[override]
        # Mirror response.edit_message for tests.
        await self.response.edit_message(view=view)


@pytest.mark.asyncio
async def test_chain_button_one_shot_invokes_and_clears() -> None:
    called: list[Any] = []

    async def on_click(interaction, value):  # type: ignore[no-untyped-def]
        called.append(value)

    builder = Chain("Press the button").with_button("Go").on_invoke(on_click)
    view = builder.build_view()

    # View should contain a button with an async callback we can call
    assert view.children, "No components rendered"
    button = view.children[0]

    i = _Interaction(user_id=1)
    # Simulate clicking
    await button.callback(i)

    # Callback captured
    assert called == [None]
    # One-shot default: controls disabled (not removed)
    assert i.response.last_edit is not None
    # We expect the edited view object to be present (disabled components)
    assert i.response.last_edit.get("view") is not None

    # Second click should be ignored (no duplicate appends)
    await button.callback(i)
    assert called == [None]


@pytest.mark.asyncio
async def test_chain_select_invokes_with_value() -> None:
    seen: list[Any] = []

    async def on_pick(interaction, value):  # type: ignore[no-untyped-def]
        seen.append(value)

    builder = chain("Choose one").with_select(["A", "B"]).on_invoke(on_pick)
    view = builder.build_view()
    select = view.children[0]

    # Fake selection value as discord would set it
    select.values = ["B"]
    i = _Interaction(user_id=42)
    await select.callback(i)

    assert seen == ["B"]
    assert i.response.last_edit is not None
    assert i.response.last_edit.get("view") is not None


@pytest.mark.asyncio
async def test_chain_restrict_blocks_other_user() -> None:
    invoked = False

    async def cb(interaction, value):  # type: ignore[no-untyped-def]
        nonlocal invoked
        invoked = True

    builder = Chain("Only user 7").restrict_to_user(7).with_button("OK").on_invoke(cb)
    view = builder.build_view()
    button = view.children[0]

    # User 8 should be blocked
    i = _Interaction(user_id=8)
    await button.callback(i)
    assert invoked is False


@pytest.mark.asyncio
async def test_chain_remove_on_use_removes_controls() -> None:
    done = []

    async def cb(i, _):  # type: ignore[no-untyped-def]
        done.append(True)

    builder = Chain("Remove on use").with_button("OK").remove_on_use(True).on_invoke(cb)
    view = builder.build_view()
    button = view.children[0]
    i = _Interaction(user_id=1)
    await button.callback(i)

    assert done == [True]
    assert i.response.last_edit is not None
    assert i.response.last_edit.get("view") is None
