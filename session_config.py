"""Oturum ve profil JSON'larından dinamik prompt değişkenleri üretir."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from calendar_logic import find_common_free_slots, load_calendars, summarize_calendars_for_llm

ROOT = Path(__file__).parent
DEFAULT_SESSION_PATH = ROOT / "data" / "sessions" / "antalya_kizkiza_tatil.json"
DEFAULT_KESIF_KATEGORILERI_PATH = ROOT / "data" / "defaults" / "kesif_kategorileri.json"
MAX_KATILIMCI = 12
MIN_KATILIMCI = 2
TZ = ZoneInfo("Europe/Istanbul")


def _resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def load_json(path: str | Path) -> dict | list:
    with _resolve_path(path).open(encoding="utf-8") as f:
        return json.load(f)


def load_profiles(paths: list[str]) -> list[dict]:
    return [load_json(p) for p in paths]


def load_session_config(path: str | Path | None = None) -> dict:
    return load_json(path or DEFAULT_SESSION_PATH)


def format_kullanici_baglami(profiller: list[dict], hedef_sehir: str) -> str:
    lines = [f"Sisteme kayıtlı {len(profiller)} katılımcı var (hedef: {hedef_sehir}):"]
    for i, p in enumerate(profiller, 1):
        isim = p.get("isim", f"Katılımcı {i}")
        kalkis = p.get("kalkis_yeri") or p.get("sehir", "?")
        butce = p.get("butce", "belirtilmedi")
        tercihler = ", ".join(p.get("tercihler", [])) or "—"
        mesai = p.get("mesai")
        mesai_txt = (
            f"mesai {mesai['baslangic']}–{mesai['bitis']} ({mesai.get('gunler', '')})"
            if isinstance(mesai, dict)
            else "mesai kısıtı yok / esnek"
        )
        notlar = p.get("notlar", "")
        lines.append(
            f"  {i}. {isim} — kalkış: {kalkis}; bütçe: {butce}; tercihler: {tercihler}; {mesai_txt}."
            + (f" Not: {notlar}" if notlar else "")
        )
    return "\n".join(lines)


def load_kesif_kategorileri(session: dict) -> list[dict]:
    """Oturum override veya varsayılan — ulaşım/konaklama lojistikte, keşifte değil."""
    if session.get("kesif_kategorileri"):
        return list(session["kesif_kategorileri"])
    raw = load_json(DEFAULT_KESIF_KATEGORILERI_PATH)
    return raw if isinstance(raw, list) else []


def _render_template(text: str, ctx: dict) -> str:
    if "{" not in text:
        return text
    try:
        return text.format(**ctx)
    except KeyError:
        return text


def render_kesif_kategorileri(kategoriler: list[dict], ctx: dict) -> list[dict]:
    """Sorgu şablonlarında {hedef} / {hedef_sehir} yer tutucularını doldurur."""
    fmt_ctx = {**ctx, "hedef": ctx.get("hedef_sehir", ctx.get("hedef", ""))}
    rendered = []
    for k in kategoriler:
        if not k.get("etkin", True):
            continue
        item = dict(k)
        sablon = item.get("sorgu_sablonu") or ""
        if sablon:
            item["sorgu_sablonu"] = _render_template(sablon, fmt_ctx)
        rendered.append(item)
    return rendered


def build_zaman_kisitlamalari(now: datetime | None = None) -> str:
    dt = now or datetime.now(TZ)
    gun_adlari = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    gun = gun_adlari[dt.weekday()]
    return (
        f"Bugün: {gun}, {dt.strftime('%d.%m.%Y %H:%M')} (Europe/Istanbul). "
        "Planlarda bu tarihi ve hafta içi/sonu ayrımını dikkate al."
    )


def build_session_context(
    session_path: str | Path | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    """State bootstrap ve prompt için tek sözlük."""
    session = load_session_config(session_path)
    profiller = load_profiles(session["profil_dosyalari"])
    hedef = session.get("hedef_sehir", "Antalya")

    takvim_path = session.get("takvim_dosyasi")
    if not takvim_path:
        raise ValueError("Oturum dosyasında 'takvim_dosyasi' zorunludur.")
    calendar_data = load_calendars(takvim_path)
    slots = find_common_free_slots(calendar_data)
    slot_metinleri = [s["metin"] for s in slots]
    takvim_ozeti = summarize_calendars_for_llm(calendar_data)

    ctx = {
        "hedef_sehir": hedef,
        "kisi_sayisi": len(profiller),
    }

    kesif_kategorileri = render_kesif_kategorileri(load_kesif_kategorileri(session), ctx)
    ortak_kisit = _render_template(session.get("ortak_kisitlamalar", ""), ctx)
    is_akis = _render_template(session.get("is_akis_adimlari", ""), ctx)
    ozel = _render_template(session.get("ozel_kurallar", ""), ctx)
    ana_gorev = _render_template(session.get("ana_gorev", ""), ctx)

    zaman = build_zaman_kisitlamalari(now)
    if slot_metinleri:
        zaman += "\nOrtak boş zamanlar (Python/takvim): " + "; ".join(slot_metinleri)
    zaman += f"\n\nTakvim özeti:\n{takvim_ozeti}"

    return {
        "session_id": session.get("session_id", "default"),
        "session_config_path": str(session_path or DEFAULT_SESSION_PATH),
        "ana_gorev": ana_gorev,
        "kullanici_profilleri": profiller,
        "kullanici_baglami": format_kullanici_baglami(profiller, hedef),
        "zaman_kisitlamalari": zaman,
        "ortak_kisitlamalar": ortak_kisit,
        "is_akis_adimlari": is_akis,
        "ozel_kurallar": ozel,
        "hedef_sehir": hedef,
        "takvim_dosyasi": str(takvim_path) if takvim_path else "",
        "takvim_ozeti": takvim_ozeti,
        "ortak_bos_zamanlar": slots,
        "ortak_bos_zaman_metinleri": slot_metinleri,
        "kesif_kategorileri": kesif_kategorileri,
        "kisi_sayisi": len(profiller),
    }
