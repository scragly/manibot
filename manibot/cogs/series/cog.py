import logging
import asyncio
import urllib
import textwrap

import bs4
import asyncpg

import discord

from manibot import group, Cog, checks
from manibot.utils.formatters import make_embed
from manibot.utils.fuzzymatch import get_partial_match

HATIGARMURL = "https://www.hatigarmscans.net/"

GENRE_SEARCH_SQL = """
SELECT * FROM series
WHERE EXISTS (
    SELECT *
    FROM (SELECT UNNEST(series.genres)) x(genres)
    WHERE x.genres ILIKE '%' || $1 || '%');
"""

logger = logging.getLogger('manibot.rss')


def get_poster_url(item_url):
    if item_url.endswith('/'):
        item_url = item_url[:-1]
    split = urllib.parse.urlsplit(item_url)
    join = f'http://hatigarmscans.net/uploads{split.path}'
    return f'{join}/cover/cover_250x350.jpg'


class Series(Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.series = self

    def __unload(self):
        del self.bot.series

    @property
    def series_table(self):
        return self.bot.dbi.table('series')

    async def add_series(self, title, link, status, priority, shortname):
        insert = self.series_table.insert(
            title=title, link=link, status=status,
            priority=priority, shortname=shortname)
        await insert.commit()

    async def edit_by_title(self, existing, new=None, **changes):
        update = self.series_table.update
        if new:
            update(title=new)
        if changes:
            update(**changes)

        await update.where(title=existing).commit()

    async def edit_by_shortname(self, existing, new=None, **changes):
        update = self.series_table.update
        if new:
            update(shortname=new)
        if changes:
            update(**changes)

        await update.where(shortname=existing).commit()

    async def get_series(self, series=None, shortname=None):
        query = self.series_table.query

        if series:
            match, __ = await self.match_series(series)
            if not match:
                return None

            query.where(title=match)
            return await query.get_one()

        if shortname:
            query.where(self.series_table['shortname'].ilike(shortname))
            return await query.get_one()

        return await query.get()

    async def series_titles(self):
        return await self.series_table.query('title').get_values()

    async def series_shortnames(self, shortname_keys=True):
        data = await self.series_table.query('shortname', 'title').get()
        if shortname_keys:
            shortname_dict = {i['shortname']: i['title'] for i in data}
        else:
            shortname_dict = {i['title']: i['shortname'] for i in data}
        return shortname_dict

    async def match_series(self, search_term):
        names = await self.series_shortnames()
        match = [
            t for n, t in names.items() if n.lower() == search_term.lower()]
        if match:
            return (match[0], 100)

        return get_partial_match(await self.series_titles(), search_term)

    async def filter_by_genre(self, genre):
        return await self.bot.dbi.execute_query(GENRE_SEARCH_SQL, genre)

    async def series_info(self, ctx, record):
        shortname = record['shortname']
        title = record['title']
        link = record['link']
        latest = record['latest_chapter'] or ''
        updated = record['updated']
        status = record['status']
        priority = record['priority']
        genres = record['genres']
        series_type = record['type']

        info = [f"**Title:** {title}", f"**Status:** {status}"]
        no_priority = ['complete', 'completed', 'dropped', 'commission']
        if status.lower() not in no_priority:
            info.append(f"**Priority:** {priority}")
        if latest:
            latest_url = link + "/" + latest
            latest_str = f"**Latest:** [Chapter {latest}]({latest_url})"
            if updated:
                date = updated.strftime("%Y-%m-%d")
                latest_str += f" on {date}"
            info.append(latest_str)
        info.append(' ')
        if series_type:
            info.append(f"**Type:** {series_type}")
        if genres:
            genres_str = textwrap.wrap(', '.join(genres), width=30)
            info.append("**Genres:**")
            info.extend(genres_str)
        await ctx.info(
            f"Series Info: {shortname}",
            '\n'.join(info),
            title_url=link,
            thumbnail=get_poster_url(link),
            footer='Click the title to read it online!')

    async def get_series_roles(self, guild_id, titles):
        roles = []
        for title in titles:
            role = await self.get_series_role(guild_id, title)
            if role:
                roles.append(role.mention)
            else:
                roles.append(f"@{title} (New?)")
        return roles

    async def get_series_role(self, guild_id, series, create_missing=True):
        role = None
        guild = self.bot.get_guild(guild_id)

        title, __ = await self.match_series(series)

        if not title:
            return

        name_dict = await self.series_shortnames(shortname_keys=False)
        try:
            shortname_match = name_dict[title]
        except KeyError:
            return None

        if not shortname_match:
            return None

        role = self.bot.get(guild.roles, name=shortname_match)

        if not role:
            if create_missing:
                role = await guild.create_role(
                    name=shortname_match,
                    mentionable=True,
                    reason='Series Subscription Role for Updates')
            else:
                return None

        return role

    @group(invoke_without_command=True)
    async def series(self, ctx, *, series):
        result = await self.get_series(series)
        if not result:
            return await ctx.error("No match")

        await self.series_info(ctx, result)

    def web_info_embed(self, series, **data):
        data['Categories'] = '\n'.join(textwrap.wrap(
            ', '.join(data['Categories']), 30))
        data['Tags'] = '\n'.join(textwrap.wrap(', '.join(data['Tags']), 30))
        chapters = data.pop('Chapters')
        chapters = chapters[:5] if len(chapters) > 5 else chapters
        chapters = [(k.replace(series, 'Chapter'), v) for k, v in chapters]
        data['Recent Chapters'] = '\n'.join(
            [f"[{k}]({v})" for k, v in chapters])
        embed = make_embed(
            msg_type='info',
            title=series,
            title_url=data['URL'],
            thumbnail=get_poster_url(data.pop('URL')),
            fields=data)
        return embed

    @series.command(name='web')
    @checks.is_admin()
    async def get_webpage(self, ctx, *, series):
        series = await self.check_series_input(ctx, series)
        data = await self.get_series(series)

        async with self.bot.session.get(data['link']) as r:
            if r.status != 200:
                return False
            content = await r.text()
            soup = bs4.BeautifulSoup(content, 'html.parser')

        title = soup.find_all('h2', class_='widget-title')[0].get_text()
        table_values = soup.find_all('dd')
        table_titles = soup.find_all('dt')
        table = dict(
            zip([t.get_text(strip=True) for t in table_titles], table_values))

        info = {'Title': title, 'URL': data['link']}
        for k, v in table.items():
            if k in ['Categories', 'Tags']:
                v = [i.string for i in v if '\n' not in i.string]
                info[k] = v
            else:
                info[k] = v.get_text(strip=True)

        chapter_data = soup.find_all('h5', class_='chapter-title-rtl')

        chapters = [(i.a.get_text(), i.a['href']) for i in chapter_data]
        info['Chapters'] = chapters

        await ctx.send(embed=self.web_info_embed(series, **info))

    @series.command(name='genre')
    async def series_genre(self, ctx, *, genre):
        if len(genre) < 3:
            return await ctx.error('Search term must have 3 letters or more')
        results = await self.filter_by_genre(genre)
        if not results:
            return await ctx.error('No results found')

        if len(results) == 1:
            return await self.series_info(ctx, results[0])

        titles = [f"[{r['title']}]({r['link']})" for r in results]

        await ctx.success(
            f"{len(results)} series found with the {genre.title()} genre.",
            '\n'.join(titles))

    @series.command()
    @checks.is_admin()
    async def autoadd(self, ctx, link):
        if link.startswith('<') and link.endswith('>'):
            link = link.lstrip('<')
            link = link.rstrip('>')

        await ctx.trigger_typing()
        async with self.bot.session.get(link) as r:
            if r.status != 200:
                return await ctx.error('The given link was invalid')
            content = await r.text()
            soup = bs4.BeautifulSoup(content, 'html.parser')

        title = soup.find_all('h2', class_='widget-title')[0].get_text()
        table_values = soup.find_all('dd')
        table_titles = soup.find_all('dt')
        table = dict(
            zip([t.get_text(strip=True) for t in table_titles], table_values))

        info = {}

        for k, v in table.items():
            if k in ['Categories', 'Tags']:
                v = [i.string for i in v if '\n' not in i.string]
                info[k] = v
            else:
                info[k] = v.get_text(strip=True)

        chapter_data = soup.find_all('h5', class_='chapter-title-rtl')
        chapters = [(i.a.get_text(), i.a['href']) for i in chapter_data]
        latest_chapter = f"[{chapters[0][0]}]({chapters[0][1]})"
        chapter_count = len(chapters)

        # def msg_check(m):
        #     return m.author == ctx.author and m.channel == ctx.channel

        # def react_check(reaction, user):
        #     if user.id != ctx.author.id:
        #         return False
        #     if reaction.message.id != confirm_msg.id:
        #         return False
        #     if reaction.emoji not in ['\u2705', '\u274e']:
        #         return False
        #     return True

        # # series title

        # await ctx.info(f"Is the title {title} correct?")

        # try:
        #     name_rsp = await self.bot.wait_for(
        #         'message', timeout=60.0, check=msg_check)
        # except asyncio.TimeoutError:
        #     return await ctx.error('You took too long, try again later')

        # title = name_rsp.clean_content

        # if title in await self.series_titles():
        #     return await ctx.error('Series already exists')

        # if not status:
        #     await ctx.info(f"What's the scanlation status of {title}?")

        #     try:
        #         status_rsp = await self.bot.wait_for(
        #             'message', timeout=60.0, check=msg_check)
        #     except asyncio.TimeoutError:
        #         return await ctx.error('You took too long, try again later')

        #     status = status_rsp.clean_content

        # if not priority:
        #     await ctx.info(f"What's the scanlation priority of {title}?")

        #     try:
        #         priority_rsp = await self.bot.wait_for(
        #             'message', timeout=60.0, check=msg_check)
        #     except asyncio.TimeoutError:
        #         return await ctx.error('You took too long, try again later')

        #     priority = priority_rsp.clean_content

        # await ctx.info(f"What's the short name for {title}?")

        # try:
        #     shortname_rsp = await self.bot.wait_for(
        #         'message', timeout=60.0, check=msg_check)
        # except asyncio.TimeoutError:
        #     return await ctx.error('You took too long, try again later')

        # shortname = shortname_rsp.clean_content

        # confirm_msg = await ctx.embed(
        #     f"Thanks! Does this look right?",
        #     (f"**{title}**\n"
        #      f"[Series Link]({link})\n"
        #      f"Shortname: {shortname}\n"
        #      f"Status: {status}\n"
        #      f"Priority: {priority}"),
        #     thumbnail=get_poster_url(link))

        # await confirm_msg.add_reaction('\u2705')
        # await confirm_msg.add_reaction('\u274e')

        # try:
        #     confirmation, __ = await self.bot.wait_for(
        #         'reaction_add', timeout=60.0, check=react_check)
        # except asyncio.TimeoutError:
        #     return await ctx.error('You took too long, try again later')

        # await confirm_msg.clear_reactions()

        # if confirmation.emoji == '\u274e':
        #     return await ctx.error('Cancelled')

        # await self.add_series(title, link, status, priority, shortname)
        # await ctx.success(
        #     f"Added {title}",
        #     ("Consider adding extra details with:"
        #      f"```{ctx.prefix}series edit <series>```"))

    @series.command()
    @checks.is_admin()
    async def add(self, ctx, link, title=None, status=None, priority=None):
        if link.startswith('<') and link.endswith('>'):
            link = link.lstrip('<')
            link = link.rstrip('>')

        if not title:
            await ctx.info("What's the name of the series?")

            def msg_check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                name_rsp = await self.bot.wait_for(
                    'message', timeout=60.0, check=msg_check)
            except asyncio.TimeoutError:
                return await ctx.error('You took too long, try again later')

            title = name_rsp.clean_content

        if title in await self.series_titles():
            return await ctx.error('Series already exists')

        if not status:
            await ctx.info(f"What's the scanlation status of {title}?")

            try:
                status_rsp = await self.bot.wait_for(
                    'message', timeout=60.0, check=msg_check)
            except asyncio.TimeoutError:
                return await ctx.error('You took too long, try again later')

            status = status_rsp.clean_content

        if not priority:
            await ctx.info(f"What's the scanlation priority of {title}?")

            try:
                priority_rsp = await self.bot.wait_for(
                    'message', timeout=60.0, check=msg_check)
            except asyncio.TimeoutError:
                return await ctx.error('You took too long, try again later')

            priority = priority_rsp.clean_content

        await ctx.info(f"What's the short name for {title}?")

        try:
            shortname_rsp = await self.bot.wait_for(
                'message', timeout=60.0, check=msg_check)
        except asyncio.TimeoutError:
            return await ctx.error('You took too long, try again later')

        shortname = shortname_rsp.clean_content

        confirm_msg = await ctx.embed(
            f"Thanks! Does this look right?",
            (f"**{title}**\n"
             f"[Series Link]({link})\n"
             f"Shortname: {shortname}\n"
             f"Status: {status}\n"
             f"Priority: {priority}"),
            thumbnail=get_poster_url(link))

        await confirm_msg.add_reaction('\u2705')
        await confirm_msg.add_reaction('\u274e')

        def react_check(reaction, user):
            if user.id != ctx.author.id:
                return False
            if reaction.message.id != confirm_msg.id:
                return False
            if reaction.emoji not in ['\u2705', '\u274e']:
                return False
            return True

        try:
            confirmation, __ = await self.bot.wait_for(
                'reaction_add', timeout=60.0, check=react_check)
        except asyncio.TimeoutError:
            return await ctx.error('You took too long, try again later')

        await confirm_msg.clear_reactions()

        if confirmation.emoji == '\u274e':
            return await ctx.error('Cancelled')

        await self.add_series(title, link, status, priority, shortname)
        await ctx.success(
            f"Added {title}",
            ("Consider adding extra details with:"
             f"```{ctx.prefix}series edit <series>```"))

    async def check_series_input(self, ctx, title):
        match, score = await self.match_series(title)
        if not match:
            return await ctx.error(
                'No match',
                f'Add a new series with\n```{ctx.prefix}series add```')

        if score < 80:
            ask = await ctx.info(f"Did you mean '{match}'?")

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
                await ctx.error('You took too long, try again later')
                return None

            await ask.clear_reactions()

            if confirmation.emoji == '\u274e':
                await ctx.error('Cancelled')
                return None

        return match

    @series.group(invoke_without_command=True)
    @checks.is_admin()
    async def edit(self, ctx, *, title):

        title = await self.check_series_input(ctx, title)

        choices = {
            1: "link",
            2: "title",
            3: "shortname",
            4: "status",
            5: "priority",
            6: "genres",
            7: "type"
        }

        choices_pretty = []
        for k, v in choices.items():
            choices_pretty.append(f"{k} - {v.title()}")

        while True:
            embed = await ctx.info(
                f"What do you want to edit?",
                f"**Editing {title}**\n" + '\n'.join(choices_pretty),
                send=False)

            options = list(choices)
            options.append('false')
            response = await ctx.ask(embed, options=options, autodelete=True)

            if response is None:
                return await ctx.error('You took too long, try again later')

            if not response:
                return await ctx.error('Edit cancelled')

            field = choices[response]

            is_type = field == 'type'

            is_other = False

            if is_type:
                type_choices = {
                    1: 'Manga',
                    2: 'Manhua',
                    3: 'Manhwa',
                    4: 'Other'
                }
                options = list(type_choices)
                options.append('false')

                type_choices_pretty = []
                for k, v in type_choices.items():
                    type_choices_pretty.append(f"{k} - {v.title()}")

                embed = await ctx.info(
                    f"What's the new {field}?",
                    '\n'.join(type_choices_pretty),
                    send=False)

                response = await ctx.ask(embed, options=options, autodelete=True)

                if response is None:
                    return await ctx.error(
                        'You took too long, try again later')
                elif not response:
                    await ctx.error('Edit cancelled')
                    continue
                elif response == 4:
                    is_other = True
                    msg = await ctx.info(f"What's the type name?")
                else:
                    new_value = type_choices[response]
            else:
                msg = await ctx.info(f"What's the new {field}?")

            if not is_type or is_other:
                def msg_check(m):
                    return m.author == ctx.author and m.channel == ctx.channel

                try:
                    response = await self.bot.wait_for(
                        'message', timeout=60.0, check=msg_check)
                except asyncio.TimeoutError:
                    return await ctx.error(
                        'You took too long, try again later')
                finally:
                    await msg.delete()

                new_value = response.clean_content

            if field == 'genres':
                new_value = list(
                    map(str.title, map(str.strip, new_value.split(','))))
                new_value_str = '\n'.join(new_value)
            else:
                new_value_str = new_value

            embed = await ctx.info(
                f"Is this {field.title()} update correct?",
                new_value_str,
                send=False)

            correct = await ctx.ask(
                embed, options=['true', 'false'], autodelete=True)

            if correct is None:
                return await ctx.error('You took too long, try again later')

            if not correct:
                await ctx.error('Update Cancelled.')

            else:
                kwarg = field if field != 'title' else 'new'
                data = {kwarg: new_value}

                await self.edit_by_title(title, **data)
                await ctx.success(f'{field.title()} updated for {title}')

            embed = await ctx.info(
                f"Do you want to edit something else?", send=False)
            response = await ctx.ask(
                embed, options=['true', 'false'], autodelete=True)
            if response is None:
                return await ctx.error('You took too long, try again later')
            if not response:
                break

    @edit.command(name='link')
    @checks.is_admin()
    async def edit_link(self, ctx, title, link):

        title = await self.check_series_input(ctx, title)

        if not title:
            return

        try:
            await self.edit_by_title(title, link=link)
        except asyncpg.UniqueViolationError:
            return await ctx.error(
                f"That link is already used")

        await ctx.success(f'{title} link changed to:', link)

    @edit.command(name='shortname')
    @checks.is_admin()
    async def edit_shortname(self, ctx, title, shortname):

        title = await self.check_series_input(ctx, title)

        if not title:
            return

        name_dict = await self.series_shortnames(shortname_keys=False)

        try:
            original_shortname = name_dict[title]
        except KeyError:
            return await ctx.error('Whoops, something went wrong!')

        try:
            await self.edit_by_title(title, shortname=shortname)
        except asyncpg.UniqueViolationError:
            return await ctx.error(
                f"The shortname {shortname} is already used")

        await ctx.success(f'{title} shortname changed to {shortname}')

        for guild in self.bot.guilds:
            role = self.bot.get(guild.roles, name=original_shortname)
            if role:
                print(f"{role} role in {role.guild}")
            if not role:
                continue
            await role.edit(name=shortname)

    @edit.command(name='latest')
    @checks.is_admin()
    async def edit_latest(self, ctx, title, latest_chapter):

        title = await self.check_series_input(ctx, title)

        if not title:
            return

        await self.edit_by_title(title, latest_chapter=latest_chapter)

        await ctx.success(
            f'{title} latest chapter changed to {latest_chapter}')

    @edit.command(name='title')
    @checks.is_admin()
    async def edit_title(self, ctx, title, *, new_title):

        title = await self.check_series_input(ctx, title)

        if not title:
            return

        try:
            await self.edit_by_title(title, new_title)
        except asyncpg.UniqueViolationError:
            return await ctx.error(
                f"The title {title} is already used")

        role = await self.get_series_role(
            ctx.guild.id, title, create_missing=False)
        if role:
            try:
                await role.edit(name=new_title)
            except discord.Forbidden:
                await ctx.error(
                    f'The series role could not be changed to the new name.',
                    ("Please edit the role manually by finding the original "
                     "series name in roles and editing to the new name. "
                     "Otherwise, ensure this bot has the `manage_roles` "
                     "permission and try again."))

        await ctx.success(f'Title Updated: {new_title}.')

    @edit.command(name='status')
    @checks.is_admin()
    async def edit_status(self, ctx, title, *, status):

        title = await self.check_series_input(ctx, title)

        if not title:
            return

        await self.edit_by_title(title, status=status)

        await ctx.success(f'{title} status changed to {status}')

    @edit.command(name='type')
    @checks.is_admin()
    async def edit_type(self, ctx, title, *, series_type):

        title = await self.check_series_input(ctx, title)

        if not title:
            return

        await self.edit_by_title(title, type=series_type)

        await ctx.success(f'{title} type changed to {series_type}')

    @edit.command(name='priority')
    @checks.is_admin()
    async def edit_priority(self, ctx, title, *, priority):

        title = await self.check_series_input(ctx, title)

        if not title:
            return

        await self.edit_by_title(title, priority=priority)

        await ctx.success(f'{title} priority changed to {priority}')

    @edit.command(name='genres')
    @checks.is_admin()
    async def edit_genres(self, ctx, title, *, genres):

        title = await self.check_series_input(ctx, title)

        if not title:
            return

        genres = list(map(str.title, map(str.strip, genres.split(','))))

        await self.edit_by_title(title, genres=genres)

        genres_str = '\n'.join(textwrap.wrap(', '.join(genres), width=30))

        await ctx.success(f'Genres updated for {title}', genres_str)

    @series.command()
    @checks.is_co_owner()
    async def lock_roles(self, ctx):
        series = await self.series_titles()
        roles = [await self.get_series_role(ctx.guild.id, title) for title in series]
        for role in roles:
            await role.edit(mentionable=False)
        await ctx.ok()

    @series.command()
    @checks.is_admin()
    async def unlock(self, ctx, *, title):
        title = await self.check_series_input(ctx, title)
        role = await self.get_series_role(ctx.guild.id, title)

        if not role:
            return await ctx.error("There is no role for that series")

        await role.edit(mentionable=True)
        await ctx.success(f"Role {role.name} unlocked,",
                          "The role will be mentionable for one use
                          "or until 2 minutes have passed.\n"
                          "Please make the mention soon to prevent other"
                          "users mentioning the role.")

        def mention_check(message):
            if message.guild.id != ctx.guild.id:
                return False
            return role.mention in message.content

        async def reset_role(timeout=False):
            await role.edit(mentionable=False)
            if timeout:
                return await ctx.send("Took too long, role reset.")
            await ctx.send("Role mention detected, role reset.")

        task = ctx.bot.loop.create_task(
            ctx.bot.wait_for('message', check=mention_check)
        )

        task.add_done_callback(reset_role)

        await asyncio.sleep(120)

        if not task.done():
            await reset_role(timeout=True)
