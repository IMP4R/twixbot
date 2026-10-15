# tpl/middleware.py
"""Aiogram middleware для автоматической подстановки locale в handler data."""

from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from tpl.locale import get_user_locale


class TplI18nMiddleware(BaseMiddleware):
    """Кладёт ключ 'locale' в data на основе user_id.
    Работает с Message и CallbackQuery."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id

        if user_id and "locale" not in data:
            data["locale"] = await get_user_locale(user_id)

        return await handler(event, data)
