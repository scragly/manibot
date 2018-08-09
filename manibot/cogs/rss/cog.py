import asyncio
import datetime
import logging
import urllib
import traceback

import aiohttp
import bs4
import feedparser

import discord
from discord import AsyncWebhookAdapter, Embed, Webhook

from manibot import Cog, checks, command, group
from manibot.utils.formatters import unescape_html
from manibot.utils.datatypes import Map

HATIGARMRSS = "https://www.hatigarmscans.net/feed"

logger = logging.getLogger('manibot.rss')

def get_poster_url(item_url):
    split = urllib.parse.urlsplit(item_url)
    join = 'http://hatigarmscans.net/uploads' + split.path
    imgurl = join.rsplit('/', 1)[0] + '/cover/cover_250x350.jpg'
    return imgurl


class RSSEntry:

    __slots__ = ('bot', 'dbi', 'data', 'title', 'link', 'author',
                 'summary', 'content', 'item_id', 'updated')

    def __init__(self, bot, data):
        self.bot = bot
        self.dbi = bot.dbi
        self.data = data
        self.title = data.title
        self.link = data.link
        self.author = data.author
        self.summary = data.summary
        self.content = str(data.content)

        # db data won't have it under id, but item_id
        if not data.id:
            self.item_id = data.item_id
        else:
            self.item_id = data.id

        # db data is already datetime object
        if isinstance(data.updated, str):
            self.updated = datetime.datetime.strptime(
                data.updated.rsplit('+', 1)[0], "%Y-%m-%dT%H:%M:%S")
        else:
            self.updated = data.updated

    @property
    def data_table(self):
        return self.dbi.table('feed_data')

    @property
    def query(self):
        return self.data_table.query.where(item_id=self.item_id)

    async def exists(self):
        value = await self.query.get_value('item_id')
        return bool(value)

    async def get(self):
        return await self.query.get()

    async def insert(self):
        insert = self.data_table.insert(
            item_id=self.item_id, title=self.title, link=self.link,
            updated=self.updated, author=self.author, summary=self.summary,
            content=self.content)
        await insert.commit()

    async def series_title(self):
        series_title = self.title.rsplit('#', 1)[0].strip()
        return (await self.bot.series.match_series(series_title))[0]

    @property
    def chapter(self):
        try:
            chapter = self.title.rsplit('#', 1)[1].strip()
        except IndexError:
            split = urllib.parse.urlsplit(self.item_id)
            chapter = split.path.rsplit('/', 1)[-1]
        return chapter

    async def update_series(self):
        try:
            # get series title
            series_title = await self.series_title()
            if not series_title:
                return

            # make this entry latest details for series
            await self.bot.series.edit_by_title(
                series_title,
                latest_chapter=self.chapter,
                updated=self.updated)

        except Exception as e:
            logger.error(f'Exception {type(e)}: {e}')

    async def first_page(self):
        try:
            async with self.bot.session.get(self.item_id) as r:
                if r.status != 200:
                    return False
                content = await r.text()
                soup = bs4.BeautifulSoup(content, 'html.parser')
                allimgs = soup.find("div", {"id": "all"})
                if not allimgs:
                    return False
                firstimg = allimgs.find("img")
                if not firstimg:
                    return False
                return firstimg['data-src']
        except aiohttp.ClientError as e:
            logger.error(
                f"Error Getting First Page "
                f"({type(e)}) - Exception: {e}")
            return None

    @property
    def poster_url(self):
        split = urllib.parse.urlsplit(self.item_id)
        join = 'http://hatigarmscans.net/uploads' + split.path
        imgurl = join.rsplit('/', 1)[0] + '/cover/cover_250x350.jpg'
        return imgurl

    @property
    def embed_data(self):
        poster = self.poster_url

        data = {
            "color"      : 2272250,
            "timestamp"  : self.updated.strftime("%Y-%m-%dT%H:%M:%S"),
            "footer"     :{
                "text"   : "Updated"
            },
            "thumbnail"  :{
                "url"    : poster
            },
            "author"     :{
                "name"   : unescape_html(self.title),
                "url"    : self.item_id
            }
        }

        if not self.summary:
            summary = '\u200b'

        else:
            summary = f"*{unescape_html(self.summary)}*\n"
        data['description'] = (f"{summary}\n\U0001f4d6 "
                               f"[Read it at Hatigarm Scans!]({self.item_id})")
        return data

    @property
    def embed(self):
        return Embed.from_data(self.embed_data)

    async def get_role(self, guild_id):
        series_title = await self.series_title()
        if series_title:
            return await self.bot.series.get_series_role(
                guild_id, series_title)
        return None

    async def get_mention(self, guild_id):
        role = await self.get_role(guild_id)
        return role.mention if role else f"@{self.series_title} (New?)"

    async def send_to_webhook(self, webhook, do_ping=True):
        if do_ping:
            pings = await self.get_mention(webhook.guild_id)
            if webhook.sub_role_id:
                pings = f"<@&{webhook.sub_role_id}> {pings}"
        else:
            pings = ""

        await self.wait_until_published()

        logger.info(f"Pushing Update - {self.item_id}")
        await webhook.webhook.send(
            pings, embed=self.embed, avatar_url=webhook.avatar)

    async def send_to_channel(self, channel):
        await channel.send(embed=self.embed)

    async def wait_until_published(self):
        logger.info(f"Check Published - {self.item_id}")
        while True:
            page = await self.get_first_page()
            if page:
                logger.info(f'Published: {page}')
                return
            logger.info(
                f"Check Published FAIL (retry in 30s) - {self.item_id}")
            await asyncio.sleep(30)
            continue

    async def get_first_page(self):
        try:
            async with self.bot.session.get(self.item_id) as r:
                if r.status != 200:
                    return False
                content = await r.text()
                soup = bs4.BeautifulSoup(content, 'html.parser')
                allimgs = soup.find("div", {"id": "all"})
                if not allimgs:
                    return False
                firstimg = allimgs.find("img")
                if not firstimg:
                    return False
                return firstimg['data-src']
        except aiohttp.ClientError as e:
            logger.error(f'{type(e)} - Exception: {e}')
            return None


class RSS(Cog):
    def __init__(self, bot):
        self.bot = bot
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

    async def on_message(self, message):
        if message.channel.id not in [328244845795737602, 444394290987270157, 465501965153992704]:
            return
        if message.content not in ['#iAm Notifbud', '##iAm Notifbud']:
            return
        await message.channel.send("Try `!sub`")

    def stop_updates(self):
        if not self.update_task:
            logger.info(f'Feed Monitor Task Not Running')
            return False
        self.update_task.cancel()
        self.update_task = None
        logger.info(f'Feed Monitor Task Stopped')
        return True

    def start_updates(self):
        if self.update_task:
            logger.info(f'Feed Monitor Task Already Running')
            return False

        logger.info(f'Starting Feed Monitor Task')
        self.update_task = self.bot.loop.create_task(self.monitor_feed())
        return True

    async def monitor_feed(self):
        """Checks the feed data for new entries"""

        # wait until bot is actually finished starting up
        await self.bot.wait_until_ready()

        # loop the feed checks
        while True:
            logger.info(f'Update Starting')

            # get the feed data and stop if nothing received
            feed_text = await self.get_feed()
            if not feed_text:
                logger.warning('  No Feed Data')
                continue

            # parse feed to easily separate feed entries and stop if no entries
            logger.info(f'  Parsing Feed Data')
            entries = feedparser.parse(feed_text).entries
            if not entries:
                logger.error(' No Entries Found - Sleeping Until Next Update')
                await asyncio.sleep(120)
                continue

            # get reversed new entries, converted to RSSEntry objects
            logger.info(f'  Getting New Entries')
            new_entries = await self.get_new_entries(entries)
            if not new_entries:
                logger.info(f'No New Entries - Sleeping Until Next Update')
                await asyncio.sleep(120)
                continue

            # update each entries series data in the background
            self.bot.loop.create_task(self.update_entries_series(new_entries))

            self.bot.loop.create_task(self.send_to_webhooks(new_entries))

            logger.info(f'Update Task Sleeping Until Next Update')
            await asyncio.sleep(120)
            continue

    async def get_feed(self):
        try:
            async with self.bot.session.get(HATIGARMRSS) as r:
                if r.status == 200:
                    return await r.text()
                logger.error(f'Feed Connect Error: Status: {r.status}')
            return None
        except aiohttp.ClientError as e:
            logger.error(f'Feed Error ({type(e)}) - Exception: {e}')
            return None

    async def get_new_entries(self, entries):
        new_entries = []

        for entry in entries:
            # cast to entry object
            entry = RSSEntry(self.bot, entry)
            # stop going through entries if one found to already exist
            if await entry.exists():
                break
            # insert the new entry into the db
            await entry.insert()
            # add to new entries
            new_entries.append(entry)

        # return new entries from oldest to newest
        return list(reversed(new_entries))

    async def update_entries_series(self, entries):
        for entry in entries:
            await entry.update_series()

    async def send_to_webhooks(self, entries):
        webhooks = await self.all_webhooks()
        logger.info(f"Sending to {len(webhooks)} Webhooks")
        await asyncio.gather(*[self.notify(wh, entries) for wh in webhooks])

    async def all_webhooks(self):
        records = await self.settings_table.query.get()
        data = []
        for record in records:
            record = Map(dict(record))
            if not record.webhook_url or not record.enabled:
                continue

            if not record.avatar:
                record.avatar = self.avatar

            record.webhook = Webhook.from_url(
                record.webhook_url,
                adapter=AsyncWebhookAdapter(self.bot.session))

            data.append(record)
        return data

    @property
    def settings_table(self):
        return self.bot.dbi.table('feed_settings')

    async def notify(self, webhook, entries):
        logger.info(
            f"{len(entries)} New Webhook Notifications:\n"
            f"  GuildID: {webhook.guild_id}"
            f"  Delaying for {webhook.delay}s")

        await asyncio.sleep(webhook.delay)

        for entry in entries:
            await entry.send_to_webhook(webhook)

    async def test_chapter(self, url):
        if url.endswith('/'):
            url = url[:-1]
        page_url = url + '/1'
        try:
            async with self.bot.session.get(page_url) as r:
                return r.status == 200
        except aiohttp.ClientError as e:
            logger.error(f'Chapter Test Error ({type(e)}) - Exception: {e}')
            return None

    async def get_first_page(self, url):
        try:
            async with self.bot.session.get(url) as r:
                print(r.url)
                print(r.status)
                if r.status != 200:
                    return False
                content = await r.text()
                soup = bs4.BeautifulSoup(content, 'html.parser')
                allimgs = soup.find("div", {"id": "all"})
                if not allimgs:
                    return False
                firstimg = allimgs.find("img")
                if not firstimg:
                    return False
                return firstimg['data-src']
        except aiohttp.ClientError as e:
            logger.error(f'Chapter Test Error ({type(e)}) - Exception: {e}')
            return None

    @command()
    @checks.is_co_owner()
    async def firstpage(self, ctx, url):
        r = await self.get_first_page(url)
        await ctx.send(str(r))

    @property
    def is_updated(self):
        return self.data.entries[0].id != self.last_item_id

    @property
    def feed_table(self):
        return self.bot.dbi.table('feed_data')

    async def settings(self, guild_id, field=None):
        query = self.settings_table.query.where(guild_id=guild_id)
        if not field:
            return await query.get_one()
        else:
            return await query.get_value(field)

    @group(name='rss', invoke_without_command=True)
    async def _rss(self, ctx, guild_id: int = None):
        """RSS setting commands. If no subcommand given, shows RSS Status."""

        async with ctx.typing():
            guild_id = guild_id or ctx.guild.id
            guild = ctx.get.guild(guild_id)

            if not guild:
                return await ctx.error('Guild not found.')

            # get feed settings for this guild
            settings = await self.settings(guild_id)

            enabled = settings['enabled']
            webhook = bool(settings['webhook_url'])
            role_id = settings['sub_role_id']
            delay = settings['delay']
            role = ctx.get.role(role_id, guild_id) if role_id else False

            if role is False:
                role_name = '***No Role***'
            elif role is None:
                role_name = '***Invalid Role***'
            else:
                role_name = role.name

            if settings['avatar']:
                avatar = f"[Set]({settings['avatar']})"
            else:
                avatar = f"[Default]({self.avatar})"

            # get feed data to ensure it's up
            data = await self.get_feed()
            status_entries = [
                "**Online Feed:** " + ('Up' if data else '***Down***'),
                "**Webhook:** " + ('Registered' if webhook else '***Not Registered***'),
                "**Updates:** " + ('Enabled' if enabled else '***Disabled***'),
                f"**Role:** {role_name}",
                f"**Avatar:** {avatar}",
            ]

            if await checks.check_is_mod(ctx):
                status_entries.append(f"**Delay:** {delay}")

            await ctx.info(
                f'RSS | {guild.name}', '\n'.join(status_entries))

    @_rss.command()
    @checks.is_admin()
    async def resend(self, ctx, number: int = 1, ping: bool = False):
        """Resend the last number of releases to this guilds webhook."""
        # get guild settings
        record = await self.settings(ctx.guild.id)
        record = Map(dict(record))

        # check if webhook registered
        if not record.webhook_url:
            return await ctx.error('No webhook registered.')

        if not record.avatar:
            record.avatar = self.avatar

        # build actual webhook object from url
        record.webhook = Webhook.from_url(
            record.webhook_url, adapter=AsyncWebhookAdapter(self.bot.session))

        # get last x number of rss entries from database
        query = self.feed_table.query.order_by('updated', asc=False)
        results = await query.limit(number).get()
        entries = [RSSEntry(self.bot, Map(dict(r))) for r in results]

        for entry in reversed(entries):
            await entry.send_to_webhook(record, do_ping=ping)
        await ctx.ok()

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
    async def setavatar(self, ctx, avatar_url=None):
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
    @checks.is_admin()
    async def register(self, ctx, webhook_url=None):
        """Register the guild rss webhook."""
        insert = self.settings_table.insert(
            guild_id=ctx.guild.id, webhook_url=webhook_url, enabled=True)
        await insert.commit(do_update=True)
        await ctx.ok()

    @_rss.command()
    @checks.is_admin()
    async def enable(self, ctx, guild_id: int = None):
        """Enable rss updates."""

        if guild_id:
            if not await checks.check_is_co_owner(ctx):
                return await ctx.error(
                    "Only bot co-owners can disable for specific guilds.")

        guild_id = guild_id or ctx.guild.id

        insert = self.settings_table.insert(
            guild_id=guild_id, enabled=True)
        await insert.commit(do_update=True)
        await ctx.ok()

    @_rss.command()
    @checks.is_admin()
    async def disable(self, ctx, guild_id: int = None):
        """Disable rss updates."""

        if guild_id:
            if not await checks.check_is_co_owner(ctx):
                return await ctx.error(
                    "Only bot co-owners can disable for specific guilds.")

        guild_id = guild_id or ctx.guild.id

        insert = self.settings_table.insert(
            guild_id=guild_id, enabled=False)
        await insert.commit(do_update=True)
        await ctx.ok()

    async def global_subscribe(self, ctx, member, remove=False):
        role_id = await self.settings(member.guild.id, 'sub_role_id')
        if not role_id:
            return None

        role = ctx.get.role(role_id)

        if not role:
            return None

        if remove:
            if role not in member.roles:
                return False
            await member.remove_roles(role)
            return role
        else:
            if role in member.roles:
                return False
            await member.add_roles(role)
            return role

    @group(aliases=['sub', 'unsubscribe', 'unsub'])
    async def subscribe(self, ctx, *, series_title=None):
        """Subscribe/Unsubscribe to release updates.

        Use the `all` argument to remove all global and series subs.
        """

        ctx.remove = False
        if ctx.invoked_with in ['unsub', 'unsubscribe']:
            if series_title == 'all':
                return await self.unsub_all(ctx)

            ctx.remove = True

        if series_title:
            return await self.sub_series(ctx, series_title)

        result = await self.global_subscribe(ctx, ctx.author, ctx.remove)

        if result is None:
            return await ctx.error(
                "A notification role hasn't been setup for this guild.")

        if not result:
            action = 'unsubscribed' if ctx.remove else 'subscribed'
            return await ctx.warning(f'You are already {action}')

        if ctx.remove:
            return await ctx.success('You are no longer subscribed')

        await ctx.success(
            f'You are now subscribed with the role {result.name}')

    async def sub_series(self, ctx, series_title):
        series_title, score = await ctx.bot.series.match_series(series_title)

        if not series_title:
            return await ctx.error("No match found")

        if score < 80:
            ask = await ctx.info(f"Did you mean '{series_title}'?")
            await ask.add_reaction('\u2705')
            await ask.add_reaction('\u274e')

            def react_check(reaction, user):
                if user.id != ctx.author.id:
                    return False
                if reaction.message.id != ask.id:
                    return False
                if reaction.emoji not in ['\u2705', '\u274e']:
                    return False
                return True

            try:
                confirmation, __ = await self.bot.wait_for(
                    'reaction_add', timeout=60.0, check=react_check)
            except asyncio.TimeoutError:
                return await ctx.error('You took too long, try again later')

            await ask.clear_reactions()

            if confirmation.emoji == '\u274e':
                return await ctx.error('Cancelled')

        role = await self.bot.series.get_series_role(ctx.guild.id, series_title)

        if not role:
            return await ctx.error(
                "Something went wrong!",
                f"Let <@{ctx.bot.owner}> know I broke.")

        if ctx.remove:
            if role not in ctx.author.roles:
                return await ctx.warning(
                    f"You're not subscribed to {series_title}")
            await ctx.author.remove_roles(role)
            return await ctx.success(f"You're now unsubscribed from {series_title}")
        else:
            if role in ctx.author.roles:
                return await ctx.warning(
                    f"You're already subscribed to {series_title}")
            await ctx.author.add_roles(role)
            return await ctx.success(f"You're now subscribed to {series_title}")

    @command(aliases=['subs'])
    async def subscriptions(self, ctx, member: discord.Member = None):
        """See all your current subscriptions."""
        member = member or ctx.author
        role_id = await self.settings(member.guild.id, 'sub_role_id')
        if role_id:
            y = ctx.get.emoji('tickcircle')
            n = ctx.get.emoji('crosscircle')
            global_role = ctx.get.role(role_id)
            e = y if global_role in member.roles else n
            global_status = f"**{e} {global_role.name} Subscription**\n"
        else:
            global_status = ""

        names = await ctx.bot.series.series_shortnames()

        series_roles = []
        for shortname, title in names.items():
            role = await self.bot.series.get_series_role(
                ctx.guild.id, shortname, create_missing=False)
            if not role:
                continue
            if role in ctx.author.roles:
                series_roles.append(f"{role.name}: {title}")

        status = [global_status]

        if series_roles:
            status.append(f"**Series Subscriptions ({len(series_roles)})**")
            status.append('\n'.join(series_roles))
        else:
            status.append("No Series Subscriptions")

        await ctx.embed("Subscriptions", '\n'.join(status))

    async def unsub_all(self, ctx):
        """Remove all subscriptions."""
        result = await self.global_subscribe(ctx, ctx.author, remove=True)

        titles = await ctx.bot.series.series_titles()

        remove_roles = []
        for title in titles:
            role = await self.bot.series.get_series_role(
                ctx.guild.id, title, create_missing=False)
            if not role:
                continue
            if role in ctx.author.roles:
                remove_roles.append(role)

        await ctx.author.remove_roles(
            *remove_roles,
            atomic=True,
            reason="Member Unsubscribed")

        if not result and not remove_roles:
            return await ctx.warning('No subscriptions found')
        elif result and remove_roles:
            await ctx.success(
                f"Global and {len(remove_roles)} series subscriptions removed")
        elif result:
            await ctx.success(f"Global subscription removed")
        else:
            await ctx.success(
                f"{len(remove_roles)} series subscriptions removed")

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
                traceback.print_tb(
                    self.update_task._exception.__traceback__)
        await ctx.codeblock(msg)

    @command()
    async def latest(self, ctx, *, title=None):
        """Search for the latest release, filtered by given title."""
        table = self.feed_table
        if title:
            table.query.where(table['title'].ilike(f'%{title}%'))
        table.query.order_by('updated', asc=False)
        result = await table.query.get_first()

        if not result:
            return await ctx.error("Sorry, I couldn't find a match.")

        entry = RSSEntry(self.bot, Map(dict(result)))

        await entry.send_to_channel(ctx.channel)
