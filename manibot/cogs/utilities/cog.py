import asyncio

import discord

from manibot import checks, command, group, utils

def bitround(x):
    return max(min(1 << int(x).bit_length() - 1, 1024), 16)

class Utilities:
    """Utility Tools"""

    def __init__(self, bot):
        self.bot = bot

    @command(name='say')
    @checks.is_mod()
    async def _say(self, ctx, *, msg):
        """Repeat the given message."""
        await ctx.send(msg)

    @group(name='embed', invoke_without_command=True)
    @checks.is_mod()
    async def _embed(self, ctx, title=None, content=None, colour=None,
                     icon_url=None, image=None, thumbnail=None,
                     plain_msg=''):
        """Create an embed from scratch"""
        await ctx.embed(title=title, description=content, colour=colour,
                        icon=icon_url, image=image, thumbnail=thumbnail,
                        plain_msg=plain_msg)

    @_embed.command(name='error')
    @checks.is_mod()
    async def _error(self, ctx, title, content=None, log_level=None):
        """Create a basic error embed"""
        await ctx.error(title, content, log_level)

    @_embed.command(name='info')
    @checks.is_mod()
    async def _info(self, ctx, title, content=None):
        """Create a basic info embed"""
        await ctx.info(title, content)

    @_embed.command(name='warning')
    @checks.is_mod()
    async def _warning(self, ctx, title, content=None):
        """Create a basic warning embed"""
        await ctx.warning(title, content)

    @_embed.command(name='success')
    @checks.is_mod()
    async def _success(self, ctx, title, content=None):
        """Create a basic success embed"""
        await ctx.success(title, content)

    @_embed.command(name='help')
    @checks.is_mod()
    async def _help(self, ctx, title, content=None):
        """Create a basic help embed"""
        embed = utils.make_embed(title=title, content=content, msg_type='help')
        await ctx.send(embed=embed)

    @command()
    @checks.is_mod()
    async def cleanup(self, ctx, after_msg_id: int, channel_id: int = None):
        after_msg = await ctx.get.message(after_msg_id)
        channel = ctx.channel
        if channel_id:
            channel = ctx.get.channel(channel_id)
        def is_eevee(msg):
            return msg.author == ctx.bot.user
        try:
            deleted = await channel.purge(
                after=after_msg, check=is_eevee, bulk=True)
        except discord.Forbidden:
            deleted = await channel.purge(
                after=after_msg, check=is_eevee, bulk=False)

        plural = "s" if len(deleted) > 1 else ""
        msg = await ctx.success(f'Deleted {len(deleted)} message{plural}')

        await asyncio.sleep(3)
        try:
            await msg.delete()
        except discord.Forbidden:
            pass

    @command(aliases=['avatar'])
    async def avy(self, ctx, member: discord.Member = None, size: bitround = 1024):
        member = member or ctx.author
        avy_url = member.avatar_url_as(size=size, static_format='png')
        try:
            colour = await utils.user_color(member)
        except OSError:
            colour = ctx.me.colour
        await ctx.embed(
            f"{member.display_name}'s Avatar",
            title_url=avy_url,
            image=avy_url,
            colour=colour)

    @command()
    @checks.is_admin()
    async def purge(self, ctx, msg_number: int = 10):
        """Delete a number of messages from the channel.

        Default is 10. Max 100."""
        if msg_number > 100:
            await ctx.error(
                'No more than 100 messages can be purged at a time.')
            return
        deleted = await ctx.channel.purge(limit=msg_number)
        result_msg = await ctx.success('Deleted {} message{}'.format(
            len(deleted), "s" if len(deleted) > 1 else ""))
        await asyncio.sleep(3)
        await result_msg.delete()

    @command()
    @checks.is_admin()
    async def delete_msg(self, ctx, *message_ids: int):
        for msg_id in message_ids:
            msg = await ctx.get.message(id=msg_id)
            if not msg:
                return
            await msg.delete()
        await asyncio.sleep(5)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @command(aliases=['priv', 'privs'])
    async def privilege(self, ctx, member: discord.Member = None):
        if member:
            if not await checks.check_is_mod(ctx):
                return await ctx.error(
                    "Only mods can check other member's privilege level.")
        member = member or ctx.author
        ctx.author = member
        if not await checks.check_is_mod(ctx):
            return await ctx.info('Normal User')
        if not await checks.check_is_admin(ctx):
            return await ctx.info('Mod')
        if not await checks.check_is_guildowner(ctx):
            return await ctx.info('Admin')
        if not await checks.check_is_co_owner(ctx):
            return await ctx.info('Guild Owner')
        if not await checks.check_is_owner(ctx):
            return await ctx.info('Bot Co-Owner')
        return await ctx.info('Bot Owner')
