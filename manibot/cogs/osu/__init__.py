"""Osu Utility Module"""

from .cog import Osu

def setup(bot):
    bot.add_cog(Osu(bot))
