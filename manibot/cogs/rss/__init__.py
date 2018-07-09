"""This is an RSS feed notification cog."""

from .cog import RSS

def setup(bot):
    bot.add_cog(RSS(bot))
