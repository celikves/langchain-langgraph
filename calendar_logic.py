"""Takvim karşılaştırma — saf Python; LLM saat hesabı yapmaz."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).parent


@dataclass(frozen=True)
class TimeSlot:
    baslangic: datetime
    bitis: datetime

    def format_tr(self) -> str:
        gun_adlari = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        gun = gun_adlari[self.baslangic.weekday()]
        return (
            f"{gun} {self.baslangic.strftime('%d.%m.%Y')} "
            f"{self.baslangic.strftime('%H:%M')}–{self.bitis.strftime('%H:%M')}"
        )

    def to_dict(self) -> dict:
        return {
            "baslangic": self.baslangic.isoformat(),
            "bitis": self.bitis.isoformat(),
            "metin": self.format_tr(),
        }


def _parse_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_calendars(path: str | Path) -> dict:
    if path is None or (isinstance(path, str) and not str(path).strip()):
        raise ValueError("takvim_dosyasi zorunludur; oturum JSON'unda yol belirtin.")
    calendar_path = Path(path)
    if not calendar_path.is_absolute():
        calendar_path = ROOT / calendar_path
    with calendar_path.open(encoding="utf-8") as f:
        return json.load(f)


def _busy_slots_for_day(
    day: date,
    events: list[dict],
    day_start: time,
    day_end: time,
) -> list[TimeSlot]:
    busy: list[TimeSlot] = []
    for event in events:
        if _parse_date(event["tarih"]) != day:
            continue
        start = datetime.combine(day, _parse_time(event["baslangic"]))
        end = datetime.combine(day, _parse_time(event["bitis"]))
        if end <= start:
            continue
        busy.append(TimeSlot(start, end))

    if not busy:
        return []

    busy.sort(key=lambda s: s.baslangic)
    merged = [busy[0]]
    for slot in busy[1:]:
        last = merged[-1]
        if slot.baslangic <= last.bitis:
            merged[-1] = TimeSlot(last.baslangic, max(last.bitis, slot.bitis))
        else:
            merged.append(slot)
    return merged


def _invert_busy_to_free(
    day: date,
    busy: list[TimeSlot],
    day_start: time,
    day_end: time,
) -> list[TimeSlot]:
    window_start = datetime.combine(day, day_start)
    window_end = datetime.combine(day, day_end)
    if window_end <= window_start:
        return []

    free: list[TimeSlot] = []
    cursor = window_start
    for slot in busy:
        if slot.baslangic > cursor:
            free.append(TimeSlot(cursor, min(slot.baslangic, window_end)))
        cursor = max(cursor, slot.bitis)
    if cursor < window_end:
        free.append(TimeSlot(cursor, window_end))
    return [s for s in free if s.bitis > s.baslangic]


def _intersect_slots(a: list[TimeSlot], b: list[TimeSlot]) -> list[TimeSlot]:
    result: list[TimeSlot] = []
    for sa in a:
        for sb in b:
            start = max(sa.baslangic, sb.baslangic)
            end = min(sa.bitis, sb.bitis)
            if end > start:
                result.append(TimeSlot(start, end))
    return result


def find_common_free_slots(
    calendar_data: dict | None = None,
    *,
    path: str | Path | None = None,
    min_duration_minutes: int | None = None,
) -> list[dict]:
    """
    İki (veya daha fazla) kişinin takvimini karşılaştırır; ortak boş aralıkları döner.
    """
    if calendar_data is None:
        if path is None or (isinstance(path, str) and not str(path).strip()):
            raise ValueError("find_common_free_slots: calendar_data veya geçerli path gerekli.")
        data = load_calendars(path)
    else:
        data = calendar_data
    meta = data["meta"]
    kisiler = data["kisiler"]

    gunler = [_parse_date(g) for g in meta["gunler"]]
    day_start = _parse_time(meta["gun_baslangic"])
    day_end = _parse_time(meta["gun_bitis"])
    min_delta = timedelta(
        minutes=min_duration_minutes if min_duration_minutes is not None else meta.get("minimum_bos_dakika", 60)
    )

    kisi_keys = list(kisiler.keys())
    if len(kisi_keys) < 2:
        raise ValueError("En az iki kişinin takvimi gerekli.")

    ortak: list[TimeSlot] = []

    for day in gunler:
        per_person_free: list[list[TimeSlot]] = []
        for key in kisi_keys:
            events = kisiler[key].get("etkinlikler", [])
            busy = _busy_slots_for_day(day, events, day_start, day_end)
            per_person_free.append(_invert_busy_to_free(day, busy, day_start, day_end))

        day_common = per_person_free[0]
        for other in per_person_free[1:]:
            day_common = _intersect_slots(day_common, other)

        for slot in day_common:
            if slot.bitis - slot.baslangic >= min_delta:
                ortak.append(slot)

    ortak.sort(key=lambda s: s.baslangic)
    return [s.to_dict() for s in ortak]


def summarize_calendars_for_llm(calendar_data: dict | None = None, *, path: str | Path | None = None) -> str:
    """Planlayıcı düğümüne bağlam olarak verilecek kısa özet (n kişi)."""
    if calendar_data is None:
        if path is None or (isinstance(path, str) and not str(path).strip()):
            raise ValueError("summarize_calendars_for_llm: calendar_data veya geçerli path gerekli.")
        data = load_calendars(path)
    else:
        data = calendar_data
    kisiler = data["kisiler"]
    lines = [f"Kişiler ve şehirler ({len(kisiler)} katılımcı):"]
    for i, (key, kisi) in enumerate(kisiler.items(), 1):
        rol = kisi.get("rol", key)
        lines.append(f"  {i}. {kisi.get('ad', key)} — {kisi.get('sehir', '?')} ({rol})")
    slots = find_common_free_slots(data)
    lines.append("\nOrtak boş zamanlar (Python hesabı, güvenilir):")
    if not slots:
        lines.append("  (Uygun ortak slot bulunamadı.)")
    else:
        for slot in slots:
            lines.append(f"  • {slot['metin']}")
    return "\n".join(lines)
