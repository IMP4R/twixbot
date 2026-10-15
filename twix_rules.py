"""TWIX-specific rules for bot_agent.

Based on bugs from TELEGRAM_BOT_BUG_CATALOG.md and AGENTS.md rules.
Copy this file to your TWIX project root and run:

    python -m bot_agent run --profile twix_client --rules ./twix_rules.py --scenario full_scan

"""

from __future__ import annotations

import re
from typing import Iterator, Optional

from bot_agent.rules.base import BaseRule, Issue
from bot_agent.inspector import ScreenState


# ── Helpers ─────────────────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+"
)


def _contains_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(text))


def _contains_unicode_emoji(text: str) -> bool:
    return bool(_EMOJI_RE.search(text))


def _is_numeric_id(value: Optional[str]) -> bool:
    if not value:
        return True  # None/empty is OK (no icon)
    return value.isdigit()


# ── TWIX Rules ──────────────────────────────────────────────────────────────

class NoHtmlInButtonText(BaseRule):
    """HTML tags in button text cause Telegram rendering issues.
    Bug: admin.tickets button had <tg-emoji> in text instead of icon field."""

    rule_id = "twix_no_html_buttons"
    description = "Button text contains HTML tags"

    def check(self, screen: ScreenState, history: Optional[list] = None) -> Iterator[Issue]:
        for b in screen.all_callback_buttons():
            if _contains_html(b.text):
                yield Issue(
                    severity="critical",
                    rule_id=self.rule_id,
                    screen_fingerprint=screen.fingerprint(),
                    detail=f"Button text contains HTML: '{b.text[:50]}'. Use icon_custom_emoji_id for emoji.",
                    button_text=b.text,
                    callback_data=b.callback_data,
                )


class NumericIconCustomEmojiId(BaseRule):
    """icon_custom_emoji_id must be a numeric string, not HTML or TAG_*."""

    rule_id = "twix_numeric_emoji_id"
    description = "icon_custom_emoji_id is not a valid numeric ID"

    def check(self, screen: ScreenState, history: Optional[list] = None) -> Iterator[Issue]:
        for b in screen.all_callback_buttons():
            if b.icon_custom_emoji_id is not None and not _is_numeric_id(b.icon_custom_emoji_id):
                yield Issue(
                    severity="critical",
                    rule_id=self.rule_id,
                    screen_fingerprint=screen.fingerprint(),
                    detail=f"icon_custom_emoji_id='{b.icon_custom_emoji_id}' is not numeric. Must be Telegram Premium emoji ID.",
                    button_text=b.text,
                    callback_data=b.callback_data,
                    actual=b.icon_custom_emoji_id,
                    expected="numeric string (e.g. 5904462880941545555)",
                )


class NoDoubleEmoji(BaseRule):
    """Unicode emoji in button text + icon_custom_emoji_id = double emoji visible to user."""

    rule_id = "twix_double_emoji"
    description = "Button has both Unicode emoji text and icon_custom_emoji_id"

    def check(self, screen: ScreenState, history: Optional[list] = None) -> Iterator[Issue]:
        for b in screen.all_callback_buttons():
            if b.icon_custom_emoji_id and _contains_unicode_emoji(b.text):
                yield Issue(
                    severity="warning",
                    rule_id=self.rule_id,
                    screen_fingerprint=screen.fingerprint(),
                    detail=f"Button '{b.text}' has Unicode emoji in text AND icon_custom_emoji_id={b.icon_custom_emoji_id}. User sees double emoji.",
                    button_text=b.text,
                    callback_data=b.callback_data,
                )


class MissingBackButtonInSubscreens(BaseRule):
    """All non-HOME screens must have a back/cancel button. Dead end = user stuck."""

    rule_id = "twix_dead_end"
    description = "Screen lacks back/cancel button"

    BACK_KEYWORDS = ["назад", "отмена", "меню", "home", "cancel", "back", "закрыть"]

    def check(self, screen: ScreenState, history: Optional[list] = None) -> Iterator[Issue]:
        btns = screen.all_callback_buttons()
        if not btns:
            return
        # Skip if this is likely HOME (only 1-3 buttons, no 'back' needed)
        if len(btns) <= 2:
            return
        has_back = any(
            any(kw in (b.text or "").lower() for kw in self.BACK_KEYWORDS)
            for b in btns
        )
        if not has_back:
            yield Issue(
                severity="warning",
                rule_id=self.rule_id,
                screen_fingerprint=screen.fingerprint(),
                detail=f"Screen has {len(btns)} buttons but no back/cancel. User may get stuck without /start.",
                button_text=", ".join(b.text for b in btns[:3]),
            )


class ButtonCountForAdminScreens(BaseRule):
    """Admin screens often have many buttons; warn if >6."""

    rule_id = "twix_admin_button_overload"
    description = "Admin screen has too many buttons"

    def check(self, screen: ScreenState, history: Optional[list] = None) -> Iterator[Issue]:
        btns = screen.all_callback_buttons()
        # Only for admin-ish screens (heuristic: button text contains admin keywords)
        adminish = any(
            "админ" in (b.text or "").lower() or "admin" in (b.text or "").lower()
            for b in btns
        )
        if len(btns) > 6 and adminish:
            yield Issue(
                severity="info",
                rule_id=self.rule_id,
                screen_fingerprint=screen.fingerprint(),
                detail=f"Admin-like screen has {len(btns)} buttons. Consider grouping into submenus.",
            )


class MediaPhotoRequiresFileId(BaseRule):
    """photo media_type without file_id = empty screen for user.
    Pattern from TWIX TPL migration."""

    rule_id = "twix_photo_no_file_id"
    description = "Photo screen missing file_id"

    def check(self, screen: ScreenState, history: Optional[list] = None) -> Iterator[Issue]:
        if screen.media_type == "photo" and not screen.file_id:
            yield Issue(
                severity="critical",
                rule_id=self.rule_id,
                screen_fingerprint=screen.fingerprint(),
                detail="media_type='photo' but file_id is empty. User sees blank screen.",
            )


class EmptyTextWithNoMedia(BaseRule):
    """Screen with no text and no media is blank."""

    rule_id = "twix_empty_screen"
    description = "Screen has no text and no media"

    def check(self, screen: ScreenState, history: Optional[list] = None) -> Iterator[Issue]:
        if not screen.text.strip() and not screen.media_type and not screen.caption:
            yield Issue(
                severity="critical",
                rule_id=self.rule_id,
                screen_fingerprint=screen.fingerprint(),
                detail="Screen is completely blank (no text, no media, no caption).",
            )


class ResponseTimeUnderThreshold(BaseRule):
    """Warn if bot response is slower than expected (>5s suggests deadlock)."""

    rule_id = "twix_slow_response"
    description = "Bot response time exceeds threshold"

    THRESHOLD_MS = 5000.0

    def check(self, screen: ScreenState, history: Optional[list] = None) -> Iterator[Issue]:
        # This rule requires history data with response_ms; if not available, skip
        if not history:
            return
        for step in history:
            if hasattr(step, "response_ms") and step.response_ms > self.THRESHOLD_MS:
                yield Issue(
                    severity="warning",
                    rule_id=self.rule_id,
                    screen_fingerprint=screen.fingerprint(),
                    detail=f"Response took {step.response_ms:.0f}ms (threshold: {self.THRESHOLD_MS:.0f}ms). Possible deadlock or heavy DB query.",
                    response_ms=step.response_ms,
                )
