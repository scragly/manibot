#!/usr/bin/python3
"""A Discord bot for the Hatigarm Community.

Manibot is a Discord bot written in Python 3.6.1 using version 1.0.0a of the discord.py library.
It is built to add notification and utilities to the Hatigarm Community."""

__version__ = "1.0.0b"

__author__ = "scragly"
__maintainer__ = "scragly"
__status__ = "Beta"

from manibot.core.bot import command, group
from manibot.core.cog_base import Cog
from manibot.core import checks, errors
