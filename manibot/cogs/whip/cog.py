import os
import random

import discord

from manibot import Cog


class Whip(Cog):
    """Hati's Whip Fun"""

    async def on_message(self, message):
        if not message.guild:
            return
        if not message.guild.id in [351755506341117954, 302958707241648128]:
            return
        if not 'whip' in message.clean_content.lower():
            return
        if message.author.id in [214932117287600128]:
            await self.whip_by_hati(message.channel)
        elif 329189822981865472 in [r.id for r in message.author.roles]:
            await self.whip_staff(message.channel)

    async def whip_by_hati(self, channel):
        folder = os.path.join(os.path.dirname(__file__), 'gifs', 'hati')
        chosen = os.path.join(folder, random.choice(os.listdir(folder)))
        await channel.send(file=discord.File(chosen))

    async def whip_staff(self, channel):
        folder = os.path.join(os.path.dirname(__file__), 'gifs', 'staff')
        chosen = os.path.join(folder, random.choice(os.listdir(folder)))
        await channel.send(file=discord.File(chosen))
