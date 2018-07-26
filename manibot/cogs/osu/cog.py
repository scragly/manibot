import discord

from manibot import group, Cog
from manibot.utils import snowflake

OSUSIG = (
    "https://lemmmy.pw/osusig/sig.php?colour=hex214ed8&uname={}&pp=1&xpbar")

OSUICON = "https://s.ppy.sh/apple-touch-icon.png"

class Osu(Cog):
    """Osu Utilities"""

    async def db_osuname(self, member_id, username=None, delete=False):
        table = self.bot.dbi.table('osu_members')
        if delete:
            await table.query.delete(member_id=member_id)
            return
        if username:
            insert = table.insert(member_id=member_id, osu_username=username)
            await insert.commit(do_update=True)
            return
        query = table.query.where(member_id=member_id)
        return await query.get_value('osu_username')

    @group(invoke_without_command=True)
    async def osu(self, ctx, *, member: discord.Member = None):
        member = member or ctx.author
        osu_username = await self.db_osuname(member.id)
        if not osu_username:
            return await ctx.error(
                "You don't have a linked osu account.",
                f"Set one with `{ctx.prefix}osu set <username>`")
        await ctx.embed(
            f"Osu! Profile for {member.display_name}",
            icon=OSUICON,
            image=(
                f"{OSUSIG.format(osu_username)}"
                f"&nocache={next(snowflake.create())}"))

    @osu.command(name='user')
    async def user(self, ctx, *, username):
        await ctx.embed(
            "Osu! Profile",
            icon=OSUICON,
            image=(
                f"{OSUSIG.format(username)}"
                f"&nocache={next(snowflake.create())}"))

    @osu.command(name='set')
    async def _set(self, ctx, *, username):
        await self.db_osuname(ctx.author.id, username)
        await ctx.success(
            f"The osu account {username} is now linked to you.")

    @osu.command()
    async def clear(self, ctx):
        await self.db_osuname(ctx.author.id, delete=True)
        await ctx.success(f"You are no longer linked to an osu account.")
