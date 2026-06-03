"""Plan satırı doğrulama — lojistik muaf, keşif satırları aktivite/mekan kurallarına tabi."""

from __future__ import annotations

import re

_LOJISTIK_ANAHTARLAR = re.compile(
    r"(?i)(yola\s*çıkış|yol\s*çıkış|varış|varis|otelde|bekleme|dinlenme|uyku|toplanma|ulaşım|ulasim|bilet|sefer|konaklama)",
)
_KESIF_SATIR = re.compile(r"\(Mekan:\s*[^)]+\)", re.I)
_PLAN_SATIR = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}\s*\|")


def plan_satirlari(metin: str) -> list[str]:
    return [ln.strip() for ln in metin.splitlines() if _PLAN_SATIR.match(ln.strip())]


def kesif_satir_mi(satir: str) -> bool:
    if re.search(r"Dayanak:\s*lojistik", satir, re.I):
        return False
    if _LOJISTIK_ANAHTARLAR.search(satir.split("|", 1)[-1] if "|" in satir else satir):
        if not _KESIF_SATIR.search(satir):
            return False
    return bool(_KESIF_SATIR.search(satir)) or bool(
        re.search(r"Dayanak:\s*kesif", satir, re.I)
    )


def satir_etkinlik_adi(satir: str) -> str:
    m = re.match(r"\d{2}:\d{2}-\d{2}:\d{2}\s*\|\s*([^|(]+)", satir)
    return m.group(1).strip() if m else ""


def satir_mekan_degeri(satir: str) -> str | None:
    m = re.search(r"Mekan:\s*([^)|\n]+)", satir, re.I)
    return m.group(1).strip() if m else None


def etkinlik_kesifte_var(etkinlik: str, norm_aktivite_adlari: set[str]) -> bool:
    et = re.sub(r"\s+", " ", etkinlik.strip().lower())
    if not et:
        return True
    for ad in norm_aktivite_adlari:
        if not ad:
            continue
        if ad == et or ad in et or et in ad:
            return True
    return False
