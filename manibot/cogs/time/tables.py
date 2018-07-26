from manibot.core.data_manager import schema

def setup(bot):
    timezonetable = bot.dbi.table('member_timezones')
    timezonetable.new_columns = [
        schema.IDColumn('member_id', primary_key=True),
        schema.StringColumn('timezone')
        ]

    return timezonetable
