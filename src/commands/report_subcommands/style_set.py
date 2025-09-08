# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from typing import Any
import discord
from discord import app_commands
from discord.app_commands import Choice
from ..framework import CommandDefinition


class ReportStyleSet(CommandDefinition):
    group_name = None

    def define(self, group: app_commands.Group, ctx: dict[str, Any]) -> None:
        storage = ctx["storage"]
        style_group = app_commands.Group(name="style", description="Report style commands", parent=group)

        @style_group.command(name="set", description="Set weekly report style")
        @app_commands.describe(style="Report style theme")
        @app_commands.choices(
            style=[
                Choice(name="style1", value="style1"),
                Choice(name="style2", value="style2"),
                Choice(name="style3", value="style3"),
                Choice(name="style4", value="style4"),
            ]
        )
        async def _cmd(interaction: discord.Interaction, style: str):
            valid_styles = {"style1", "style2", "style3", "style4"}
            if style not in valid_styles:
                await interaction.response.send_message(
                    f"Invalid style. Choose one of: {', '.join(sorted(valid_styles))}.", ephemeral=True
                )
                return
            if not interaction.guild_id:
                await interaction.response.send_message("This command must be used in a guild.", ephemeral=True)
                return
            storage.set_guild_report_style(interaction.guild_id, style)
            await interaction.response.send_message(f"Report style set to {style}.", ephemeral=True)
