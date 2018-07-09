"""This is a developer tools cog."""

from .cog import Dev

def setup(bot):
    bot.add_cog(Dev(bot))
