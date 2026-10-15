SETTINGS       = "5870982283724328568"
PENCIL         = "5870676941614354370"
TRASH          = "5870875489362513438"
CHECK          = "5870633910337015697"
CROSS          = "5870657884844462243"
HOME           = "5873147866364514353"
ARROW_UP       = "5963103826075456248"
ARROW_DOWN     = "5893057118545646106"
FOLDER         = "5870528606328852614"
BOX            = "5884479287171485878"
CHART_GROWTH   = "5870930636742595124"
CLOCK          = "5983150113483134607"
LOADING        = "5345906554510012647"
INFO           = "6028435952299413210"
BELL           = "6039486778597970865"
MONEY          = "5904462880941545555"
CODE           = "5940433880585605708"
ADD_TEXT       = "5771851822897566479"
PROFILE        = "5870994129244131212"
PEOPLE         = "5870772616305839506"
EYE            = "6037397706505195857"
LINK           = "5769289093221454192"
FORMAT         = "5778479949572738874"
CLIP           = "6039451237743595514"
SEND           = "5963103826075456248"


def emoji_tag(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


TAG_SETTINGS     = emoji_tag(SETTINGS,     "⚙️")
TAG_PENCIL       = emoji_tag(PENCIL,       "🖋")
TAG_TRASH        = emoji_tag(TRASH,        "🗑")
TAG_CHECK        = emoji_tag(CHECK,        "✅")
TAG_CROSS        = emoji_tag(CROSS,        "❌")
TAG_HOME         = emoji_tag(HOME,         "🏘")
TAG_ARROW_UP     = emoji_tag(ARROW_UP,     "⬆️")
TAG_ARROW_DOWN   = emoji_tag(ARROW_DOWN,   "📰")
TAG_FOLDER       = emoji_tag(FOLDER,       "📁")
TAG_BOX          = emoji_tag(BOX,          "📦")
TAG_CHART_GROWTH = emoji_tag(CHART_GROWTH, "📊")
TAG_CLOCK        = emoji_tag(CLOCK,        "⏰")
TAG_LOADING      = emoji_tag(LOADING,      "🔄")
TAG_INFO         = emoji_tag(INFO,         "ℹ️")
TAG_BELL         = emoji_tag(BELL,         "🔔")
TAG_MONEY        = emoji_tag(MONEY,        "🪙")
TAG_CODE         = emoji_tag(CODE,         "🔨")
TAG_ADD_TEXT     = emoji_tag(ADD_TEXT,     "🔡")
TAG_PROFILE      = emoji_tag(PROFILE,      "👤")
TAG_PEOPLE       = emoji_tag(PEOPLE,       "👥")
TAG_EYE          = emoji_tag(EYE,          "👁")
TAG_LINK         = emoji_tag(LINK,         "🔗")
TAG_FORMAT       = emoji_tag(FORMAT,       "↔️")
TAG_CLIP         = emoji_tag(CLIP,         "📎")
TAG_SEND         = emoji_tag(SEND,         "⬆️")

ERR_CROSS = "❌"
ERR_WARN  = "⚠️"