"""Adım 3 — deterministik plan_builder birim testleri."""

from __future__ import annotations

import re
import unittest

from multi_agent.plan_builder import (
    _dakika_aralik,
    _kesif_yerlestir,
    _slot_saat_araligi,
    deterministik_plan_olustur,
)
from multi_agent.plan_validate import kesif_satir_mi, plan_satirlari


class SlotSaatTest(unittest.TestCase):
    def test_slot_aralik(self):
        slot = {"baslangic": "2026-06-06T11:30:00", "bitis": "2026-06-06T15:00:00"}
        self.assertEqual(_slot_saat_araligi(slot), "11:30-15:00")

    def test_dakika_aralik(self):
        bas, bit = _dakika_aralik("11:30", 90)
        self.assertEqual(bas, "11:30")
        self.assertEqual(bit, "13:00")


class KesifYerlestirmeTest(unittest.TestCase):
    def test_ardisik_uc_yemek_yok(self):
        slots = [
            {"baslangic": "2026-06-06T11:30:00", "bitis": "2026-06-06T15:00:00"},
            {"baslangic": "2026-06-06T16:30:00", "bitis": "2026-06-06T23:00:00"},
            {"baslangic": "2026-06-07T07:00:00", "bitis": "2026-06-07T14:00:00"},
        ]
        aktiviteler = [
            {"tur": "yemek", "ad": "Yemek A", "mekan": "A", "sure_dakika": 60, "mekan_zorunlu": True},
            {"tur": "yemek", "ad": "Yemek B", "mekan": "B", "sure_dakika": 60, "mekan_zorunlu": True},
            {"tur": "yemek", "ad": "Yemek C", "mekan": "C", "sure_dakika": 60, "mekan_zorunlu": True},
            {"tur": "gezi", "ad": "Gezi X", "mekan": "Müze", "sure_dakika": 90, "mekan_zorunlu": True},
        ]
        yerlesen = _kesif_yerlestir(slots, aktiviteler)
        turler = [a["tur"] for _, a in yerlesen]
        for i in range(len(turler) - 2):
            self.assertFalse(turler[i : i + 3] == ["yemek", "yemek", "yemek"])


class DeterministikPlanTest(unittest.TestCase):
    def _ornek_state(self) -> dict:
        return {
            "ortak_bos_zamanlar": [
                {"baslangic": "2026-06-05T18:00:00", "bitis": "2026-06-05T23:00:00", "metin": "Cuma"},
                {"baslangic": "2026-06-06T11:30:00", "bitis": "2026-06-06T15:00:00", "metin": "Cmt"},
                {"baslangic": "2026-06-06T16:30:00", "bitis": "2026-06-06T23:00:00", "metin": "Cmt2"},
                {"baslangic": "2026-06-07T07:00:00", "bitis": "2026-06-07T14:00:00", "metin": "Paz"},
                {"baslangic": "2026-06-07T16:00:00", "bitis": "2026-06-07T19:00:00", "metin": "Paz2"},
                {"baslangic": "2026-06-07T21:00:00", "bitis": "2026-06-07T23:00:00", "metin": "Paz3"},
            ],
            "lojistik_plani": {
                "Ali": {
                    "isim": "Ali",
                    "kalkis_sehri": "Ankara",
                    "cikis_saat_metin": "18:00",
                    "tahmini_varis_saat_metin": "23:30",
                }
            },
            "ortak_bulusma_penceresi": {
                "ortak_etkinlik_baslangic": "2026-06-06T11:30:00",
                "gece_otel_baslangic_saat_metin": "23:30",
                "gece_otel_bitis_saat_metin": "11:30",
                "gece_otel_aciklama": "Otelde dinlenme",
                "erken_gelen_aksiyonlari": [
                    {
                        "isim": "Ayşe",
                        "tahmini_varis_saat_metin": "22:00",
                        "bekleme_bitis_saat_metin": "23:30",
                        "aksiyon": "Otelde bekleme",
                    }
                ],
            },
            "kesif_verisi": {
                "hava": {"ham_metin": "25°C güneşli", "sicaklik_c": "25"},
                "aktiviteler": [
                    {
                        "tur": "gezi",
                        "ad": "Gezi — Kaleiçi",
                        "mekan": "Kaleiçi",
                        "sure_dakika": 90,
                        "mekan_zorunlu": True,
                    },
                    {
                        "tur": "yemek",
                        "ad": "Anatolia Restaurant",
                        "mekan": "Anatolia Restaurant",
                        "sure_dakika": 60,
                        "mekan_zorunlu": True,
                    },
                    {
                        "tur": "plaj",
                        "ad": "Plaj/yüzme — Konyaaltı Plajı",
                        "mekan": "Konyaaltı Plajı",
                        "sure_dakika": 120,
                        "mekan_zorunlu": False,
                    },
                ],
            },
        }

    def test_format_ve_zorunlu_bolumler(self):
        plan = deterministik_plan_olustur(self._ornek_state())
        self.assertIn("### Hafta Sonu Planı (deterministik)", plan)
        self.assertIn("**Lojistik:**", plan)
        self.assertIn("**Keşif:**", plan)
        self.assertIn("Dayanak: lojistik", plan)
        self.assertIn("Dayanak: kesif", plan)
        self.assertIn("Ayşe", plan)
        self.assertIn("23:30-11:30", plan)
        self.assertIn("21:00-23:00", plan)

        satirlar = plan_satirlari(plan)
        kesif = [s for s in satirlar if kesif_satir_mi(s)]
        self.assertGreaterEqual(len(kesif), 1)
        for s in kesif:
            self.assertRegex(s, r"Dayanak:\s*kesif", re.I)


if __name__ == "__main__":
    unittest.main()
