"""Adım 1 — keşif isimlendirme ve plan doğrulama birim testleri."""

from __future__ import annotations

import unittest

from multi_agent.kesif_layer import (
    _aktivite_ad_uret,
    kesif_partial_birlestir,
    mekan_satir_uygun,
)
from multi_agent.place_extract import gecerli_mekan_adi, mekan_adi_temizle
from multi_agent.plan_validate import kesif_satir_dogrula, kesif_satir_mi, plan_satirlari


class AktiviteAdTest(unittest.TestCase):
    def test_plaj_mekanli_ayirt_edici_ad(self):
        kat = {"tur": "plaj", "aktivite_ad": "Plaj/yüzme", "mekan_zorunlu": False}
        self.assertEqual(_aktivite_ad_uret(kat, "Konyaaltı Plajı"), "Plaj/yüzme — Konyaaltı Plajı")
        self.assertEqual(_aktivite_ad_uret(kat, ""), "Plaj/yüzme")

    def test_gezi_oneki(self):
        kat = {"tur": "gezi", "aktivite_ad_oneki": "Gezi", "mekan_zorunlu": True}
        self.assertEqual(_aktivite_ad_uret(kat, "Anatolia Restaurant"), "Gezi — Anatolia Restaurant")


class MekanTemizlikTest(unittest.TestCase):
    def test_platform_soneki_temizlenir(self):
        ad = mekan_adi_temizle("Konyaaltı Plajı - Apple Maps")
        self.assertEqual(ad, "Konyaaltı Plajı")

    def test_belediye_elenir(self):
        self.assertFalse(gecerli_mekan_adi("Antalya Büyükşehir Belediyesi - Facebook"))


class MergeDedupeTest(unittest.TestCase):
    def test_ayni_mekan_farkli_ad_tek_aktivite(self):
        partials = [
            {
                "mekanlar": [{"ad": "Arkadas Alabalik Restaurant"}],
                "aktiviteler": [
                    {
                        "tur": "gezi",
                        "ad": "Gezi — ARKADAS ALABALIK RESTAURANT, Antalya",
                        "mekan": "Arkadas Alabalik Restaurant",
                        "mekan_zorunlu": True,
                    }
                ],
                "uyarilar": [],
                "plaj_mekan_bulundu": False,
                "arama_sayisi": 1,
            },
            {
                "mekanlar": [],
                "aktiviteler": [
                    {
                        "tur": "yemek",
                        "ad": "Anatolia Restaurant",
                        "mekan": "Anatolia Restaurant",
                        "mekan_zorunlu": True,
                    },
                    {
                        "tur": "gezi",
                        "ad": "Gezi — Arkadas Alabalik Restaurant",
                        "mekan": "Arkadas Alabalik Restaurant",
                        "mekan_zorunlu": True,
                    },
                ],
                "uyarilar": [],
                "plaj_mekan_bulundu": False,
                "arama_sayisi": 1,
            },
        ]
        kv, err = kesif_partial_birlestir("Antalya", [], [], partials, {})
        self.assertEqual(err, "")
        gezi = [a for a in kv["aktiviteler"] if a["tur"] == "gezi"]
        self.assertEqual(len(gezi), 1)


class PlanParserTest(unittest.TestCase):
    def test_llm_bullet_format_taninir(self):
        plan = "- **11:30-12:30** | Plaj/yüzme — Konyaaltı (Mekan: Konyaaltı Plajı) | Dayanak: keşif"
        satirlar = plan_satirlari(plan)
        self.assertEqual(len(satirlar), 1)
        self.assertTrue(kesif_satir_mi(satirlar[0]))

    def test_plaj_yok_gecerli(self):
        kv = {
            "hedef_sehir": "Antalya",
            "aktiviteler": [
                {
                    "ad": "Plaj/yüzme — Konyaaltı Plajı",
                    "tur": "plaj",
                    "mekan": "Konyaaltı Plajı",
                    "mekan_zorunlu": False,
                }
            ],
        }
        satir = "13:30-15:00 | Plaj/yüzme — Konyaaltı Plajı (Mekan: yok) | Dayanak: kesif"
        ok, tur = kesif_satir_dogrula(satir, kv)
        self.assertTrue(ok, tur)
        self.assertTrue(mekan_satir_uygun(kv["aktiviteler"][0], "yok", kv))


if __name__ == "__main__":
    unittest.main()
