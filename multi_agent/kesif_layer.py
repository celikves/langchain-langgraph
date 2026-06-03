"""Keşif katmanı — kategori tabanlı mimari: mekanlar[] + aktiviteler[].

Kategoriler session_config / data/defaults/kesif_kategorileri.json'dan gelir;
ulaşım ve konaklama lojistikte kalır, JSON'da sabit alan değildir.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Literal

from multi_agent.place_extract import gecerli_mekan_adi, mekanlari_cikar

AktiviteTur = Literal["plaj", "yemek", "gezi", "muzik"]

MAX_MEKAN_ARAMA_BASINA = 3
_PLAJ_ADI_SABIT = "Plaj/yüzme"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _tercih_eslesir(tercih: str, kategori: dict) -> bool:
    t = _norm(tercih)
    for anahtar in kategori.get("tercih_eslestir") or []:
        if _norm(anahtar) in t or t in _norm(anahtar):
            return True
    return False


def _aktivite_ad_uret(kategori: dict, mekan_ad: str) -> str:
    tur = kategori.get("tur", "")
    if tur == "plaj":
        return kategori.get("aktivite_ad") or _PLAJ_ADI_SABIT
    oneki = (kategori.get("aktivite_ad_oneki") or "").strip()
    if oneki and mekan_ad:
        return f"{oneki} — {mekan_ad}"
    if oneki:
        return oneki
    return mekan_ad


def kesif_sorgulari_uret(
    hedef: str,
    profiller: list[dict],
    kategoriler: list[dict],
) -> list[dict]:
    """Temel kategoriler + profil tercih eşleşmeleri → deterministik arama listesi."""
    sorgular: list[dict] = []
    seen_sorgu: set[str] = set()

    def _ekle(kategori: dict, tercih_sahibi: str = "", tercih_etiketi: str = "") -> None:
        if tercih_etiketi and kategori.get("tercih_sorgu_sablonu"):
            sorgu = kategori["tercih_sorgu_sablonu"].replace("{hedef}", hedef).replace("{tercih}", tercih_etiketi).strip()
        else:
            sablon = (kategori.get("sorgu_sablonu") or "").strip()
            if not sablon:
                return
            sorgu = sablon.replace("{hedef}", hedef).replace("{tercih}", tercih_etiketi).strip()
        key = _norm(sorgu)
        if key in seen_sorgu:
            return
        seen_sorgu.add(key)
        sorgular.append(
            {
                "kategori_id": kategori.get("id", ""),
                "tur": kategori.get("tur", "gezi"),
                "sorgu": sorgu,
                "kategori": kategori,
                "tercih_sahibi": tercih_sahibi,
                "tercih_etiketi": tercih_etiketi,
            }
        )

    for kat in kategoriler:
        if kat.get("temel"):
            _ekle(kat)

    for profil in profiller:
        isim = (profil.get("isim") or "").strip()
        for tercih in profil.get("tercihler") or []:
            tercih = (tercih or "").strip()
            if not tercih:
                continue
            for kat in kategoriler:
                if _tercih_eslesir(tercih, kat):
                    _ekle(kat, tercih_sahibi=isim, tercih_etiketi=tercih)
                    break

    return sorgular


def _mekan_payload_coz(raw: Any) -> tuple[list[dict], str]:
    mekanlar: list[dict] = []
    uyari = ""
    try:
        payload = json.loads(str(raw))
        if isinstance(payload, dict):
            mekanlar = list(payload.get("mekanlar") or [])
            uyari = payload.get("uyari") or ""
    except json.JSONDecodeError:
        mekanlar = mekanlari_cikar(raw)

    mekanlar = [m for m in mekanlar if gecerli_mekan_adi(m.get("ad", ""))]
    if len(mekanlar) < 1:
        ek = mekanlari_cikar(raw)
        seen = {_norm(m["ad"]) for m in mekanlar}
        for m in ek:
            if _norm(m["ad"]) not in seen:
                mekanlar.append(m)
                seen.add(_norm(m["ad"]))
    return mekanlar[:MAX_MEKAN_ARAMA_BASINA], uyari


def _mekan_birlestir(hedef: list[dict], yeni: list[dict]) -> None:
    seen = {_norm(m["ad"]) for m in hedef}
    for m in yeni:
        ad = (m.get("ad") or "").strip()
        if ad and _norm(ad) not in seen:
            hedef.append(m)
            seen.add(_norm(ad))


def _aktivite_ekle(
    aktiviteler: list[dict],
    seen: set[str],
    *,
    kategori: dict,
    ad: str,
    mekan: str = "",
    tercih_sahibi: str = "",
    tercih_etiketi: str = "",
    kaynak: str = "",
) -> None:
    ad = (ad or "").strip()
    mekan = (mekan or "").strip()
    tur = kategori.get("tur", "gezi")
    if not ad:
        return
    if kategori.get("mekan_zorunlu", True) and not mekan:
        return
    key = f"{tur}|{_norm(ad)}|{_norm(mekan)}"
    if key in seen:
        return
    seen.add(key)
    sure = int(kategori.get("sure_dakika") or 60)
    aktiviteler.append(
        {
            "tur": tur,
            "ad": ad,
            "sure_dakika": sure,
            "mekan": mekan,
            "mekan_zorunlu": bool(kategori.get("mekan_zorunlu", True)),
            "tercih_sahibi": tercih_sahibi,
            "tercih_etiketi": tercih_etiketi,
            "kaynak": kaynak,
            "kategori_id": kategori.get("id", ""),
        }
    )


def kesif_verisi_topla(
    hedef: str,
    hedef_tarih: str,
    profiller: list[dict],
    kategoriler: list[dict],
    *,
    hava_fn: Callable[[str, str], str],
    mekan_ara_fn: Callable[[str], str],
) -> tuple[dict[str, Any], str]:
    hava_raw = hava_fn(hedef, hedef_tarih)
    hava = _extract_weather_fields(str(hava_raw))

    sorgular = kesif_sorgulari_uret(hedef, profiller, kategoriler)
    mekanlar: list[dict] = []
    aktiviteler: list[dict] = []
    aktivite_seen: set[str] = set()
    uyarilar: list[str] = []
    plaj_mekan_bulundu = False

    for item in sorgular:
        kategori = item["kategori"]
        tur = kategori.get("tur", "gezi")
        raw = mekan_ara_fn(item["sorgu"])
        bulunan, uyari = _mekan_payload_coz(raw)
        if uyari:
            uyarilar.append(uyari)
        _mekan_birlestir(mekanlar, bulunan)

        if tur == "plaj":
            if bulunan:
                plaj_mekan_bulundu = True
                for m in bulunan:
                    _aktivite_ekle(
                        aktiviteler,
                        aktivite_seen,
                        kategori=kategori,
                        ad=_aktivite_ad_uret(kategori, m.get("ad", "")),
                        mekan=(m.get("ad") or "").strip(),
                        tercih_sahibi=item.get("tercih_sahibi", ""),
                        tercih_etiketi=item.get("tercih_etiketi", ""),
                        kaynak=(m.get("kaynak") or ""),
                    )
        else:
            for m in bulunan:
                mekan_ad = (m.get("ad") or "").strip()
                _aktivite_ekle(
                    aktiviteler,
                    aktivite_seen,
                    kategori=kategori,
                    ad=_aktivite_ad_uret(kategori, mekan_ad),
                    mekan=mekan_ad,
                    tercih_sahibi=item.get("tercih_sahibi", ""),
                    tercih_etiketi=item.get("tercih_etiketi", ""),
                    kaynak=(m.get("kaynak") or ""),
                )

    if not plaj_mekan_bulundu:
        plaj_kat = next((k for k in kategoriler if k.get("tur") == "plaj"), None)
        if plaj_kat:
            _aktivite_ekle(
                aktiviteler,
                aktivite_seen,
                kategori=plaj_kat,
                ad=_aktivite_ad_uret(plaj_kat, ""),
                mekan="",
                tercih_etiketi="plaj",
            )

    kesif_verisi = {
        "hava": hava,
        "mekanlar": mekanlar,
        "aktiviteler": aktiviteler,
        "tercih_ozeti": _tercih_ozeti(profiller),
        "kategori_ozeti": [{"id": k.get("id"), "tur": k.get("tur")} for k in kategoriler],
        "arama_sayisi": len(sorgular),
        "uyari": "; ".join(dict.fromkeys(u for u in uyarilar if u)),
    }

    if not aktiviteler and not mekanlar:
        return kesif_verisi, kesif_verisi["uyari"] or "Keşif: doğrulanmış mekan/aktivite listesi boş."
    if len(aktiviteler) < 2 and len(mekanlar) < 2:
        return kesif_verisi, "Keşif: yeterli mekan veya aktivite bulunamadı."
    return kesif_verisi, ""


def _tercih_ozeti(profiller: list[dict]) -> list[dict]:
    return [
        {
            "isim": (p.get("isim") or "").strip(),
            "tercihler": [t.strip() for t in (p.get("tercihler") or []) if (t or "").strip()],
        }
        for p in profiller
        if (p.get("isim") or "").strip()
    ]


def _extract_weather_fields(weather_text: str) -> dict:
    sicaklik_match = re.search(r"(\d+(?:[.,]\d+)?)°C", weather_text)
    yagis_match = re.search(r"Yağış ihtimali:\s*%?(\d+)", weather_text, flags=re.IGNORECASE)
    return {
        "ham_metin": weather_text,
        "sicaklik_c": sicaklik_match.group(1) if sicaklik_match else "",
        "yagis_ihtimali_yuzde": yagis_match.group(1) if yagis_match else "",
    }


def gecerli_mekan_degerleri(kesif_verisi: dict) -> set[str]:
    izinli: set[str] = set()
    for m in kesif_verisi.get("mekanlar") or []:
        ad = (m.get("ad") or "").strip()
        if ad:
            izinli.add(_norm(ad))
    for a in kesif_verisi.get("aktiviteler") or []:
        mekan = (a.get("mekan") or "").strip()
        if mekan:
            izinli.add(_norm(mekan))
    return izinli


def gecerli_aktivite_adlari(kesif_verisi: dict) -> set[str]:
    return {_norm(a.get("ad", "")) for a in (kesif_verisi.get("aktiviteler") or []) if a.get("ad")}


def plaj_mekan_yok_kabul(kesif_verisi: dict) -> bool:
    return any(
        a.get("tur") == "plaj" and not (a.get("mekan") or "").strip()
        for a in (kesif_verisi.get("aktiviteler") or [])
    )


def mekan_yok_satir_izinli(etkinlik: str, kesif_verisi: dict) -> bool:
    """Mekan: yok yalnızca plaj aktivitesi için geçerli."""
    et = _norm(etkinlik)
    if _PLAJ_ADI_SABIT.lower() in et:
        return plaj_mekan_yok_kabul(kesif_verisi)
    return False
