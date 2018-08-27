import io
import textwrap
import traceback
import os

from contextlib import redirect_stdout
from subprocess import Popen, PIPE

from discord.ext import commands

from manibot import checks, command, group


class Dev:
    """Developer Tools"""

    def __init__(self, bot):
        self.bot = bot
        self._last_result = None
        self._last_eval_task = None

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')

    @command()
    @checks.is_owner()
    async def stopeval(self, ctx):
        if self._last_eval_task:
            self._last_eval_task.cancel()
            self._last_eval_task = None
            return await ctx.success('Last eval cancelled')
        else:
            return await ctx.error('No ongoing eval task.')

    async def do_eval(self, to_compile, env):
        exec(to_compile, env)

    @command(name='eval')
    @checks.is_owner()
    async def _eval(self, ctx, *, body: str):
        """Evaluates provided python code"""

        env = {
            'bot': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            '__': self._last_result
        }

        env.update(globals())

        body = self.cleanup_code(body)
        stdout = io.StringIO()

        to_compile = (f'async def func():\n{textwrap.indent(body, "  ")}')

        try:
            self._last_eval_task = ctx.bot.loop.create_task(self.do_eval(to_compile, env))
            # exec(to_compile, env)
            await self._last_eval_task
        except Exception as e:
            self._last_eval_task = None
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except Exception:
                pass

            if ret is None:
                if value:
                    paginator = commands.Paginator(prefix='```py')
                    for line in textwrap.wrap(value, 80):
                        paginator.add_line(line.rstrip().replace('`', '\u200b`'))
                    for p in paginator.pages:
                        await ctx.send(p)
            else:
                self._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')

        self._last_eval_task = None

    @command(aliases=['cls'])
    @checks.is_owner()
    async def clear_console(self, ctx):
        """Clear the console"""
        os.system('cls')
        await ctx.ok()

    @group()
    @checks.is_owner()
    async def git(self, ctx):
        ctx.git_path = os.path.dirname(ctx.bot.bot_dir)
        ctx.git_cmd = ['git']

    @git.command()
    async def pull(self, ctx):
        ctx.git_cmd.append('pull')

        p = Popen(ctx.git_cmd, stdout=PIPE, cwd=ctx.git_path)
        await ctx.codeblock(p.stdout.read().decode("utf-8"), syntax="")
