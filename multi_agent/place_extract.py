"""Tavily / web arama çıktısından geçerli mekan adları — liste başlıkları elenir."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

_TR_LOWER = str.maketrans("İIĞÜŞÖÇ", "iığüşöç")

# Tavily sonuçlarında hedef dışı şehir adı taşıyan mekanları elemek için
_BASKA_SEHIRLER = (
    "Ankara",
    "İstanbul",
    "Istanbul",
    "İzmir",
    "Izmir",
    "Bursa",
    "Adana",
    "Konya",
    "Gaziantep",
    "Mersin",
    "Kayseri",
    "Eskişehir",
    "Eskisehir",
    "Diyarbakır",
    "Diyarbakir",
    "Samsun",
    "Denizli",
    "Şanlıurfa",
    "Sanliurfa",
    "Trabzon",
    "Erzurum",
    "Malatya",
    "Manisa",
    "Balıkesir",
    "Balikesir",
    "Aydın",
    "Aydin",
    "Tekirdağ",
    "Tekirdag",
    "Muğla",
    "Mugla",
    "Mardin",
    "Antalya",
    "Van",
    "Batman",
    "Elazığ",
    "Elazig",
    "Sakarya",
    "Kocaeli",
    "Hatay",
    "Kahramanmaraş",
    "Kahramanmaras",
    "Rize",
    "Ordu",
    "Afyon",
    "Çanakkale",
    "Canakkale",
)

# Makale / liste başlığı kalıpları (gerçek işletme adı değil)
_KAYNAK_SONEK = re.compile(
    r"\s*[-–|]\s*"
    r"(tripadvisor|vikipedi|wikipedia|google\s*maps|apple\s*maps|facebook|instagram|"
    r"yelp|foursquare|yandex|oregano|2gis|zomato|"
    r"beldibi\s*[-–]?\s*tripadvisor|fast\s*food\.?)\s*$",
    re.I,
)
_KIRLI_PLATFORM = re.compile(r"(?i)\b(yandex|oregano|2gis|zomato)\b")
_OTEL_LISTE_KALIPI = re.compile(
    r"(?i)(\bhotels?\b|\bhotel\b|\bAKKA\b|\bresort\b|\baccommodation\b)"
)


def mekan_adi_temizle(ad: str) -> str:
    """Arama başlığındaki kaynak/SEO soneklerini kısaltır."""
    ad = (ad or "").strip()
    if not ad:
        return ""
    onceki = None
    while ad != onceki:
        onceki = ad
        ad = _KAYNAK_SONEK.sub("", ad).strip()
        ad = re.sub(r"\s*-\s*Tripadvisor\s*$", "", ad, flags=re.I).strip()
        ad = re.sub(r"\s*-\s*Beldi(?:bi)?\s*$", "", ad, flags=re.I).strip()
    return ad


_GENERIC_PATTERNS = re.compile(
    r"(?i)("
    r"\ben\s+iyi\b|\ben\s+popüler\b|\brestoranları\b|\brestoranlar\b|\bkafeler\b|"
    r"\bmekanları\b|\bmekanlar\b|\böneriler\b|\brehber\b|\bliste\b|"
    r"\btop\s*\d+\b|\bthe\s+\d+\s+best\b|\bbest\s+\d+\b|nereye\s+gidelim|nerede\s+yenir|"
    r"gezilecek|yapılacak|best\s+restaurants|'\s*nın\s+en\s+iyi|instagram|@\w+|"
    r"\bbelediyesi\b|\bbüyükşehir\b|"
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


def _norm_sehir(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().translate(_TR_LOWER).casefold())


def mekan_hedef_sehre_uygun(ad: str, hedef: str) -> bool:
    """Mekan adında hedef dışı bir şehir adı geçiyorsa False."""
    ad_n = _norm_sehir(ad)
    hedef_n = _norm_sehir(hedef)
    if not ad_n or not hedef_n:
        return True
    for sehir in _BASKA_SEHIRLER:
        sn = _norm_sehir(sehir)
        if not sn or sn == hedef_n:
            continue
        if re.search(rf"(?<![\wçğıöşü]){re.escape(sn)}(?![\wçğıöşü])", ad_n):
            return False
    return True


def gecerli_mekan_adi(ad: str) -> bool:
    ad = mekan_adi_temizle(ad)
    if len(ad) < 3 or len(ad) > 55:
        return False
    if _OTEL_LISTE_KALIPI.search(ad) and not re.search(
        r"(?i)(restaurant|restoran|cafe|kafe|bistro|lokanta|bar\s*&)",
        ad,
    ):
        return False
    if _GENERIC_PATTERNS.search(ad):
        return False
    if _KIRLI_PLATFORM.search(ad):
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
    ad = mekan_adi_temizle(ad)
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
