"""Role Colour Management Module"""

from .cog import RoleColours


def setup(bot):
    bot.add_cog(RoleColours(bot))
