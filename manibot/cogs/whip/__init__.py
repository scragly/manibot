"""This is a fun cog for Hati's whip."""

from .cog import Whip

def setup(bot):
    bot.add_cog(Whip(bot))
