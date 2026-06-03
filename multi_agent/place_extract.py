"""Tavily / web arama çıktısından geçerli mekan adları — liste başlıkları elenir."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

# Makale / liste başlığı kalıpları (gerçek işletme adı değil)
_GENERIC_PATTERNS = re.compile(
    r"(?i)("
    r"\ben\s+iyi\b|\ben\s+popüler\b|\brestoranları\b|\brestoranlar\b|\bkafeler\b|"
    r"\bmekanları\b|\bmekanlar\b|\böneriler\b|\brehber\b|\bliste\b|"
    r"\btop\s*\d+\b|\bthe\s+\d+\s+best\b|\bbest\s+\d+\b|nereye\s+gidelim|nerede\s+yenir|"
    r"gezilecek|yapılacak|best\s+restaurants|'\s*nın\s+en\s+iyi|instagram|@\w+|"
    r"old\s+town\s*$|updated\s+20\d{2}|account\s+of\b|hakkında\s+bilmeniz|"
    r"lezzet\s+rotası|gastronomi\s+turizmi|you'll\s+want\s+to\s+visit|want\s+to\s+visit"
    r")"
)

# İçerikten işletme adı adayları (özel isim + mekan türü)
_NAME_IN_CONTENT = re.compile(
    r"[A-ZÇĞİÖŞÜ][\wçğıöşüÇĞİÖŞÜ'&\-\.]{2,35}"
    r"(?:\s+[A-ZÇĞİÖŞÜ][\wçğıöşüÇĞİÖŞÜ'&\-\.]{0,25}){0,2}"
    r"\s+(?:Restaurant|Restoran|Kebap|Cafe|Kafe|Bistro|Balık|Lokanta)",
    re.MULTILINE,
)


def gecerli_mekan_adi(ad: str) -> bool:
    ad = (ad or "").strip()
    if len(ad) < 3 or len(ad) > 55:
        return False
    if _GENERIC_PATTERNS.search(ad):
        return False
    if ad.count(",") >= 2:
        return False
    if "|" in ad:
        return False
    if re.search(r"https?://|\.com\b|\.tr\b", ad, re.I):
        return False
    if " - " in ad and len(ad) > 45:
        return False
    if "@" in ad:
        return False
    if ad.endswith((".", ":", "|")):
        return False
    if re.search(r"\(\s*updated\s+20\d{2}\s*\)", ad, re.I):
        return False
    kelime_sayisi = len(ad.split())
    if kelime_sayisi > 8:
        return False
    # Tamamı büyük harf uzun başlık (SEO listesi)
    if len(ad) > 35 and ad.upper() == ad:
        return False
    return True


def _normalize_results(raw: Any) -> list[dict]:
    if isinstance(raw, str):
        stripped = raw.strip()
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError:
            try:
                raw = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                return []
    if isinstance(raw, dict):
        return raw.get("results") or raw.get("data") or []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def _ekle(mekanlar: list[dict], ad: str, kaynak: str, content: str = "") -> None:
    ad = ad.strip()
    if not gecerli_mekan_adi(ad):
        return
    norm = ad.lower()
    if any(m["ad"].lower() == norm for m in mekanlar):
        return
    mekanlar.append({"ad": ad, "kaynak": kaynak, "butce_notu": "belirsiz", "kaynak_ozet": (content or "")[:200]})


def mekanlari_cikar(raw: Any, *, max_adet: int = 8) -> list[dict]:
    """Tavily ham sonucu veya formatlanmış metinden mekan listesi."""
    mekanlar: list[dict] = []
    for item in _normalize_results(raw):
        title = (item.get("title") or item.get("name") or "").strip()
        url = (item.get("url") or "").strip()
        content = (item.get("content") or item.get("snippet") or "").strip()
        if gecerli_mekan_adi(title):
            _ekle(mekanlar, title, url, content)
        for match in _NAME_IN_CONTENT.findall(content):
            _ekle(mekanlar, match.strip(), url, content)
        if len(mekanlar) >= max_adet:
            break

    # "1. Başlık\n   içerik" formatı (search_places_online metni)
    if isinstance(raw, str) and len(mekanlar) < max_adet:
        blocks = re.split(r"\n(?=\d+\.\s)", raw.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if not lines:
                continue
            first = re.sub(r"^\d+\.\s*", "", lines[0]).strip()
            url = ""
            body = ""
            for line in lines[1:]:
                if line.strip().lower().startswith("kaynak:"):
                    url = line.split(":", 1)[-1].strip()
                else:
                    body += line + " "
            if gecerli_mekan_adi(first):
                _ekle(mekanlar, first, url, body)
            for match in _NAME_IN_CONTENT.findall(body):
                _ekle(mekanlar, match.strip(), url, body)
            if len(mekanlar) >= max_adet:
                break

    return mekanlar[:max_adet]
