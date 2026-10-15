# tpl/tree.py
"""Дерево шаблонов: иерархические ключи, конвенции callback_data, утилиты группировки."""

from __future__ import annotations

import re
from collections import defaultdict

SEPARATOR = "."
CALLBACK_SEP = "_"


def normalize_key(key: str) -> str:
    """Привести ключ к стандартному виду: строчные, точка как разделитель."""
    key = key.strip().lower()
    key = key.replace(" ", SEPARATOR)
    key = re.sub(r"[\\/]+", SEPARATOR, key)
    return key


def key_to_callback(key: str) -> str:
    """main.profile.balance -> main_profile_balance."""
    return key.replace(SEPARATOR, CALLBACK_SEP)


def callback_to_key(callback: str) -> str:
    """main_profile_balance -> main.profile.balance.
    Сохраняет переменные внутри [id]: main_profile_[id] -> main.profile.[id]."""
    # Сначала защитим плейсхолдеры [...]
    placeholders: list[str] = []
    def _store_ph(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"§PH{len(placeholders)-1}§"
    temp = re.sub(r"\[[^\]]+]", _store_ph, callback)
    # Заменяем оставшиеся _ на .
    temp = temp.replace(CALLBACK_SEP, SEPARATOR)
    # Восстанавливаем [...]
    for i, ph in enumerate(placeholders):
        temp = temp.replace(f"§PH{i}§", ph)
    return temp


def split_key(key: str) -> list[str]:
    """main.profile.balance -> ['main', 'profile', 'balance']."""
    return key.split(SEPARATOR)


def parent_key(key: str) -> str | None:
    """main.profile.balance -> main.profile."""
    if SEPARATOR not in key:
        return None
    return key.rsplit(SEPARATOR, 1)[0]


def key_depth(key: str) -> int:
    return len(split_key(key))


def build_tree(keys: list[str]) -> dict:
    """Построить вложенный dict из списка ключей.
    {'main': {'profile': {'balance': {}, 'referral': {}}}}"""
    tree: dict = {}
    for key in keys:
        parts = split_key(key)
        node = tree
        for part in parts:
            node = node.setdefault(part, {})
    return tree


def group_by_prefix(keys: list[str], depth: int = 1) -> dict[str, list[str]]:
    """Сгруппировать ключи по префиксу на заданной глубине.
    group_by_prefix(['main.profile', 'main.balance', 'admin.stats'], 1)
    -> {'main': ['main.profile', 'main.balance'], 'admin': ['admin.stats']}"""
    groups: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        parts = split_key(key)
        prefix = SEPARATOR.join(parts[:depth]) if len(parts) >= depth else key
        groups[prefix].append(key)
    return dict(groups)


def list_children(keys: list[str], prefix: str) -> list[str]:
    """Все ключи, непосредственно вложенные в prefix (на 1 уровень глубже)."""
    prefix_parts = split_key(prefix)
    plen = len(prefix_parts)
    result = []
    seen = set()
    for key in keys:
        parts = split_key(key)
        if len(parts) == plen + 1 and parts[:plen] == prefix_parts:
            child = parts[plen]
            if child not in seen:
                seen.add(child)
                result.append(child)
    return sorted(result)


def get_tree_nodes(keys: list[str], prefix: str | None = None) -> tuple[list[str], list[str]]:
    """Разделить ключи на папки и листья относительно prefix.
    Возвращает (folders, leaves).
    prefix=None -> корень дерева.
    """
    if prefix:
        prefix_parts = split_key(prefix)
        plen = len(prefix_parts)
    else:
        prefix_parts = []
        plen = 0

    folders: set[str] = set()
    leaves: list[str] = []

    for key in keys:
        parts = split_key(key)
        if plen == 0:
            if len(parts) == 1:
                leaves.append(key)
            elif len(parts) > 1:
                folders.add(parts[0])
            continue

        # prefix задан
        if len(parts) <= plen or parts[:plen] != prefix_parts:
            continue
        if len(parts) == plen + 1:
            leaves.append(key)
        else:
            folders.add(parts[plen])

    return sorted(folders), sorted(leaves)


def is_in_namespace(key: str, namespace: str) -> bool:
    """Проверить, что ключ находится внутри namespace."""
    return key == namespace or key.startswith(namespace + SEPARATOR)
