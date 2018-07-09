"""Configuration values - Copy and name as config.py"""

# bot token from discord developers
bot_token = 'your_token_here'

# default bot settings
bot_prefix = '!'
bot_master = 12345678903216549878
bot_coowners = [174764205927432192,]
preload_extensions = ['rss','dev','utilities']

# minimum required permissions for bot user
bot_permissions = 268822592

# postgresql database credentials
db_details = {
    'username' : 'manibot',
    'database' : 'manibot',
    'hostname' : 'localhost',
    'password' : 'password'
}

# default language
lang_bot = 'en'

# help command categories
command_categories = {
    "Owner" : {
        "index"       : "5",
        "description" : "Owner-only commands for bot config or info."
    },
    "Server Config" : {
        "index"       : "10",
        "description" : "Server configuration commands."
    },
    "Bot Info" : {
        "index"       : "15",
        "description" : "Commands for finding out information on the bot."
    },
}
