# tpl/admin_emoji.py
"""Premium Emoji ID constants + HTML-теги с fallback-символами."""

# ═══════ Основные навигационные ═══════
SETTINGS   = "5870982283724328568"   # ⚙️
FOLDER     = "5870528606328852614"   # 📁
HOME       = "5873147866364514353"   # 🏘
CROSS      = "5870657884844462243"   # ❌
ARROW_UP   = "5963103826075456248"   # ⬆️
ARROW_DOWN = "5893057118545646106"   # 📰

# ═══════ Действия ═══════
PENCIL     = "5870676941614354370"   # 🖋
TRASH      = "5870875489362513438"   # 🗑
CHECK      = "5870633910337015697"   # ✅
EYE        = "6037397706505195857"   # 👁
EYE_HIDDEN = "6037243349675544634"   # 👁 скрыто
LINK       = "5769289093221454192"   # 🔗
CLIP       = "6039451237743595514"   # 📎
WRITE      = "5870753782874246579"   # ✍️
BRUSH      = "6050679691004612757"   # 🖌
CODE       = "5940433880585605708"   # 🔨 </>
ADD_TEXT   = "5771851822897566479"   # 🔡
DOWNLOAD   = "6039802767931871481"   # ⬇️
SEND_EMO   = "5963103826075456248"   # ⬆️

# ═══════ Данные / Статистика ═══════
CHART_GROWTH    = "5870930636742595124"   # 📊 рост
CHART_STATS     = "5870921681735781843"   # 📊 статистика
PROFILE         = "5870994129244131212"   # 👤
PEOPLE          = "5870772616305839506"   # 👥
PERSON_CHECK    = "5891207662678317861"   # 👤+✅
PERSON_CROSS    = "5893192487324880883"   # 👤+❌
WALLET          = "5769126056262898415"   # 👛
MONEY           = "5904462880941545555"   # 🪙
MONEY_SEND      = "5890848474563352982"   # 🪙 отправить
MONEY_RECEIVE   = "5879814368572478751"   # 🏧 принять
BOX             = "5884479287171485878"   # 📦
CALENDAR        = "5890937706803894250"   # 📅
CLOCK           = "5983150113483134607"   # ⏰
TIME_PAST       = "5775896410780079073"   # 🕓
TAG_EMOJI       = "5886285355279193209"   # 🏷

# ═══════ Статусы / Состояния ═══════
LOCK_CLOSED  = "6037249452824072506"   # 🔒
LOCK_OPEN    = "6037496202990194718"   # 🔓
BELL         = "6039486778597970865"   # 🔔
LOADING      = "5345906554510012647"   # 🔄
SMILE        = "5870764288364252592"   # 🙂
PARTY        = "6041731551845159060"   # 🎉
GIFT         = "6032644646587338669"   # 🎁

# ═══════ Медиа ═══════
MEDIA_PHOTO  = "6035128606563241721"   # 🖼
PIN          = "6042011682497106307"   # 📍
FONT         = "5870801517140775623"   # 🔗 шрифт
FORMAT       = "5778479949572738874"   # ↔️
APPS         = "5778672437122045013"   # 📦 приложения

# ═══════ Лавовая лампа (TWIX стиль) ═══════
LAVA         = "5465466718769913517"   # 🔥 лава из майнкрафта
LAVA_DOT     = "5226625550239422765"   # 🟠 анимированный оранжевый кружок

# ═══════ Прочее ═══════
INFO         = "6028435952299413210"   # ℹ️
BOT          = "6030400221232501136"   # 🤖
CRYPTO_BOT   = "5260752406890711732"   # 👾
MEGAPHONE    = "6039422865189638057"   # 📣


def emoji_tag(emoji_id: str, fallback: str) -> str:
    """Обёртка в HTML-тег Premium эмодзи c fallback-символом."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


# ── Готовые HTML-теги (с fallback-символами) ──
TAG_SETTINGS       = emoji_tag(SETTINGS,       "⚙️")
TAG_CROSS          = emoji_tag(CROSS,          "❌")
TAG_FOLDER         = emoji_tag(FOLDER,         "📁")
TAG_HOME           = emoji_tag(HOME,           "🏘")
TAG_PENCIL         = emoji_tag(PENCIL,         "🖋")
TAG_TRASH          = emoji_tag(TRASH,          "🗑")
TAG_CHECK          = emoji_tag(CHECK,          "✅")
TAG_EYE            = emoji_tag(EYE,            "👁")
TAG_EYE_HIDDEN     = emoji_tag(EYE_HIDDEN,     "👁")
TAG_LINK           = emoji_tag(LINK,           "🔗")
TAG_CLIP           = emoji_tag(CLIP,           "📎")
TAG_WRITE          = emoji_tag(WRITE,          "✍️")
TAG_BRUSH          = emoji_tag(BRUSH,          "🖌")
TAG_CODE           = emoji_tag(CODE,           "🔨")
TAG_ADD_TEXT       = emoji_tag(ADD_TEXT,       "🔡")
TAG_LOADING        = emoji_tag(LOADING,        "🔄")
TAG_CHART_GROWTH   = emoji_tag(CHART_GROWTH,   "📊")
TAG_CHART_STATS    = emoji_tag(CHART_STATS,    "📊")
TAG_PROFILE        = emoji_tag(PROFILE,        "👤")
TAG_PEOPLE         = emoji_tag(PEOPLE,         "👥")
TAG_WALLET         = emoji_tag(WALLET,         "👛")
TAG_MONEY          = emoji_tag(MONEY,          "🪙")
TAG_BOX            = emoji_tag(BOX,            "📦")
TAG_CALENDAR       = emoji_tag(CALENDAR,       "📅")
TAG_CLOCK          = emoji_tag(CLOCK,          "⏰")
TAG_TAG            = emoji_tag(TAG_EMOJI,       "🏷")
TAG_LOCK_CLOSED    = emoji_tag(LOCK_CLOSED,    "🔒")
TAG_LOCK_OPEN      = emoji_tag(LOCK_OPEN,      "🔓")
TAG_BELL           = emoji_tag(BELL,           "🔔")
TAG_SMILE          = emoji_tag(SMILE,          "🙂")
TAG_PARTY          = emoji_tag(PARTY,          "🎉")
TAG_GIFT           = emoji_tag(GIFT,           "🎁")
TAG_MEDIA_PHOTO    = emoji_tag(MEDIA_PHOTO,    "🖼")
TAG_PIN            = emoji_tag(PIN,            "📍")
TAG_FONT           = emoji_tag(FONT,           "🔗")
TAG_FORMAT         = emoji_tag(FORMAT,         "↔️")
TAG_APPS           = emoji_tag(APPS,           "📦")
TAG_INFO           = emoji_tag(INFO,           "ℹ️")
TAG_BOT            = emoji_tag(BOT,            "🤖")
TAG_CRYPTO_BOT     = emoji_tag(CRYPTO_BOT,     "👾")
TAG_MEGAPHONE      = emoji_tag(MEGAPHONE,      "📣")
TAG_ARROW_UP       = emoji_tag(ARROW_UP,       "⬆️")
TAG_ARROW_DOWN     = emoji_tag(ARROW_DOWN,     "📰")
TAG_DOWNLOAD       = emoji_tag(DOWNLOAD,       "⬇️")
TAG_SEND           = emoji_tag(SEND_EMO,        "⬆️")
TAG_MONEY_SEND     = emoji_tag(MONEY_SEND,     "🪙")
TAG_MONEY_RECEIVE  = emoji_tag(MONEY_RECEIVE,  "🏧")
TAG_TIME_PAST      = emoji_tag(TIME_PAST,      "🕓")
TAG_PERSON_CHECK   = emoji_tag(PERSON_CHECK,   "👤")
TAG_PERSON_CROSS   = emoji_tag(PERSON_CROSS,   "👤")

# ═══════ Стандартные эмодзи для ошибок (яркие, заметные) ═══════
ERR_CROSS = "❌"          # крестик ошибки — стандартный, красный
ERR_WARN  = "⚠️"          # предупреждение