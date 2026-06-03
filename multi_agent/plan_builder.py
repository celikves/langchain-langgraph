"""Deterministik plan sentezi — reviewer kurallarına uyan satırlar (LLM revizyon yedeği)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from multi_agent.kesif_layer import _norm

_GUN_BASLIKLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
_TUR_ONCELIK = ("gezi", "plaj", "yemek", "muzik")


def _slot_saat_araligi(slot: dict) -> str:
    """Slot ISO zamanlarından HH:MM-HH:MM."""
    bas = datetime.fromisoformat(slot["baslangic"])
    bit = datetime.fromisoformat(slot["bitis"])
    return f"{bas.strftime('%H:%M')}-{bit.strftime('%H:%M')}"


def _dakika_aralik(bas_hhmm: str, sure_dk: int) -> tuple[str, str]:
    """HH:MM + süre → (başlangıç, bitiş) aynı gün."""
    h, m = map(int, bas_hhmm.split(":"))
    bas_dt = datetime(2000, 1, 1, h, m)
    bit_dt = bas_dt + timedelta(minutes=max(int(sure_dk), 15))
    return bas_dt.strftime("%H:%M"), bit_dt.strftime("%H:%M")


def _aralik_olustur(bas: str, bit: str) -> str:
    return f"{bas}-{bit}"


def _lojistik_satir(aralik: str, aciklama: str) -> str:
    return f"**Lojistik:** {aralik} | {aciklama} | Dayanak: lojistik"


def _kesif_satir(aralik: str, aktivite: dict) -> str:
    ad = (aktivite.get("ad") or "").strip()
    mekan = (aktivite.get("mekan") or "").strip()
    zorunlu = bool(aktivite.get("mekan_zorunlu", True))
    if not zorunlu and not mekan:
        mekan_metin = "yok"
    elif mekan:
        mekan_metin = mekan
    elif zorunlu:
        mekan_metin = "yok"
    else:
        mekan_metin = "yok"
    return f"**Keşif:** {aralik} | {ad} (Mekan: {mekan_metin}) | Dayanak: kesif"


def _gun_basligi(dt: datetime) -> str:
    return f"#### {_GUN_BASLIKLARI[dt.weekday()]}"


def _slot_baslangic(slot: dict) -> datetime:
    return datetime.fromisoformat(slot["baslangic"])


def _kesif_slotlari(
    slots: list[dict],
    *,
    etkinlik_baslangic: datetime | None,
) -> list[dict]:
    """Cuma yol slotu hariç, ortak aktivite başlangıcından sonraki keşif slotları."""
    out: list[dict] = []
    for slot in slots:
        bas = _slot_baslangic(slot)
        if bas.weekday() == 4 and bas.hour >= 17:
            continue
        if etkinlik_baslangic and bas < etkinlik_baslangic:
            continue
        out.append(slot)
    return out


def _pazar_donus_slotu(slots: list[dict]) -> dict | None:
    for slot in reversed(slots):
        bas = _slot_baslangic(slot)
        if bas.weekday() == 6 and bas.hour >= 20:
            return slot
    return None


def _pazar_rezervasyon_araligi(slots: list[dict]) -> str | None:
    """16–19 ve 21–23 arasında boşluk → takvim rezervasyon penceresi."""
    pazar = sorted(
        [s for s in slots if _slot_baslangic(s).weekday() == 6],
        key=lambda s: s["baslangic"],
    )
    if len(pazar) < 2:
        return None
    for a, b in zip(pazar, pazar[1:]):
        bit_a = datetime.fromisoformat(a["bitis"])
        bas_b = datetime.fromisoformat(b["baslangic"])
        if bas_b > bit_a:
            return f"{bit_a.strftime('%H:%M')}-{bas_b.strftime('%H:%M')}"
    return None


def _aktivite_sirala(aktiviteler: list[dict]) -> list[dict]:
    """Tür önceliği + tercih sahibi çeşitliliği."""
    def key(a: dict) -> tuple[int, str]:
        tur = a.get("tur") or "gezi"
        try:
            oncelik = _TUR_ONCELIK.index(tur)
        except ValueError:
            oncelik = 99
        return (oncelik, _norm(a.get("ad") or ""))

    return sorted(aktiviteler, key=key)


def _aktivite_sec(
    havuz: list[dict],
    *,
    kullanilan_mekan: set[str],
    kullanilan_ad: set[str],
    son_turler: list[str],
) -> dict | None:
    for a in _aktivite_sirala(havuz):
        tur = a.get("tur") or ""
        ad = (a.get("ad") or "").strip()
        mekan = (a.get("mekan") or "").strip()
        if not ad:
            continue
        ad_key = _norm(ad)
        if ad_key in kullanilan_ad:
            continue
        mekan_key = _norm(mekan) if mekan else ""
        if mekan_key and mekan_key in kullanilan_mekan:
            continue
        if tur == "yemek" and len(son_turler) >= 2 and son_turler[-2:] == ["yemek", "yemek"]:
            continue
        return a
    return None


def _kesif_yerlestir(
    kesif_slots: list[dict],
    aktiviteler: list[dict],
) -> list[tuple[str, dict]]:
    """Her slota en fazla bir keşif aktivitesi; mümkünse slot süresine sığdır."""
    kullanilan_mekan: set[str] = set()
    kullanilan_ad: set[str] = set()
    son_turler: list[str] = []
    havuz = list(aktiviteler)
    yerlesen: list[tuple[str, dict]] = []

    for slot in kesif_slots:
        if not havuz:
            break
        aralik_slot = _slot_saat_araligi(slot)
        bas_str, _ = aralik_slot.split("-", 1)
        secilen = _aktivite_sec(
            havuz,
            kullanilan_mekan=kullanilan_mekan,
            kullanilan_ad=kullanilan_ad,
            son_turler=son_turler,
        )
        if not secilen:
            continue
        sure = int(secilen.get("sure_dakika") or 60)
        bas, bit = _dakika_aralik(bas_str, sure)
        slot_bit = datetime.fromisoformat(slot["bitis"]).strftime("%H:%M")
        if bit > slot_bit:
            bit = slot_bit
        aralik = _aralik_olustur(bas, bit)
        yerlesen.append((aralik, secilen))
        havuz.remove(secilen)
        kullanilan_ad.add(_norm(secilen.get("ad") or ""))
        mk = (secilen.get("mekan") or "").strip()
        if mk:
            kullanilan_mekan.add(_norm(mk))
        son_turler.append(secilen.get("tur") or "")
        if len(son_turler) > 3:
            son_turler.pop(0)
    return yerlesen


def _hava_bolumu(hava: dict) -> list[str]:
    satirlar: list[str] = []
    ham = (hava.get("ham_metin") or "").strip()
    if ham:
        for parca in re.split(r"\n{2,}|\n", ham):
            p = parca.strip()
            if p:
                satirlar.append(f"- {p}")
    sicaklik = (hava.get("sicaklik_c") or "").strip()
    yagis = (hava.get("yagis_ihtimali_yuzde") or "").strip()
    if sicaklik or yagis:
        ozet = []
        if sicaklik:
            ozet.append(f"Sıcaklık: {sicaklik}°C")
        if yagis:
            ozet.append(f"Yağış ihtimali: %{yagis}")
        satirlar.append(f"- {', '.join(ozet)}")
    if not satirlar:
        satirlar.append("- Hava verisi keşif aşamasından alındı.")
    return ["### Hava Durumu", *satirlar]


def deterministik_plan_olustur(state: dict[str, Any]) -> str:
    """
    Lojistik iskelet (varış, erken gelen, gece otel, dönüş) + keşif aktivitelerini
    ortak slotlara yerleştirir. Reviewer formatına uygundur.
    """
    kesif_verisi = state.get("kesif_verisi") or {}
    aktiviteler = list(kesif_verisi.get("aktiviteler") or [])
    if not aktiviteler:
        return ""

    slots = list(state.get("ortak_bos_zamanlar") or [])
    pencere = state.get("ortak_bulusma_penceresi") or {}
    lojistik = state.get("lojistik_plani") or {}
    hava = kesif_verisi.get("hava") or {}

    etkinlik_bas: datetime | None = None
    raw_bas = pencere.get("ortak_etkinlik_baslangic")
    if raw_bas:
        try:
            etkinlik_bas = datetime.fromisoformat(raw_bas)
        except ValueError:
            etkinlik_bas = None

    satirlar: list[str] = ["### Hafta Sonu Planı (deterministik)", ""]

    # --- Cuma: yol + varış + gece otel + erken gelen ---
    satirlar.append("#### Cuma")
    cuma_slot = next((s for s in slots if _slot_baslangic(s).weekday() == 4), None)
    cuma_aralik = _slot_saat_araligi(cuma_slot) if cuma_slot else "18:00-23:00"

    for isim, plan in sorted(lojistik.items(), key=lambda x: x[0]):
        kalkis = plan.get("kalkis_sehri", "")
        cikis = plan.get("cikis_saat_metin", "")
        varis = plan.get("tahmini_varis_saat_metin", "")
        satirlar.append(
            _lojistik_satir(
                f"{cikis}-{varis}" if cikis and varis else cuma_aralik,
                f"{isim}: {kalkis} → yola çıkış, tahmini varış {varis}",
            )
        )

    for aks in pencere.get("erken_gelen_aksiyonlari") or []:
        bas = aks.get("tahmini_varis_saat_metin", "")
        bit = aks.get("bekleme_bitis_saat_metin", "")
        aralik = f"{bas}-{bit}" if bas and bit else cuma_aralik
        satirlar.append(
            _lojistik_satir(
                aralik,
                f"{aks.get('isim', '')}: {aks.get('aksiyon', 'Otelde bekleme')}",
            )
        )

    gece_bas = pencere.get("gece_otel_baslangic_saat_metin", "")
    gece_bit = pencere.get("gece_otel_bitis_saat_metin", "")
    if gece_bas and gece_bit:
        satirlar.append(
            _lojistik_satir(
                f"{gece_bas}-{gece_bit}",
                pencere.get("gece_otel_aciklama", "Otelde dinlenme/uyku"),
            )
        )
    satirlar.append("")

    # --- Keşif günleri (slot sırasıyla) ---
    kesif_slots = _kesif_slotlari(slots, etkinlik_baslangic=etkinlik_bas)
    yerlesen = _kesif_yerlestir(kesif_slots, aktiviteler)
    yerlesen_kuyruk = list(yerlesen)
    pazar_rez_eklendi = False

    mevcut_gun: str | None = None
    for slot in kesif_slots:
        gun = _gun_basligi(_slot_baslangic(slot))
        if gun != mevcut_gun:
            if mevcut_gun is not None:
                satirlar.append("")
            satirlar.append(gun)
            mevcut_gun = gun

        if yerlesen_kuyruk:
            aralik, akt = yerlesen_kuyruk.pop(0)
            satirlar.append(_kesif_satir(aralik, akt))

        if _slot_baslangic(slot).weekday() == 6 and not pazar_rez_eklendi:
            rez = _pazar_rezervasyon_araligi(slots)
            if rez:
                satirlar.append(
                    _lojistik_satir(
                        rez,
                        "Rezervasyonlu akşam yemeği (takvim — ortak buluşma)",
                    )
                )
                pazar_rez_eklendi = True

    donus = _pazar_donus_slotu(slots)
    if donus:
        satirlar.append("")
        donus_gun = _gun_basligi(_slot_baslangic(donus))
        if donus_gun != mevcut_gun:
            satirlar.append(donus_gun)
        satirlar.append(
            _lojistik_satir(
                _slot_saat_araligi(donus),
                "Dönüş hazırlığı / yola çıkış (takvim penceresi)",
            )
        )

    satirlar.append("")
    satirlar.extend(_hava_bolumu(hava))
    return "\n".join(satirlar).strip() + "\n"
