# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from typing import Any, Callable, Dict
import discord
from discord import app_commands
from ..framework import CommandDefinition


class DebugGenerateUser(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        generate_random_user_recent: Callable[..., Dict[str, Any]] = ctx["generate_random_user_recent"]

        @group.command(name="generate_user", description="Generate clustered test user messages for this channel")
        async def _cmd(
            interaction: discord.Interaction,
            user_id: str | None = None,
            messages: int = 5,
            dry_run: bool = True,
        ):
            try:
                await interaction.response.defer(ephemeral=True, thinking=True)
                cid = interaction.channel_id
                if cid is None:
                    await interaction.followup.send("This command must be used in a channel.", ephemeral=True)
                    return
                messages = max(1, min(200, int(messages)))
                result = generate_random_user_recent(
                    channel_discord_id=cid,
                    user_id=user_id,
                    messages=messages,
                    dry_run=dry_run,
                )
                written = result.get("written", False)
                sample_dates = sorted({m["extracted_date"] for m in result["messages"]})
                body = (
                    f"Generated {len(result['messages'])} messages for user {result['user_id']}.\n"
                    f"Dates: {', '.join(sample_dates[:10])}{'...' if len(sample_dates) > 10 else ''}\n"
                    f"Written to DB: {written} (dry_run={dry_run})"
                )
                await interaction.followup.send(body, ephemeral=True)
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Error generating user: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Error generating user: {e}", ephemeral=True)
