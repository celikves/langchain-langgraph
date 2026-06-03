"""Lojistik planı — N kişi × trafik/bilet araçları; statik süre yok."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable


def profillerden_katilimci(profiller: list[dict]) -> list[dict]:
    return [
        {
            "isim": p.get("isim", ""),
            "kalkis_sehri": (p.get("kalkis_yeri") or p.get("sehir") or "").strip(),
            "butce": p.get("butce", ""),
        }
        for p in profiller
        if p.get("isim")
    ]


def _saat_metin(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _mesai_cikis_zamani(profil: dict, referans: datetime) -> datetime | None:
    mesai = profil.get("mesai")
    if not isinstance(mesai, dict):
        return None
    bitis = mesai.get("bitis")
    if not bitis:
        return None
    try:
        t = datetime.strptime(bitis, "%H:%M").time()
    except ValueError:
        return None
    return referans.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


def _cikis_zamani(profil: dict, slot_baslangic: datetime) -> datetime:
    """Kişisel çıkış: mesai bitişi varsa onu kullan; yoksa ortak slot başlangıcı."""
    mesai_cikis = _mesai_cikis_zamani(profil, slot_baslangic)
    if mesai_cikis is not None:
        return mesai_cikis
    return slot_baslangic


def _parse_trafik_payload(ham: str | dict) -> dict:
    if isinstance(ham, dict):
        return ham
    try:
        return json.loads(ham)
    except json.JSONDecodeError:
        return {"hata": f"Trafik aracı JSON döndürmedi: {ham}"}


def _parse_bilet_payload(ham: str | dict) -> dict:
    if isinstance(ham, dict):
        return ham
    try:
        return json.loads(ham)
    except json.JSONDecodeError:
        return {"hata": f"Bilet aracı JSON döndürmedi: {ham}", "secenekler": []}


def _gece_otel_ve_ilk_aktivite(
    en_gec_varis: datetime,
    ilk_slot: dict,
    tum_slotlar: list[dict],
) -> tuple[datetime, datetime, datetime, str]:
    """
    Gece varışta: otelde dinlenme penceresi + takvimdeki ilk uygun DIŞ ortak slot.
    Cuma 18:00–23:00 slotu yola çıkış içindir; gece 01:00–03:00 varışları bu slota sığmaz.
    """
    slot_end = datetime.fromisoformat(ilk_slot["bitis"])

    # Gündüz/akşam hepsi yetişti → aynı gün aktivite
    if en_gec_varis <= slot_end and en_gec_varis.hour >= 17:
        return en_gec_varis, en_gec_varis, en_gec_varis, "aksam_aynı_gece"

    # Gece varış: en az 6 saat otel dinlenmesi, sonra takvimdeki ilk ortak slot
    gece_bas = en_gec_varis
    sabah_taban = en_gec_varis.replace(hour=9, minute=0, second=0, microsecond=0)
    dinlenme_bitis = max(en_gec_varis + timedelta(hours=6), sabah_taban)

    for slot in tum_slotlar:
        start = datetime.fromisoformat(slot["baslangic"])
        if start >= dinlenme_bitis:
            return gece_bas, dinlenme_bitis, start, "gece_otel_sonraki_takvim_slotu"

    fallback = dinlenme_bitis + timedelta(hours=2)
    return gece_bas, dinlenme_bitis, fallback, "gece_otel_minimum_dinlenme"


def _erken_gelen_aksiyonlari(
    varislar: list[tuple[str, datetime]],
    en_gec_isim: str,
    en_gec_dt: datetime,
    hedef_sehir: str,
) -> list[dict]:
    aksiyonlar: list[dict] = []
    for isim, varis in sorted(varislar, key=lambda x: x[1]):
        if varis >= en_gec_dt:
            continue
        bekleme_dk = int((en_gec_dt - varis).total_seconds() // 60)
        aksiyonlar.append(
            {
                "isim": isim,
                "tahmini_varis_saat_metin": _saat_metin(varis),
                "tahmini_varis_saati": varis.isoformat(),
                "bekleme_bitis_saat_metin": _saat_metin(en_gec_dt),
                "bekleme_suresi_dakika": bekleme_dk,
                "bulusma_noktasi": f"{hedef_sehir} (otel lobisi / oda hazırlığı)",
                "aksiyon": (
                    f"Otelde toplanma ve dinlenme — {en_gec_isim} "
                    f"({_saat_metin(en_gec_dt)}) gelene kadar bekleniyor."
                ),
            }
        )
    return aksiyonlar


def hesapla_lojistik_plani(
    profiller: list[dict],
    katilimcilar: list[dict],
    ilk_slot: dict,
    hedef_sehir: str,
    trafik_hesapla: Callable[[str, str, str, str], str | dict],
    bilet_ara: Callable[[str, str, str, str], str | dict] | None = None,
    *,
    tum_slotlar: list[dict] | None = None,
) -> tuple[dict[str, dict], dict, str]:
    """
    Her katılımcı için trafik_ve_mesafe_getir (+ isteğe bağlı bilet_ara) çağrılır.
    Returns: (lojistik_plani, ortak_bulusma_penceresi, hata_durumu)
    """
    profil_by_isim = {p.get("isim", ""): p for p in profiller}
    slot_start = datetime.fromisoformat(ilk_slot["baslangic"])
    slot_end = datetime.fromisoformat(ilk_slot["bitis"])
    tarih = slot_start.strftime("%Y-%m-%d")
    slots = tum_slotlar or [ilk_slot]

    lojistik_plani: dict[str, dict] = {}
    varislar: list[tuple[str, datetime]] = []

    for k in katilimcilar:
        isim = k.get("isim", "")
        kalkis = k.get("kalkis_sehri", "")
        if not isim or not kalkis:
            return {}, {}, f"Eksik katılımcı verisi: {k}"

        profil = profil_by_isim.get(isim, {})
        cikis = _cikis_zamani(profil, slot_start)
        cikis_saat = _saat_metin(cikis)

        trafik_raw = trafik_hesapla(kalkis, hedef_sehir, cikis_saat, tarih)
        trafik = _parse_trafik_payload(trafik_raw)
        if trafik.get("hata"):
            return {}, {}, f"Trafik hesabı ({isim}): {trafik['hata']}"

        sure_sn = trafik.get("sure_saniye_trafik_dahil")
        if not sure_sn:
            return {}, {}, f"Trafik süresi yok ({isim})."

        varis = cikis + timedelta(seconds=float(sure_sn))

        bilet_verisi: dict[str, Any] = {}
        if bilet_ara is not None:
            bilet_raw = bilet_ara(tarih, kalkis, hedef_sehir, "otobus")
            bilet_verisi = _parse_bilet_payload(bilet_raw)

        lojistik_plani[isim] = {
            "isim": isim,
            "kalkis_sehri": kalkis,
            "hedef_sehir": hedef_sehir,
            "cikis_saati": cikis.isoformat(),
            "cikis_saat_metin": cikis_saat,
            "tahmini_varis_saati": varis.isoformat(),
            "tahmini_varis_saat_metin": _saat_metin(varis),
            "km": trafik.get("km"),
            "sure_metin": trafik.get("sure_metin", ""),
            "trafik_carpani": trafik.get("trafik_carpani", 1.0),
            "trafik_notu": trafik.get("trafik_notu", ""),
            "rota_araci": "trafik_ve_mesafe_getir",
            "bilet": bilet_verisi,
        }
        varislar.append((isim, varis))

    en_gec_isim, en_gec_dt = max(varislar, key=lambda x: x[1])
    gece_bas, gece_dinlenme_bitis, etkinlik_baslangic, etkinlik_modu = _gece_otel_ve_ilk_aktivite(
        en_gec_dt, ilk_slot, slots
    )
    varis_ozeti = [
        {"isim": isim, "varis_saat_metin": _saat_metin(dt), "varis_saati": dt.isoformat()}
        for isim, dt in sorted(varislar, key=lambda x: x[1])
    ]
    erken_aksiyonlar = _erken_gelen_aksiyonlari(varislar, en_gec_isim, en_gec_dt, hedef_sehir)

    ozet_satirlar = [f"{v['isim']} {v['varis_saat_metin']}'da varıyor" for v in varis_ozeti]

    pencere = {
        "tatil_baslangic": en_gec_dt.isoformat(),
        "tatil_baslangic_saat_metin": _saat_metin(en_gec_dt),
        "en_gec_varan": en_gec_isim,
        "gece_otel_baslangic": gece_bas.isoformat(),
        "gece_otel_baslangic_saat_metin": _saat_metin(gece_bas),
        "gece_otel_bitis": etkinlik_baslangic.isoformat(),
        "gece_otel_bitis_saat_metin": _saat_metin(etkinlik_baslangic),
        "gece_otel_aciklama": (
            f"Son varış {_saat_metin(en_gec_dt)}. "
            f"{_saat_metin(gece_bas)}–{_saat_metin(etkinlik_baslangic)} arası yalnızca otelde dinlenme/uyku; "
            "dışarıda ortak aktivite yok."
        ),
        "ortak_etkinlik_baslangic": etkinlik_baslangic.isoformat(),
        "ortak_etkinlik_baslangic_saat_metin": _saat_metin(etkinlik_baslangic),
        "ortak_etkinlik_modu": etkinlik_modu,
        "ilk_ortak_slot_metin": next(
            (s.get("metin", "") for s in slots if datetime.fromisoformat(s["baslangic"]) == etkinlik_baslangic),
            "",
        ),
        "kaynak_slot_baslangic": slot_start.isoformat(),
        "kaynak_slot_bitis": slot_end.isoformat(),
        "cuma_slot_notu": (
            "Cuma 18:00–23:00 takvim slotu ortak YOLA ÇIKIŞ penceresidir; "
            "gece varışları bu slotta buluşma anlamına gelmez."
        ),
        "varis_ozeti": varis_ozeti,
        "erken_gelen_aksiyonlari": erken_aksiyonlar,
        "metin": (
            f"Varış özeti: {'; '.join(ozet_satirlar)}. "
            f"Gece otel: {_saat_metin(gece_bas)}–{_saat_metin(etkinlik_baslangic)} (dinlenme). "
            f"İlk dış ortak aktivite: {_saat_metin(etkinlik_baslangic)} ({etkinlik_modu}). "
            + (
                f"Erken gelenler ({len(erken_aksiyonlar)} kişi) otelde bekler."
                if erken_aksiyonlar
                else ""
            )
        ),
    }
    return lojistik_plani, pencere, ""
