"""Plan satırı doğrulama — lojistik muaf; keşif kuralları aktivite meta verisinden gelir."""

from __future__ import annotations

import re

from multi_agent.kesif_layer import _norm, aktivite_bul, mekan_satir_uygun
from multi_agent.place_extract import mekan_hedef_sehre_uygun

_LOJISTIK_ANAHTARLAR = re.compile(
    r"(?i)(yola\s*çıkış|yol\s*çıkış|varış|varis|otelde|bekleme|dinlenme|uyku|toplanma|ulaşım|ulasim|bilet|sefer|konaklama)",
)
_KESIF_SATIR = re.compile(r"\(Mekan:\s*[^)]+\)", re.I)
_ZAMAN_ARALIK = re.compile(r"\d{2}:\d{2}-\d{2}:\d{2}\s*\|")
_UYDURMA_ETIKET = re.compile(
    r"(?i)^(yürüyüş|yuruyus|yemek|brunch|kahve|serbest|öğle\s*yemeği|akşam\s*yemeği)\s*([—\-]|$)"
)


def satir_canoniklestir(ham: str) -> str | None:
    """Markdown/bullet öneklerini atıp 'HH:MM-HH:MM | ...' biçimine indirger."""
    ln = (ham or "").strip()
    if not ln or ln.startswith("#"):
        return None
    ln = re.sub(r"^[-*•]\s+", "", ln)
    ln = re.sub(r"\*\*(Lojistik|Keşif|Loğistik|Kesif)\*\*\s*:\s*", r"\1: ", ln, flags=re.I)
    # LLM revizyonunda sık: - **11:30-12:30** | ...
    ln = re.sub(r"\*\*(\d{2}:\d{2}-\d{2}:\d{2})\*\*", r"\1", ln)
    m = _ZAMAN_ARALIK.search(ln)
    if not m:
        return None
    return ln[m.start() :].strip()


def plan_satirlari(metin: str) -> list[str]:
    out: list[str] = []
    for ln in metin.splitlines():
        canon = satir_canoniklestir(ln)
        if canon:
            out.append(canon)
    return out


def kesif_satir_mi(satir: str) -> bool:
    if re.search(r"Dayanak:\s*lojistik", satir, re.I):
        return False
    govde = satir.split("|", 1)[-1] if "|" in satir else satir
    if re.match(r"\s*yok\s*\|", govde, re.I):
        return False
    if _LOJISTIK_ANAHTARLAR.search(govde):
        if not _KESIF_SATIR.search(satir):
            return False
    return bool(_KESIF_SATIR.search(satir)) or bool(
        re.search(r"Dayanak:\s*k[eşs]if", satir, re.I)
    )


def satir_etkinlik_adi(satir: str) -> str:
    m = re.match(
        r"\d{2}:\d{2}-\d{2}:\d{2}\s*\|\s*(.+?)(?:\s*\(Mekan:|\s*\|\s*Dayanak:|\s*$)",
        satir,
        re.I,
    )
    return m.group(1).strip() if m else ""


def satir_mekan_degeri(satir: str) -> str | None:
    m = re.search(r"Mekan:\s*([^)|\n]+)", satir, re.I)
    return m.group(1).strip() if m else None


def uydurma_etiket_mi(etkinlik: str, kesif_verisi: dict) -> bool:
    """Keşif listesinde yoksa ve kısa/genel etiket ise."""
    if aktivite_bul(kesif_verisi, etkinlik):
        return False
    et = (etkinlik or "").strip()
    if not et:
        return True
    if _UYDURMA_ETIKET.match(et):
        return True
    return _norm(et) in {"yürüyüş", "yuruyus", "yemek", "brunch", "kahve", "serbest", "yok"}


def kesif_satir_dogrula(satir: str, kesif_verisi: dict) -> tuple[bool, str]:
    """(geçerli, hata_turu) — hata_turu: aktivite | mekan | mekan_sehir | bos."""
    etkinlik = satir_etkinlik_adi(satir)
    mekan = satir_mekan_degeri(satir)
    hedef = (kesif_verisi.get("hedef_sehir") or "").strip()
    if not etkinlik:
        return False, "bos"
    aktivite = aktivite_bul(kesif_verisi, etkinlik, plan_mekan=mekan)
    if not aktivite:
        return False, "aktivite"
    if mekan and hedef and not mekan_hedef_sehre_uygun(mekan, hedef):
        return False, "mekan_sehir"
    if not mekan_satir_uygun(aktivite, mekan, kesif_verisi):
        return False, "mekan"
    return True, ""
