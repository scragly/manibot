import io
from datetime import datetime
import typing
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import discord

from manibot import checks, command
from manibot.utils.converters import Guild

DAILYMSGSQL = """
SELECT sent
FROM discord_messages
WHERE guild_id = $1 AND is_edit = FALSE AND author_id = $2
ORDER BY sent DESC
"""

class Statistics:
    """Statistics Tools"""
    def __init__(self, bot):
        self.bot = bot

    @command()
    @checks.is_co_owner()
    async def msgcount(self, ctx, member: typing.Union[discord.Member, Guild] = None):
        guild = None
        if isinstance(member, discord.Guild):
            if await checks.check_is_owner(ctx):
                guild = member
                member = ctx.author
            else:
                member = None

        guild = guild or ctx.guild
        member = member or ctx.author
        query = ctx.bot.dbi.table('discord_messages').query('sent')
        query.where(guild_id=guild.id, is_edit=False, author_id=member.id)
        query.order_by('sent', asc=False)
        data = await query.get_values()

        # results = await ctx.bot.dbi.execute_query(
        #     DAILYMSGSQL, ctx.guild.id, member.id)
        if not data:
            return await ctx.error(
                f"I haven't seen {member.display_name} before.")

        dates = mdates.epoch2num(data)

        fig, ax = plt.subplots(linewidth=0, sharey=True, tight_layout=True)
        fig.set_size_inches(8, 4)
        ax.tick_params(labelsize=12, color='lightgrey', labelcolor='lightgrey')

        # ax.bar(x, y, color='r', width=1.0, linewidth=0, tick_label=labels)

        locator = mdates.AutoDateLocator()
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))

        counts, bins, patches = ax.hist(dates, 10, facecolor='red', alpha=0.75)
        ax.set_xticks(bins)

        plot_bytes = io.BytesIO()
        fig.savefig(
            plot_bytes,
            format='png',
            facecolor='#32363C',
            transparent=True)
        plot_bytes.seek(0)
        fig.clf()

        fname = f"msgcount-{member.id}.png"
        plot_file = discord.File(plot_bytes, filename=fname)

        embed = await ctx.embed(
            f"Message Stats - {member.display_name} in {guild.name}", send=False)
        embed.set_image(url=f"attachment://{fname}")
        await ctx.send(file=plot_file, embed=embed)
