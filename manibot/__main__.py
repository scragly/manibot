"""Bot Module.

By using this command instead of ``manibot``, the bot will bypass the launcher.

Command:
    ``manibot-bot``

Options:
    -d, --debug   Enable debug mode.
"""
import argparse
import asyncio
import sys

import discord

from manibot.core import logger, context
from manibot.core.bot import Bot
from manibot.utils import ExitCodes

if discord.version_info.major < 1:
    print("You are not running discord.py v1.0.0a or above.\n\n"
          "This bot requires the new discord.py library to function "
          "correctly. Please install the correct version.")
    sys.exit(1)

def run_bot(debug=False, launcher=None, from_restart=False):
    """Sets up the bot, runs it and handles exit codes."""

    # create async loop and setup contextvar
    loop = asyncio.get_event_loop()
    context.ctx_setup(loop)

    # create bot instance
    description = "Manibot v1 - Beta"
    bot = Bot(
        description=description, launcher=launcher,
        debug=debug, from_restart=from_restart)

    # setup logging
    bot.logger = logger.init_logger(bot, debug)

    # load the required core extensions
    bot.load_extension('manibot.core.error_handling')
    bot.load_extension('manibot.core.commands')
    bot.load_extension('manibot.core.cog_manager')

    # load extensions marked for preload in config
    for ext in bot.preload_ext:
        print(ext)
        ext_name = ("manibot.cogs."+ext)
        bot.load_extension(ext_name)

    if bot.token is None or not bot.default_prefix:
        bot.logger.critical("Token and prefix must be set in order to login.")
        sys.exit(1)
    try:
        loop.run_until_complete(bot.start(bot.token))
    except discord.LoginFailure:
        bot.logger.critical("Invalid token")
        loop.run_until_complete(bot.logout())
        bot.shutdown_mode = ExitCodes.SHUTDOWN
    except KeyboardInterrupt:
        bot.logger.info("Keyboard interrupt detected. Quitting...")
        loop.run_until_complete(bot.logout())
        bot.shutdown_mode = ExitCodes.SHUTDOWN
    except Exception as exc:
        bot.logger.critical("Fatal exception", exc_info=exc)
        loop.run_until_complete(bot.logout())
    finally:
        code = bot.shutdown_mode
        sys.exit(code.value)

def parse_cli_args():
    parser = argparse.ArgumentParser(
        description="Manibot - A Discord Bot for the Hatigarm Community.")
    parser.add_argument(
        "--debug", "-d", help="Enabled debug mode.", action="store_true")
    parser.add_argument(
        "--launcher", "-l", help=argparse.SUPPRESS, action="store_true")
    parser.add_argument(
        "--fromrestart", help=argparse.SUPPRESS, action="store_true")
    return parser.parse_args()



def main():
    args = parse_cli_args()
    run_bot(debug=args.debug, launcher=args.launcher, from_restart=args.fromrestart)

if __name__ == '__main__':
    main()
