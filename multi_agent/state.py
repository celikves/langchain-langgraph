from __future__ import annotations

from typing import Annotated, Any, NotRequired, TypedDict

from langgraph.graph.message import add_messages


class KatilimciBilgisi(TypedDict):
    isim: str
    kalkis_sehri: str
    butce: str


class LojistikKisiPlani(TypedDict, total=False):
    isim: str
    kalkis_sehri: str
    hedef_sehir: str
    cikis_saati: str
    cikis_saat_metin: str
    tahmini_varis_saati: str
    tahmini_varis_saat_metin: str
    km: int
    sure_metin: str
    trafik_carpani: float
    trafik_notu: str
    rota_araci: str
    bilet: dict[str, Any]


class ErkenGelenAksiyonu(TypedDict):
    isim: str
    tahmini_varis_saat_metin: str
    tahmini_varis_saati: str
    bekleme_bitis_saat_metin: str
    bekleme_suresi_dakika: int
    bulusma_noktasi: str
    aksiyon: str


class VarisOzeti(TypedDict):
    isim: str
    varis_saat_metin: str
    varis_saati: str


class KesifAktivitesi(TypedDict, total=False):
    tur: str  # plaj | yemek | gezi | muzik
    ad: str
    sure_dakika: int
    mekan: str
    tercih_sahibi: str
    tercih_etiketi: str
    kaynak: str


class KesifVerisi(TypedDict, total=False):
    hava: dict[str, Any]
    mekanlar: list[dict[str, Any]]
    aktiviteler: list[KesifAktivitesi]
    tercih_ozeti: list[dict[str, Any]]
    arama_sayisi: int
    uyari: str


class OrtakBulusmaPenceresi(TypedDict, total=False):
    tatil_baslangic: str
    tatil_baslangic_saat_metin: str
    en_gec_varan: str
    ortak_etkinlik_baslangic: str
    ortak_etkinlik_baslangic_saat_metin: str
    ortak_etkinlik_modu: str
    kaynak_slot_baslangic: str
    kaynak_slot_bitis: str
    varis_ozeti: list[VarisOzeti]
    erken_gelen_aksiyonlari: list[ErkenGelenAksiyonu]
    metin: str


class SeyahatState(TypedDict, total=False):
    """
    Multi-Agent LangGraph ortak hafızası.
    Serbest metin yerine JSON/araç çıktısından doldurulan yapılandırılmış alanlar.
    """

    messages: Annotated[list, add_messages]

    session_config_path: str
    hedef_sehir: str
    takvim_dosyasi: str
    ortak_kisitlamalar: str
    hedef_tarih: str

    katilimci_bilgileri: list[KatilimciBilgisi]
    kullanici_profilleri: list[dict[str, Any]]
    ortak_bos_zamanlar: list[dict[str, Any]]
    lojistik_plani: dict[str, LojistikKisiPlani]
    ortak_bulusma_penceresi: OrtakBulusmaPenceresi
    hata_durumu: NotRequired[str]

    lojistik_verisi: dict[str, Any]
    kesif_verisi: dict[str, Any]
    nihai_plan: str

    hata_mesaji: str
    siradaki_ajan: str
    revizyon_sayisi: int
    kesif_kategorileri: list[dict[str, Any]]
    kisi_sayisi: int
