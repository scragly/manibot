from manibot.core.data_manager import schema

def setup(bot):
    table = bot.dbi.table('osu_members')
    table.new_columns = [
        schema.IDColumn('member_id', primary_key=True),
        schema.StringColumn('osu_username')
        ]

    return table
