from manibot.core.data_manager import schema, sqltypes

def setup(bot):
    series = bot.dbi.table('series')
    series.new_columns = [
        schema.StringColumn('shortname', primary_key=True),
        schema.StringColumn('title', unique=True),
        schema.StringColumn('link'),
        schema.StringColumn('type'),
        schema.StringColumn('latest_chapter'),
        schema.DatetimeColumn('updated'),
        schema.StringColumn('status'),
        schema.StringColumn('priority'),
        schema.Column('genres', sqltypes.ArraySQL(sqltypes.StringSQL()))
        ]

    return series
