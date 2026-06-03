"""Keşif katmanı — kategori tabanlı mimari: mekanlar[] + aktiviteler[].

Kategoriler session_config / data/defaults/kesif_kategorileri.json'dan gelir;
ulaşım ve konaklama lojistikte kalır, JSON'da sabit alan değildir.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Literal

from multi_agent.place_extract import (
    gecerli_mekan_adi,
    mekan_adi_temizle,
    mekan_hedef_sehre_uygun,
    mekanlari_cikar,
)

AktiviteTur = Literal["plaj", "yemek", "gezi", "muzik"]

MAX_MEKAN_ARAMA_BASINA = 3
_PLAJ_ADI_SABIT = "Plaj/yüzme"
_RESTORAN_KALIPI = re.compile(
    r"(?i)(restaurant|restoran|kebap|balıkçı|balikci|lokanta|cafe|kafe|bistro|balik)"
)
_TARIH_MEKAN_KALIPI = re.compile(
    r"(?i)(müze|muze|kale|antik|anıt|anit|parkı|parki|köprü|koprü|cami|saray|harabe|kültür|kultur)"
)


def _gezi_mekan_kabul(mekan_ad: str) -> bool:
    """Gezi türünde salt restoran adlarını ele; tarihi/müze adayları kalsın."""
    ad = (mekan_ad or "").strip()
    if not ad:
        return False
    if _RESTORAN_KALIPI.search(ad) and not _TARIH_MEKAN_KALIPI.search(ad):
        return False
    return True


_TR_LOWER = str.maketrans("İIĞÜŞÖÇ", "iığüşöç")


def _norm(s: str) -> str:
    """Türkçe + tire varyantları için karşılaştırma anahtarı."""
    s = (s or "").strip().translate(_TR_LOWER)
    s = re.sub(r"[—–‐‑‒−\-]+", "-", s)
    return re.sub(r"\s+", " ", s.casefold())


def _tercih_eslesir(tercih: str, kategori: dict) -> bool:
    t = _norm(tercih)
    for anahtar in kategori.get("tercih_eslestir") or []:
        if _norm(anahtar) in t or t in _norm(anahtar):
            return True
    return False


def _aktivite_ad_uret(kategori: dict, mekan_ad: str) -> str:
    """Kategori şablonundan aktivite adı — mekan varsa oneki ile ayırt edilir."""
    tur = kategori.get("tur", "")
    oneki = (kategori.get("aktivite_ad_oneki") or kategori.get("aktivite_ad") or "").strip()
    mekan_ad = (mekan_ad or "").strip()

    if tur == "plaj":
        base = kategori.get("aktivite_ad") or _PLAJ_ADI_SABIT
        return f"{base} — {mekan_ad}" if mekan_ad else base

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


def kesif_sorgulari_ture_gore(sorgular: list[dict]) -> dict[str, list[dict]]:
    """Arama listesini keşif türüne göre gruplar (paralel uzman düğümleri için)."""
    gruplar: dict[str, list[dict]] = {}
    for item in sorgular:
        tur = item.get("tur") or item.get("kategori", {}).get("tur") or "gezi"
        gruplar.setdefault(tur, []).append(item)
    return gruplar


def beklenen_kesif_turleri(kategoriler: list[dict], profiller: list[dict]) -> list[str]:
    """Temel kategoriler + profil tercih eşleşmelerinden beklenen keşif türleri."""
    turler: list[str] = []
    seen: set[str] = set()
    for kat in kategoriler:
        if kat.get("etkin", True) is False:
            continue
        if kat.get("temel"):
            tur = (kat.get("tur") or "").strip()
            if tur and tur not in seen:
                turler.append(tur)
                seen.add(tur)
    for profil in profiller:
        for tercih in profil.get("tercihler") or []:
            tercih = (tercih or "").strip()
            if not tercih:
                continue
            for kat in kategoriler:
                if kat.get("etkin", True) is False:
                    continue
                if _tercih_eslesir(tercih, kat):
                    tur = (kat.get("tur") or "").strip()
                    if tur and tur not in seen:
                        turler.append(tur)
                        seen.add(tur)
                    break
    return turler


def tur_aktivite_sayisi(kesif_verisi: dict, tur: str) -> int:
    return sum(
        1
        for a in kesif_verisi.get("aktiviteler") or []
        if (a.get("tur") or "") == tur
    )


def eksik_turleri_hesapla(
    kesif_verisi: dict,
    kategoriler: list[dict],
    profiller: list[dict],
) -> list[str]:
    """Beklenen ama yeterli aktivitesi olmayan keşif türleri (programatik)."""
    beklenen = beklenen_kesif_turleri(kategoriler, profiller)
    return [t for t in beklenen if tur_aktivite_sayisi(kesif_verisi, t) < 1]


def kesif_hedefli_guncelle(
    mevcut: dict[str, Any],
    yeni_partials: list[dict],
    hedef: str,
    profiller: list[dict],
    kategoriler: list[dict],
    hava: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Hedefli keşif sonrası mevcut kesif_verisi ile yeni partial'ları birleştirir."""
    plaj_mekan = any(
        (a.get("tur") == "plaj" and (a.get("mekan") or "").strip())
        for a in mevcut.get("aktiviteler") or []
    )
    mevcut_partial = {
        "mekanlar": list(mevcut.get("mekanlar") or []),
        "aktiviteler": list(mevcut.get("aktiviteler") or []),
        "plaj_mekan_bulundu": plaj_mekan,
        "arama_sayisi": 0,
    }
    hava_kullan = mevcut.get("hava") or hava
    return kesif_partial_birlestir(
        hedef, profiller, kategoriler, [mevcut_partial, *yeni_partials], hava_kullan
    )


def kesif_tur_calistir(
    hedef: str,
    tur: str,
    sorgular: list[dict],
    *,
    mekan_ara_fn: Callable[[str], str],
) -> dict[str, Any]:
    """Tek keşif türü (plaj/yemek/muzik/gezi) için bağımsız uzman çalışması."""
    mekanlar: list[dict] = []
    aktiviteler: list[dict] = []
    aktivite_seen: set[str] = set()
    uyarilar: list[str] = []
    plaj_mekan_bulundu = False

    for item in sorgular:
        kategori = item["kategori"]
        raw = mekan_ara_fn(item["sorgu"])
        bulunan, uyari = _mekan_payload_coz(raw, hedef)
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
                if tur == "gezi" and not _gezi_mekan_kabul(mekan_ad):
                    continue
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

    return {
        "tur": tur,
        "mekanlar": mekanlar,
        "aktiviteler": aktiviteler,
        "uyarilar": uyarilar,
        "plaj_mekan_bulundu": plaj_mekan_bulundu,
        "arama_sayisi": len(sorgular),
    }


def kesif_partial_birlestir(
    hedef: str,
    profiller: list[dict],
    kategoriler: list[dict],
    partials: list[dict],
    hava: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Paralel uzman çıktılarını dedupe + plaj fallback ile nihai kesif_verisi yapar."""
    mekanlar: list[dict] = []
    aktiviteler: list[dict] = []
    aktivite_seen: set[str] = set()
    mekan_tur_seen: set[str] = set()
    uyarilar: list[str] = []
    plaj_mekan_bulundu = False
    arama_sayisi = 0

    for p in partials:
        _mekan_birlestir(mekanlar, p.get("mekanlar") or [])
        for a in p.get("aktiviteler") or []:
            tur = a.get("tur", "gezi")
            ad = (a.get("ad") or "").strip()
            mekan = (a.get("mekan") or "").strip()
            if mekan:
                tur_mekan = f"{tur}|{_norm(mekan)}"
                if tur_mekan in mekan_tur_seen:
                    continue
                mekan_tur_seen.add(tur_mekan)
            key = f"{tur}|{_norm(ad)}|{_norm(mekan)}"
            if key in aktivite_seen:
                continue
            aktivite_seen.add(key)
            aktiviteler.append(a)
        for u in p.get("uyarilar") or []:
            if u:
                uyarilar.append(u)
        if p.get("plaj_mekan_bulundu"):
            plaj_mekan_bulundu = True
        arama_sayisi += int(p.get("arama_sayisi") or 0)

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
        "hedef_sehir": hedef,
        "mekanlar": mekanlar,
        "aktiviteler": aktiviteler,
        "tercih_ozeti": _tercih_ozeti(profiller),
        "kategori_ozeti": [{"id": k.get("id"), "tur": k.get("tur")} for k in kategoriler],
        "arama_sayisi": arama_sayisi,
        "uyari": "; ".join(dict.fromkeys(u for u in uyarilar if u)),
    }

    if not aktiviteler and not mekanlar:
        return kesif_verisi, kesif_verisi["uyari"] or "Keşif: doğrulanmış mekan/aktivite listesi boş."
    if len(aktiviteler) < 2 and len(mekanlar) < 2:
        return kesif_verisi, "Keşif: yeterli mekan veya aktivite bulunamadı."
    return kesif_verisi, ""


def _mekan_payload_coz(raw: Any, hedef: str = "") -> tuple[list[dict], str]:
    mekanlar: list[dict] = []
    uyari = ""
    try:
        payload = json.loads(str(raw))
        if isinstance(payload, dict):
            mekanlar = list(payload.get("mekanlar") or [])
            uyari = payload.get("uyari") or ""
    except json.JSONDecodeError:
        mekanlar = mekanlari_cikar(raw)

    temiz: list[dict] = []
    for m in mekanlar:
        ad = mekan_adi_temizle(m.get("ad", ""))
        if gecerli_mekan_adi(ad) and mekan_hedef_sehre_uygun(ad, hedef):
            temiz.append({**m, "ad": ad})
    mekanlar = temiz
    if len(mekanlar) < 1:
        ek = mekanlari_cikar(raw)
        seen = {_norm(m["ad"]) for m in mekanlar}
        for m in ek:
            ad = mekan_adi_temizle(m.get("ad", ""))
            if _norm(ad) in seen:
                continue
            if gecerli_mekan_adi(ad) and mekan_hedef_sehre_uygun(ad, hedef):
                mekanlar.append({**m, "ad": ad})
                seen.add(_norm(ad))
    return mekanlar[:MAX_MEKAN_ARAMA_BASINA], uyari


def _mekan_birlestir(hedef: list[dict], yeni: list[dict]) -> None:
    seen = {_norm(m["ad"]) for m in hedef}
    for m in yeni:
        ad = mekan_adi_temizle(m.get("ad") or "")
        if ad and _norm(ad) not in seen:
            hedef.append({**m, "ad": ad})
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
    gruplar = kesif_sorgulari_ture_gore(sorgular)
    partials = [
        kesif_tur_calistir(hedef, tur, items, mekan_ara_fn=mekan_ara_fn)
        for tur, items in gruplar.items()
    ]
    return kesif_partial_birlestir(hedef, profiller, kategoriler, partials, hava)


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


def mekan_eslesir(plan_mekan: str, kesif_mekan: str) -> bool:
    """Plan metnindeki mekan adı ile keşif kaydı (kısaltma / kaynak soneki toleransı)."""
    p = _norm(plan_mekan)
    k = _norm(kesif_mekan)
    if not p or not k:
        return False
    if p == k or p in k or k in p:
        return True
    k_t = _norm(mekan_adi_temizle(kesif_mekan))
    p_t = _norm(mekan_adi_temizle(plan_mekan))
    return p_t == k_t or p_t in k_t or k_t in p_t


def mekan_kesifte_var(plan_mekan: str, kesif_verisi: dict) -> bool:
    m = (plan_mekan or "").strip()
    if not m or _norm(m) in {"", "yok"}:
        return False
    for kayit in kesif_verisi.get("mekanlar") or []:
        if mekan_eslesir(m, kayit.get("ad") or ""):
            return True
    for a in kesif_verisi.get("aktiviteler") or []:
        if mekan_eslesir(m, a.get("mekan") or "") or mekan_eslesir(m, a.get("ad") or ""):
            return True
    return False


def gecerli_mekan_degerleri(kesif_verisi: dict) -> set[str]:
    izinli: set[str] = set()
    for m in kesif_verisi.get("mekanlar") or []:
        ad = mekan_adi_temizle(m.get("ad") or "")
        if ad:
            izinli.add(_norm(ad))
    for a in kesif_verisi.get("aktiviteler") or []:
        for alan in (a.get("mekan"), a.get("ad")):
            ad = mekan_adi_temizle(alan or "")
            if ad:
                izinli.add(_norm(ad))
    return izinli


def gecerli_aktivite_adlari(kesif_verisi: dict) -> set[str]:
    return {_norm(a.get("ad", "")) for a in (kesif_verisi.get("aktiviteler") or []) if a.get("ad")}


def aktivite_bul(
    kesif_verisi: dict,
    etkinlik: str,
    plan_mekan: str | None = None,
) -> dict | None:
    """Plan satırındaki etkinlik adını keşif aktivitesi kaydına bağlar."""
    et = _norm(etkinlik)
    if not et:
        return None
    eslesen = [
        a
        for a in kesif_verisi.get("aktiviteler") or []
        if _norm(a.get("ad") or "") == et
    ]
    if not eslesen:
        return None
    if len(eslesen) == 1:
        return eslesen[0]

    plan = (plan_mekan or "").strip()
    plan_n = _norm(plan)
    if plan_n not in {"", "yok"}:
        for a in eslesen:
            if mekan_eslesir(plan, a.get("mekan") or ""):
                return a

    for a in eslesen:
        if (a.get("mekan") or "").strip():
            return a
    return eslesen[0]


def mekan_satir_uygun(aktivite: dict, plan_mekan: str | None, kesif_verisi: dict) -> bool:
    """Kategori/aktivite meta verisine göre (mekan_zorunlu + keşifteki mekan alanı)."""
    plan = (plan_mekan or "").strip()
    plan_n = _norm(plan)
    kesif_mk = (aktivite.get("mekan") or "").strip()
    zorunlu = bool(aktivite.get("mekan_zorunlu", True))

    if plan_n in {"", "yok"}:
        return not zorunlu

    if kesif_mk:
        return mekan_eslesir(plan, kesif_mk)
    return mekan_kesifte_var(plan, kesif_verisi)
