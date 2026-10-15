"""TWIX Bot Configuration — loaded from .env file."""
import os
from pathlib import Path
from decimal import Decimal

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")

# ── Paths ──────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.getenv("DB_PATH", "twix.db"))

TEMPLATES_FILE = DATA_DIR / "templates.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

# ── Telegram ───────────────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("BOT_TOKEN", '')

ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", '0').split(",") if x.strip()]

# ── Business Defaults ──────────────────────────────────────────────────────

DEFAULT_RATES = [
    {"name": "до 100 USDT", "min": "0", "max": "100", "rate": "84.00"},
    {"name": "до 300 USDT", "min": "100", "max": "300", "rate": "85.00"},
    {"name": "до 10000 USDT", "min": "300", "max": "10000", "rate": "86.00"},
]

RAPIRA_COEFFICIENT = Decimal("1.147")

# Loyalty tiers: (volume_threshold, rate_bonus)
LOYALTY_TIERS = [
    (Decimal("500"), Decimal("0.2")),
    (Decimal("1000"), Decimal("0.4")),
]

# Auto-cancel timeout in seconds
AUTO_CANCEL_SECONDS = int(os.getenv("AUTO_CANCEL_SECONDS", "3600"))

# Ticket threshold in RUB worth
TICKET_THRESHOLD = Decimal("2000")
