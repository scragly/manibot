"""This is the cog for managing series."""

from .cog import Series

def setup(bot):
    bot.add_cog(Series(bot))
