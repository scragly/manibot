import logging
import asyncio
import urllib
import datetime
import html
import feedparser
import aiohttp
import discord
from discord import Webhook, AsyncWebhookAdapter, Embed
from manibot import command, group, Cog, checks

HATIGARMRSS = "https://www.hatigarmscans.net/feed"

logger = logging.getLogger('manibot.rss')

class RSS(Cog):
    def __init__(self, bot):
        self.test_webhook_url = (
            'https://discordapp.com/api/webhooks/465376012297961492/'
            'mTV37gjkuZ1C8kbLGVfMJkvs694TuIInB3gSIEZkyutL5IaJ'
            '_JV6xoDoKfxiAQkhUcic')
        self.do_update = True
        self.data = None
        self.last_item_id = None
        self.update_task = None
        self.avatar = 'https://i.imgur.com/HZ27mE7.png'
        self.start_updates()

    def __unload(self):
        self.stop_updates()

    def stop_updates(self):
        if not self.update_task:
            return False
        self.update_task.cancel()
        self.update_task = None
        return True

    def start_updates(self):
        if self.update_task:
            return False
        self.update_task = self.bot.loop.create_task(self.update_data())
        return True

    async def update_data(self):
        while True:
            await asyncio.sleep(30)
            rawdata = await self.get_feed()
            if not rawdata:
                logger.warning('No data received from RSS Feed')
            else:
                self.data = feedparser.parse(rawdata)
                if not self.last_item_id:
                    self.last_item_id = await self.get_last_item()
                if self.is_updated:
                    await self.update_feed_db()
                    await self.send_to_webhooks()

            await asyncio.sleep(30)
            continue

    async def get_feed(self):
        try:
            async with self.bot.session.get(HATIGARMRSS) as r:
                if r.status == 200:
                    return await r.text()
                logger.error(f'Feed Connect Error: Status: {r.status}')
            return None
        except aiohttp.ClientConnectorError as e:
            logger.error(f'Feed Connector Error: Exception: {e}')
            return None

    async def get_last_item(self):
        query = self.feed_table.query.order_by('updated', asc=False).limit(1)
        last_item = await query.get_value('item_id')
        self.last_item_id = last_item
        return last_item

    async def update_feed_db(self):
        feed_insert = self.feed_table.insert
        last_item = self.last_item_id
        for item in self.data.entries:
            if item.id == last_item:
                break
            timestamp = datetime.datetime.strptime(
                item.updated.rsplit('+', 1)[0], "%Y-%m-%dT%H:%M:%S")
            feed_insert(
                item_id=item.id, title=item.title, link=item.link,
                updated=timestamp, author=item.author,
                summary=str(item.summary), content=str(item.content)
            )
        await feed_insert.commit(do_update=False)
        await self.get_last_item()

    async def send_to_webhooks(self):
        embeds = self.build_embeds(self.new_items)
        msgs = self.split_list(embeds, 10)
        for wh_data in await self.all_webhooks():
            webhook = wh_data['webhook']
            role = wh_data['sub_role_id']
            avatar = wh_data['avatar'] or self.avatar
            delay = wh_data['avatar'] or 0
            self.bot.loop.create_task(
                self.notify(webhook, role, avatar, delay, msgs))

    async def all_webhooks(self):
        query = self.settings_table.query
        records = await query.get()
        data = []
        for record in records:
            rcrd_data = dict(record)
            rcrd_data['webhook'] = Webhook.from_url(
                rcrd_data['webhook_url'],
                adapter=AsyncWebhookAdapter(self.bot.session))
            data.append(rcrd_data)
        return data

    async def notify(self, webhook, role, avatar, delay, messages):
        await asyncio.sleep(delay)
        for embeds in messages:
            if embeds == messages[0]:
                ping = f'<@&{role}>' if role else None
            else:
                ping = None
            await webhook.send(
                ping, embeds=embeds, username='New Update!', avatar_url=avatar)
            await asyncio.sleep(0.5)

    @property
    def is_updated(self):
        return self.data.entries[0].id != self.last_item_id

    @property
    def feed_table(self):
        return self.bot.dbi.table('feed_data')

    @property
    def settings_table(self):
        return self.bot.dbi.table('feed_settings')

    async def settings(self, guild_id, *fields):
        query = self.settings_table.query.where(guild_id=guild_id)
        if not fields:
            return await query.get_one()
        else:
            return await query.get_value(*fields)

    def get_poster_url(self, item_url):
        split = urllib.parse.urlsplit(item_url)
        join = 'http://hatigarmscans.net/uploads' + split.path
        imgurl = join.rsplit('/', 1)[0] + '/cover/cover_250x350.jpg'
        return imgurl

    @staticmethod
    def split_list(l, n):
        data = []
        for i in range(0, len(l), n):
            data.append(l[i:i + n])
        return data

    @property
    def new_items(self):
        new_items = []
        for item in self.data.entries:
            if item.id == self.last_item_id:
                break
            new_items.append(item)
        return reversed(new_items)

    def build_embeds(self, items):
        embeds = []
        for item in items:
            embed_data = self.build_embed(item.title, item.id, item.updated, item.summary)
            embeds.append(Embed.from_data(embed_data))
        return embeds

    @staticmethod
    def html_text(text):
        return html.unescape(html.unescape(text))

    def build_embed(self, name, page_url, timestamp, summary):
        if isinstance(timestamp, datetime.datetime):
            timestamp = timestamp.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            timestamp = timestamp.split('+')[0]
        poster_url = self.get_poster_url(page_url)
        data = {
            "color"      : 2272250,
            "timestamp"  : timestamp,
            "footer"     :{
                "text"   : "Updated"
            },
            "thumbnail"  :{
                "url"    : poster_url
            },
            "author"     :{
                "name"   : self.html_text(name),
                "url"    : page_url
            }
        }
        if not summary:
            summary = '\u200b'
        else:
            summary = f"*{summary}*\n"
        data['description'] = f'{summary}\n\U0001f4d6 [Read it at Hatigarm Scans!]({page_url})'
        return data

    @group(name='rss', invoke_without_command=True)
    async def _rss(self, ctx):
        async with ctx.typing():
            data = await self.get_feed()
            if not data:
                return await ctx.error('RSS Feed is down.')
            await ctx.success('RSS Feed is up.')

    @_rss.command()
    @checks.is_admin()
    async def test(self, ctx, ping: bool = False, number=1):
        data = feedparser.parse(HATIGARMRSS)
        items = data.entries[0:number]
        embeds = self.build_embeds(reversed(items))
        msgs = self.split_list(embeds, 10)
        settings = await self.settings(ctx.guild.id)
        wh_url = settings['webhook_url']
        role_id = settings['sub_role_id'] if ping else None
        avatar = settings['avatar'] or self.avatar
        delay = settings['delay'] or 0
        if not wh_url:
            return await ctx.error('Webhook not registered for this guild')
        webhook = Webhook.from_url(
            wh_url, adapter=AsyncWebhookAdapter(self.bot.session))
        await self.notify(webhook, role_id, avatar, delay, msgs)

    @_rss.command()
    @checks.is_mod()
    async def setdelay(self, ctx, seconds_delay: int):
        """Sets the guilds rss webhook notification delay in seconds."""
        insert = self.settings_table.insert(
            guild_id=ctx.guild.id, delay=seconds_delay)
        await insert.commit(do_update=True)
        await ctx.ok()

    @_rss.command()
    @checks.is_co_owner()
    async def stop(self, ctx):
        """Stop the background update task loop."""
        status = self.stop_updates()
        if status:
            await ctx.ok()
        else:
            await ctx.error('There is no update task to stop.')

    @_rss.command()
    @checks.is_co_owner()
    async def start(self, ctx):
        """Start the background update task loop."""
        status = self.start_updates()
        if status:
            await ctx.ok()
        else:
            await ctx.warning('The update task was already running.')

    @_rss.command()
    @checks.is_mod()
    async def setavatar(self, ctx, avatar_url = None):
        """Sets the guilds rss webhook avatar."""
        if avatar_url.startswith('<') and avatar_url.endswith('>'):
            avatar_url = avatar_url.lstrip('<')
            avatar_url = avatar_url.rstrip('>')
        insert = self.settings_table.insert(
            guild_id=ctx.guild.id, avatar=avatar_url)
        await insert.commit(do_update=True)
        await ctx.ok()

    @_rss.command()
    @checks.is_mod()
    async def setrole(self, ctx, role: discord.Role = None):
        """Sets the guilds rss webhook notification role."""
        if not role:
            role_id = None
        else:
            role_id = role.id
        insert = self.settings_table.insert(
            guild_id=ctx.guild.id, sub_role_id=role_id)
        await insert.commit(do_update=True)
        await ctx.ok()

    @_rss.command()
    @checks.is_mod()
    async def register(self, ctx, webhook_url):
        """Register the guild rss webhook."""
        insert = self.settings_table.insert(
            guild_id=ctx.guild.id, webhook_url=webhook_url)
        await insert.commit(do_update=True)
        await ctx.ok()

    @command(aliases=['sub'])
    async def subscribe(self, ctx, member: discord.Member = None):
        """Add the subscriber role to be notified when there's updates."""
        if member:
            if not await checks.check_is_mod(ctx):
                return await ctx.error('Only mods can subscribe others.')
        member = member or ctx.author
        role_id = await self.settings(ctx.guild.id, 'sub_role_id')
        if not role_id:
            return await ctx.error(
                "A notification role hasn't been setup yet.")
        role = ctx.get.role(role_id)
        await member.add_roles(role)
        await ctx.ok()

    @command(aliases=['unsub'])
    async def unsubscribe(self, ctx, member: discord.Member = None):
        """Remove the subscriber role to stop update notifications."""
        if member:
            if not await checks.check_is_mod(ctx):
                return await ctx.error('Only mods can unsubscribe others.')
        member = member or ctx.author
        role_id = await self.settings(ctx.guild.id, 'sub_role_id')
        if not role_id:
            return await ctx.error(
                "A notification role hasn't been setup yet.")
        role = ctx.get.role(role_id)
        await member.remove_roles(role)
        await ctx.ok()

    @command()
    @checks.is_admin()
    async def taskstatus(self, ctx):
        """Check on the status of the feed update background task."""
        if not self.update_task:
            return await ctx.codeblock('No Running Update Task')
        msg = asyncio.coroutines._format_coroutine(self.update_task._coro)
        if self.update_task._state == 'FINISHED':
            if self.update_task._exception is not None:
                msg += '\n\nException:\n{!r}'.format(
                    self.update_task._exception)
        await ctx.codeblock(msg)

    @command()
    async def latest(self, ctx, title):
        """Search for the latest release of the entered series."""
        table = self.feed_table
        table.query.where(table['title'].ilike(f'%{title}%'))
        table.query.order_by('updated', asc=False)
        result = await table.query.get_first()
        # name, page_url, timestamp, summary
        if not result:
            return await ctx.error("Sorry, I couldn't find a match.")
        embed_data = self.build_embed(
            result['title'], result['item_id'], result['updated'], result['summary'])
        embed = discord.Embed.from_data(embed_data)
        await ctx.send(embed=embed)
