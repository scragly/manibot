import logging
import asyncio
import urllib
import datetime
import feedparser
import aiohttp
import discord
from discord import Webhook, AsyncWebhookAdapter, Embed
from manibot import command, group, Cog, checks
from manibot.utils.formatters import unescape_html, split_list

HATIGARMRSS = "https://www.hatigarmscans.net/feed"

logger = logging.getLogger('manibot.rss')

def get_poster_url(item_url):
    split = urllib.parse.urlsplit(item_url)
    join = 'http://hatigarmscans.net/uploads' + split.path
    imgurl = join.rsplit('/', 1)[0] + '/cover/cover_250x350.jpg'
    return imgurl

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

    async def on_message(self, message):
        if message.channel.id not in [328244845795737602, 444394290987270157, 465501965153992704]:
            return
        if message.content not in ['#iAm Notifbud', '##iAm Notifbud']:
            return
        await message.channel.send("Try `!sub`")

    def stop_updates(self):
        if not self.update_task:
            return False
        self.update_task.cancel()
        self.update_task = None
        return True

    def start_updates(self):

        logger.info(f'Running start_updates()')

        if self.update_task:
            logger.info(f'Update task not created - Already running')
            return False
        logger.info(f'Start Update Task')
        self.update_task = self.bot.loop.create_task(self.update_data())
        return True

    async def update_data(self, guild=None, limit=None):

        task_params = f'guild={guild}, limit={limit}' if guild else ''
        logger.info(
            f'Update Task Starting: {task_params}')

        while True:
            if not guild:
                await asyncio.sleep(30)
            rawdata = await self.get_feed()
            if not rawdata:

                if guild:
                    logger.warning(
                        'Update Task Ended: No data received from RSS Feed')
                    return False

                logger.warning(
                    'Update Task: No data received from RSS Feed '
                    '- Retry in 30s')
                continue

            logger.info(f'Update Task: Parsing Feed Data')
            self.data = feedparser.parse(rawdata)

            if not self.last_item_id and not guild:
                logger.info(f'Update Task: Getting Last Item ID from DB')
                self.last_item_id = await self.get_last_item()

            if self.is_updated or guild:
                logger.info(f'Update Task: Update Data Received')
                if not guild:
                    logger.info(f'Update Task: Updating Feed DB')
                    await self.update_feed_db()
                logger.info(
                    f'Update Task: Sending to Webhooks - {task_params}')
                await self.send_to_webhooks(guild, limit)
            else:
                logger.info(f'Update Task: No Update Found: {task_params}')

            if guild:
                logger.info(
                    f'Update Task Ended: {task_params}')
                break

            logger.info(
                f'Update Task Sleeping: {task_params}')
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

    async def update_series(self, item):
        timestamp = datetime.datetime.strptime(
            item.updated.rsplit('+', 1)[0], "%Y-%m-%dT%H:%M:%S")
        try:
            series_title = item.title.rsplit('#', 1)[0].strip()
            match, __ = await self.bot.series.match_series(series_title)
            if match:
                split = urllib.parse.urlsplit(item.id)
                chapter = split.path.rsplit('/', 1)[-1]
                await self.bot.series.edit_series(
                    title=match,
                    lastest_chapter=chapter,
                    updated=timestamp)
        except Exception as e:
            logger.error(f'Exception {type(e)}: {e}')

    async def update_feed_db(self):
        feed_insert = self.feed_table.insert
        last_item = self.last_item_id
        for item in self.data.entries:
            if item.id == last_item:
                break
            timestamp = datetime.datetime.strptime(
                item.updated.rsplit('+', 1)[0], "%Y-%m-%dT%H:%M:%S")
            await self.update_series(item)
            feed_insert(
                item_id=item.id, title=item.title, link=item.link,
                updated=timestamp, author=item.author,
                summary=str(item.summary), content=str(item.content)
            )
        await feed_insert.commit(do_update=False)

    async def send_to_webhooks(self, guild=None, limit=None):
        task_params = f'guild={guild}, limit={limit}' if guild else ''
        logger.info(f'Send To Webhooks: Starting - {task_params}')

        logger.info(f'Send To Webhooks: Getting New Items (limit={limit})')
        new_items = self.new_items(limit)
        if not new_items:
            logger.warning(f'Send To Webhooks Ended: No New Items')
            return

        logger.info(f'Send To Webhooks: Building Embeds')
        embeds = self.build_embeds(new_items)
        logger.info(f'Send To Webhooks: Split Updates into Chunks')
        msgs = split_list(embeds, 10)

        if not guild:
            logger.info(f'Send To Webhooks: Update last_item attribute.')
            await self.get_last_item()

        logger.info(f'Send To Webhooks: Start looping webhooks.')

        titles = [i.title.rsplit('#', 1)[0].strip() for i in new_items]

        for wh_data in await self.all_webhooks():
            guild_id = wh_data['guild_id']

            if guild and guild_id != guild:
                logger.info(
                    f"Send To Webhooks: guild={guild} - "
                    f"{guild_id} doesn't match.")
                continue

            if not guild and not wh_data['enabled']:
                logger.info(
                    f"Send To Webhooks: Updates are disabled for guild"
                    f"{guild_id}, skipping")
                continue

            webhook = wh_data['webhook']
            avatar = wh_data['avatar'] or self.avatar
            delay = wh_data['delay'] or 0
            do_ping = wh_data['ping']

            series_roles = []
            if not do_ping:
                global_role = None
                series_roles = None
            else:
                global_role = wh_data['sub_role_id']
                series_roles = await self.bot.series.get_series_roles(
                    guild_id, titles)

            logger.info(
                f"Send To Webhooks: Sending Notification for guild "
                f"{guild_id} - {webhook.url}, limit={limit}")

            self.bot.loop.create_task(
                self.notify(
                    webhook, global_role, series_roles, avatar, delay, msgs))

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

    async def notify(self, wh, global_role, series_roles, avatar, delay, msgs):
        logger.info(
            f"Notify Webhook ({wh.url}): "
            f"global_role={global_role}, delay={delay}, avatar={avatar}")

        logger.info(
            f"Notify Webhook ({wh.url}): "
            f"Delaying for {delay} seconds")

        await asyncio.sleep(delay)

        logger.info(
            f"Notify Webhook ({wh.url}): "
            f"Sending {len(msgs)} messages")

        for embeds in msgs:
            if embeds == msgs[0]:
                pings = f'<@&{global_role}> ' if global_role else None
                pings += ' '.join(set(series_roles))
            else:
                pings = None
            await wh.send(
                pings, embeds=embeds, username='New Update!', avatar_url=avatar)
            await asyncio.sleep(0.5)

        logger.info(
            f"Notify Webhook ({wh.url}): Complete")

    @property
    def is_updated(self):
        return self.data.entries[0].id != self.last_item_id

    @property
    def feed_table(self):
        return self.bot.dbi.table('feed_data')

    @property
    def settings_table(self):
        return self.bot.dbi.table('feed_settings')

    async def settings(self, guild_id, field=None):
        query = self.settings_table.query.where(guild_id=guild_id)
        if not field:
            return await query.get_one()
        else:
            return await query.get_value(field)

    def new_items(self, limit=None):
        new_items = []
        for item in self.data.entries:
            if limit and item == self.data.entries[limit]:
                break
            if not limit and item.id == self.last_item_id:
                break
            new_items.append(item)
        return list(reversed(new_items))

    def build_embeds(self, items):
        embeds = []
        for item in items:
            embed_data = self.build_embed(item.title, item.id, item.updated, item.summary)
            embeds.append(Embed.from_data(embed_data))
        return embeds

    def build_embed(self, name, page_url, timestamp, summary):
        if isinstance(timestamp, datetime.datetime):
            timestamp = timestamp.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            timestamp = timestamp.split('+')[0]
        poster_url = get_poster_url(page_url)
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
                "name"   : unescape_html(name),
                "url"    : page_url
            }
        }
        if not summary:
            summary = '\u200b'
        else:
            summary = f"*{unescape_html(summary)}*\n"
        data['description'] = f'{summary}\n\U0001f4d6 [Read it at Hatigarm Scans!]({page_url})'
        return data

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

    @_rss.command(name='update_series')
    @checks.is_co_owner()
    async def _update_series(self, ctx):
        titles = await ctx.bot.series.series_titles()
        table = self.feed_table
        for title in titles:
            if title:
                table.query.where(table['title'].ilike(f'%{title}%'))
            table.query.order_by('updated', asc=False)
            result = await table.query.get_first()

            if not result:
                continue

            await self.update_series(result)
            embed_data = self.build_embed(
                result['title'], result['item_id'], result['updated'], result['summary'])
            embed = discord.Embed.from_data(embed_data)
            await ctx.send(embed=embed)

    @_rss.command()
    @checks.is_admin()
    async def resend(self, ctx, number: int = 1):
        """Resend the last number of releases to this guilds webhook."""
        await self.update_data(ctx.guild.id, limit=number)
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
    async def register(self, ctx, webhook_url):
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
        embed_data = self.build_embed(
            result['title'], result['item_id'], result['updated'], result['summary'])
        embed = discord.Embed.from_data(embed_data)
        await ctx.send(embed=embed)
