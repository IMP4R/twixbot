from __future__ import annotations

from decimal import Decimal

from tg_settings import DecimalCodec, TierCodec
from twix_runtime import runtime


def _coerce(key,value):
    codec=runtime().schema.get(key).codec
    if isinstance(codec,DecimalCodec) and not isinstance(value,Decimal):return Decimal(str(value))
    if isinstance(codec,TierCodec):return [{k:Decimal(str(v)) for k,v in item.items()} for item in value]
    return value


async def get(key):
    return runtime().settings.get(key)


def get_sync(key):
    return runtime().settings.get(key)


async def set(key,value):
    return await runtime().settings.set(key,_coerce(key,value))


async def reset(key):
    return await runtime().settings.reset(key)


async def get_all():
    return runtime().settings.snapshot()[1]


def on_change(hook):
    async def notify(change):await hook(change.key,change.old,change.new)
    return runtime().settings.on_change(notify)
