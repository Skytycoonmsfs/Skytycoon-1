# -*- coding: utf-8 -*-
"""Leichtgewichtige DE/EN-Übersetzung für SkyTycoon (News, Tickets, Marketing)."""
from __future__ import annotations

import re
from typing import Tuple

_DE_HINTS = re.compile(
    r"\b(und|der|die|das|nicht|für|mit|wird|sind|Pilot|Flotte|Update|News)\b",
    re.I,
)


def detect_lang(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return "de"
    de_score = len(_DE_HINTS.findall(raw))
    en_score = len(re.findall(r"\b(the|and|for|with|your|flight|update|news)\b", raw, re.I))
    if en_score > de_score + 1:
        return "en"
    if de_score >= en_score:
        return "de"
    return "en"


def _translate_via_deep(text: str, target: str) -> str:
    try:
        from deep_translator import GoogleTranslator  # type: ignore[import-untyped]

        return (GoogleTranslator(source="auto", target=target).translate(text) or "").strip()
    except Exception:
        return ""


def bilingual_pair(text: str) -> Tuple[str, str]:
    """Erkennt Sprache und liefert (message_de, message_en)."""
    src = (text or "").strip()[:12000]
    if not src:
        return "", ""
    lang = detect_lang(src)
    if lang == "de":
        de = src
        en = _translate_via_deep(src, "en") or src
    else:
        en = src
        de = _translate_via_deep(src, "de") or src
    return de[:12000], en[:12000]
