from manibot.core.data_manager import schema

def setup(bot):
    feed_data = bot.dbi.table('feed_data')
    feed_data.new_columns = [
        schema.StringColumn('item_id', primary_key=True),
        schema.StringColumn('title'),
        schema.StringColumn('link'),
        schema.DatetimeColumn('updated'),
        schema.StringColumn('author'),
        schema.StringColumn('summary'),
        schema.StringColumn('content')
        ]

    feed_settings = bot.dbi.table('feed_settings')
    feed_settings.new_columns = [
        schema.IDColumn('guild_id', primary_key=True),
        schema.StringColumn('webhook_url'),
        schema.IDColumn('sub_role_id'),
        schema.StringColumn('avatar'),
        schema.IntColumn('delay', default=60),
        schema.BoolColumn('ping', default=True),
        schema.BoolColumn('enabled')
        ]

    return [feed_data, feed_settings]
