import discord
from discord.ext import commands

from manibot import Cog, command


colour_roles = {
    302958707241648128: {
        312126115273506817: 334811709053206540,  # ron
        146430655197216769: 304510376509177856,  # kuka
        214932117287600128: 312297405175562250   # hati
    },
    351755506341117954: {
        174764205927432192: 351758043643510788   # scragly test role
    }
}


def has_colour_role(ctx):
    gcr = colour_roles.get(ctx.guild.id)
    if not gcr:
        return False
    mcr = gcr.get(ctx.author.id)
    if mcr:
        return True
    return False


class RoleColours(Cog):

    @command()
    @commands.check(has_colour_role)
    async def setcolour(self, ctx, colour: discord.Colour = None):
        """Allows you to adjust your unique colour role value.

        Accepts the following colour hex formats:
            0x<hex>, #<hex>, 0x#<hex>

        Also accepts the following preset colours:
            default, teal, dark_teal, green, dark_green, blue, dark_blue,
            purple, dark_purple, magenta, dark_magenta, gold, dark_gold,
            orange, dark_orange, red, dark_red, lighter_grey, dark_grey,
            light_grey, darker_grey, blurple, greyple.
        """
        if not colour:
            return await ctx.embed(
                ctx.author.top_role.colour,
                colour=ctx.author.top_role.colour)

        role = ctx.get.role(colour_roles[ctx.author.id])
        await role.edit(colour=colour)
        await ctx.success(f"{role.name} role changed to colour: {colour}")
