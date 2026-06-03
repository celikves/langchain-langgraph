import os
from langchain_core.messages import SystemMessage, HumanMessage
import json
import re

from multi_agent.state import SeyahatState
from multi_agent.tools import kesif_araclari, lojistik_araclari

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()
elif not os.getenv("OPENAI_API_KEY"):
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except OSError:
            pass

# ==========================================
# ORTAK LLM KURULUMU
# ==========================================
# Tüm ajanlar bu modeli kullanacak. 
# Sıcaklık (temperature) 0 tutularak analitik ve tutarlı sonuçlar hedefleniyor.
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None


def _build_llm():
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and ChatOpenAI is not None:
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            api_key=openai_key,
        )
    if ChatOllama is not None:
        return ChatOllama(model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"), temperature=0)
    raise RuntimeError(
        "LLM bulunamadı: OPENAI_API_KEY + langchain_openai veya langchain_ollama gerekli."
    )


llm = _build_llm()


def _halt_payload(hata: str) -> dict:
    return {"hata_durumu": hata, "siradaki_ajan": "basarisiz_kapanis"}


# ==========================================
# 1. LOJİSTİK AJANI VE DÜĞÜMÜ
# ==========================================
def lojistik_node(state: SeyahatState):
    print("\n[🤖] Lojistik Ajanı — N kişi rota ve buluşma senkronizasyonu...")
    if state.get("hata_durumu"):
        return {}

    from multi_agent.logistics_compute import hesapla_lojistik_plani

    profiller = state.get("kullanici_profilleri") or []
    katilimcilar = state.get("katilimci_bilgileri") or []
    slots = state.get("ortak_bos_zamanlar") or []
    hedef = state.get("hedef_sehir", "")
    if not hedef:
        return _halt_payload("hedef_sehir state'te tanımlı değil.")
    if not slots:
        return _halt_payload("ortak_bos_zamanlar boş; lojistik hesaplanamaz.")

    trafik_araci = next(t for t in lojistik_araclari if t.name == "trafik_ve_mesafe_getir")
    bilet_araci = next(t for t in lojistik_araclari if t.name == "bilet_ara")

    print(f"  → {len(katilimcilar)} katılımcı için trafik_ve_mesafe_getir + bilet_ara döngüsü")
    for k in katilimcilar:
        print(f"     • {k.get('isim')}: {k.get('kalkis_sehri')} → {hedef}")

    def trafik_fn(kalkis: str, varis: str, saat: str, tarih: str) -> str:
        return str(
            trafik_araci.invoke(
                {
                    "kalkis_sehir": kalkis,
                    "varis_sehir": varis,
                    "kalkis_saati": saat,
                    "tarih": tarih,
                }
            )
        )

    def bilet_fn(tarih: str, kalkis: str, varis: str, tercih: str) -> str:
        return str(
            bilet_araci.invoke(
                {"tarih": tarih, "kalkis": kalkis, "varis": varis, "tercih": tercih}
            )
        )

    lojistik_plani, pencere, hata = hesapla_lojistik_plani(
        profiller,
        katilimcilar,
        slots[0],
        hedef,
        trafik_fn,
        bilet_fn,
        tum_slotlar=slots,
    )
    if hata:
        return _halt_payload(hata)

    for v in pencere.get("varis_ozeti", []):
        print(f"     ✓ {v['isim']} varış: {v['varis_saat_metin']}")
    print(f"  → Gece otel dinlenme: {pencere.get('gece_otel_baslangic_saat_metin')}–{pencere.get('gece_otel_bitis_saat_metin')}")
    print(f"  → İlk dış aktivite (takvim): {pencere.get('ortak_etkinlik_baslangic_saat_metin')} ({pencere.get('ilk_ortak_slot_metin', '')})")

    lojistik_verisi = {
        "kisit_ozeti": state.get("ortak_kisitlamalar", ""),
        "rota_ozetleri": list(lojistik_plani.values()),
        "ortak_bulusma_penceresi": pencere,
        "ilk_ortak_slot": slots[0],
        "arac_cagrilari": ["trafik_ve_mesafe_getir", "bilet_ara"],
    }
    return {
        "lojistik_plani": lojistik_plani,
        "ortak_bulusma_penceresi": pencere,
        "lojistik_verisi": lojistik_verisi,
    }

# ==========================================
# 2. KEŞİF AJANI VE DÜĞÜMÜ
# ==========================================
kesif_prompt = """Keşif deterministik kesif_layer modülü ile yapılır (profil tercihleri × N arama)."""


def kesif_node(state: SeyahatState):
    print("\n[🔎] Keşif Ajanı Çalışıyor...")
    if state.get("hata_durumu"):
        return {}

    from multi_agent.kesif_layer import kesif_verisi_topla

    hava_araci = next(t for t in kesif_araclari if t.name == "hava_durumu_getir")
    mekan_araci = next(t for t in kesif_araclari if t.name == "internette_mekan_ara")
    hedef = state.get("hedef_sehir", "")
    hedef_tarih = state.get("hedef_tarih", "")
    if not hedef or not hedef_tarih:
        return _halt_payload("hedef_sehir veya hedef_tarih eksik.")

    profiller = state.get("kullanici_profilleri") or []
    kategoriler = state.get("kesif_kategorileri") or []

    def hava_fn(sehir: str, tarih: str) -> str:
        return str(hava_araci.invoke({"sehir": sehir, "tarih": tarih}))

    def mekan_fn(sorgu: str) -> str:
        return str(mekan_araci.invoke({"sorgu": sorgu}))

    kesif_verisi, hata = kesif_verisi_topla(
        hedef,
        hedef_tarih,
        profiller,
        kategoriler,
        hava_fn=hava_fn,
        mekan_ara_fn=mekan_fn,
    )
    if hata:
        return _halt_payload(hata)

    mekan_adlari = [m["ad"] for m in kesif_verisi.get("mekanlar", [])]
    aktivite_adlari = [a["ad"] for a in kesif_verisi.get("aktiviteler", [])]
    print(f"  ✓ {kesif_verisi.get('arama_sayisi', 0)} arama → "
          f"{len(mekan_adlari)} mekan, {len(aktivite_adlari)} aktivite")
    if mekan_adlari:
        print(f"  ✓ Mekanlar: {', '.join(mekan_adlari[:5])}")
    if aktivite_adlari:
        print(f"  ✓ Aktiviteler: {', '.join(dict.fromkeys(aktivite_adlari))}")

    return {"kesif_verisi": kesif_verisi}

# ==========================================
# 3. PLANLAYICI AJAN (SENTEZ) DÜĞÜMÜ
# ==========================================
# Planlayıcı dış dünya ile iletişime geçmez (tool kullanmaz).
# Sadece State'teki verileri alıp akıcı bir metne döker.
def planlayici_node(state: SeyahatState):
    print("\n[✍️] Planlayıcı Ajan Sentez Yapıyor...")
    if state.get("hata_durumu"):
        return {}

    revizyon_sayisi = state.get("revizyon_sayisi", 0)
    hata_mesaji = state.get("hata_mesaji", "")

    kesif_verisi = state.get("kesif_verisi") or {
        "hava": {},
        "mekanlar": [],
        "aktiviteler": [],
        "uyari": "",
    }
    aktiviteler = kesif_verisi.get("aktiviteler") or []
    mekan_adlari = [m.get("ad", "") for m in kesif_verisi.get("mekanlar", []) if m.get("ad")]
    if not aktiviteler and not mekan_adlari:
        return _halt_payload("Planlayıcı: keşif verisinde aktivite/mekan yok.")

    aktivite_ozet = [
        {
            "tur": a.get("tur"),
            "ad": a.get("ad"),
            "sure_dakika": a.get("sure_dakika"),
            "mekan": a.get("mekan") or "yok",
            "tercih_sahibi": a.get("tercih_sahibi", ""),
        }
        for a in aktiviteler
    ]
    tercih_ozeti = kesif_verisi.get("tercih_ozeti") or []

    planlayici_prompt = f"""Sen Baş Planlayıcı Ajansın.
Aşağıdaki lojistik ve keşif verilerini kullanarak saat saat yapılandırılmış bir sürpriz hafta sonu planı oluştur.
Asla veri uydurma.

--- Katılımcılar (yapılandırılmış) ---
{json.dumps(state.get('katilimci_bilgileri', []), ensure_ascii=False)}

--- Profil tercih özeti (herkese gün içinde yer ver) ---
{json.dumps(tercih_ozeti, ensure_ascii=False)}

--- Ortak boş zamanlar (Python) ---
{json.dumps(state.get('ortak_bos_zamanlar', []), ensure_ascii=False)}

--- Lojistik planı (çıkış/varış) ---
{json.dumps(state.get('lojistik_plani', {}), ensure_ascii=False)}

--- Ortak buluşma penceresi ---
{json.dumps(state.get('ortak_bulusma_penceresi', {}), ensure_ascii=False)}

--- Lojistik Verisi ---
{json.dumps(state.get('lojistik_verisi', {}), ensure_ascii=False)}

--- Keşif Verisi (mekanlar + aktiviteler) ---
{json.dumps(kesif_verisi, ensure_ascii=False)}

--- Keşif aktiviteleri (yalnızca bunları kullan) ---
{json.dumps(aktivite_ozet, ensure_ascii=False)}

--- Reviewer Geri Bildirimi (varsa) ---
{hata_mesaji}

Kurallar:
1. Keşif satırlarında etkinlik metni BİREBİR aktiviteler[].ad olmalı — "Yemek", "Gezi", "Brunch" gibi genel etiket YASAK.
   Örnek doğru: "Canlı müzik — Siestita Cafe (Mekan: Siestita Cafe)" veya "Vanilla Restaurant (Mekan: Vanilla Restaurant)".
2. Lojistik satırları (yola çıkış, varış, otelde bekleme, dinlenme/uyku): Dayanak: lojistik yaz; (Mekan: ...) ZORUNLU DEĞİL.
3. Keşif satırları: (Mekan: ...) zorunlu. Plaj dışında "yok" YASAK — müzik/yemek/gezi için mutlaka keşifteki mekan adı.
4. Plaj: ad="Plaj/yüzme"; mekan keşifte varsa yaz, yoksa "yok".
5. Aktivite zinciri serbest: 60 dk kafe → 90 dk müze → 120 dk plaj (hepsi keşif aktivitelerinden).
6. Cumartesi/Pazar: tercih_ozeti'ndeki her katılımcıya en az bir aktivite (tercih_sahibi veya uyumlu tur).
7. sure_dakika sürelerine uy; koşullu ifade ("eğer/olursa/muhtemelen") yasak.
8. Format:
   - Cuma Akşamı / Cumartesi / Pazar
   Lojistik: HH:MM-HH:MM | <açıklama> | Dayanak: lojistik
   Keşif: HH:MM-HH:MM | <aktivite_adı> (Mekan: <ad veya yok>) | Dayanak: kesif
9. Lojistik saatleriyle çelişme; gece otel aralığında yalnızca dinlenme/uyku.
10. Hava verisinden en az bir kesin satır. Revizyon: {revizyon_sayisi}. Geri bildirim: {hata_mesaji}
"""

    try:
        sonuc = llm.invoke(
            [
                SystemMessage(content="Sen deneyimli bir seyahat planlayıcısısın."),
                HumanMessage(content=planlayici_prompt),
            ]
        )
        return {"nihai_plan": sonuc.content}
    except Exception as e:
        return _halt_payload(f"Planlayıcı LLM erişim hatası: {e}")


def reviewer_node(state: SeyahatState):
    print("\n[🛡️] Reviewer Ajan Planı Denetliyor...")
    if state.get("hata_durumu"):
        return {"siradaki_ajan": "basarisiz_kapanis"}

    revizyon_sayisi = state.get("revizyon_sayisi", 0)
    nihai_plan = state.get("nihai_plan", "") or ""
    kesif_verisi = state.get("kesif_verisi") or {
        "hava": {},
        "mekanlar": [],
        "aktiviteler": [],
        "uyari": "",
    }
    from multi_agent.kesif_layer import (
        gecerli_aktivite_adlari,
        gecerli_mekan_degerleri,
        mekan_yok_satir_izinli,
    )
    from multi_agent.plan_validate import (
        etkinlik_kesifte_var,
        kesif_satir_mi,
        plan_satirlari,
        satir_etkinlik_adi,
        satir_mekan_degeri,
    )

    norm_mekan_izinli = gecerli_mekan_degerleri(kesif_verisi)
    norm_aktivite_adlari = gecerli_aktivite_adlari(kesif_verisi)

    def _reject(reason: str) -> dict:
        yeni_sayi = revizyon_sayisi + 1
        if yeni_sayi >= 2:
            return {
                "hata_mesaji": reason,
                "siradaki_ajan": "basarisiz_kapanis",
                "revizyon_sayisi": yeni_sayi,
                "nihai_plan": (
                    "Plan doğrulanamadı\n"
                    f"Hata: {reason}\n"
                    f"Son deneme çıktısı:\n{nihai_plan}"
                ),
            }
        return {
            "hata_mesaji": reason,
            "siradaki_ajan": "yeniden_planla",
            "revizyon_sayisi": yeni_sayi,
        }

    # Programatik kontroller (LLM öncesi)
    if not norm_aktivite_adlari and not norm_mekan_izinli:
        return _reject("RED: Keşif verisinde aktivite/mekan listesi boş; plan doğrulanamaz.")

    kesif_satirlari = [s for s in plan_satirlari(nihai_plan) if kesif_satir_mi(s)]
    if not kesif_satirlari:
        return _reject("RED: Planda Dayanak: kesif satırı veya (Mekan: ...) içeren keşif aktivitesi yok.")

    uygunsuz_aktiviteler = []
    for satir in kesif_satirlari:
        etkinlik = satir_etkinlik_adi(satir)
        if not etkinlik_kesifte_var(etkinlik, norm_aktivite_adlari):
            uygunsuz_aktiviteler.append(etkinlik)

    if uygunsuz_aktiviteler:
        return _reject(
            "RED: Keşif aktivitelerinde olmayan etkinlik adları: "
            f"{', '.join(sorted(set(uygunsuz_aktiviteler))[:5])}"
        )

    uygunsuz_mekanlar = []
    for satir in kesif_satirlari:
        etkinlik = satir_etkinlik_adi(satir)
        mekan = satir_mekan_degeri(satir)
        if mekan is None:
            uygunsuz_mekanlar.append("(Mekan: alanı eksik)")
            continue
        m_norm = re.sub(r"\s+", " ", mekan.strip().lower())
        if m_norm in {"", "yok"}:
            if not mekan_yok_satir_izinli(etkinlik, kesif_verisi):
                uygunsuz_mekanlar.append(f"yok — '{etkinlik}' için geçersiz (yalnızca Plaj/yüzme)")
            continue
        if m_norm not in norm_mekan_izinli:
            uygunsuz_mekanlar.append(mekan.strip())

    if uygunsuz_mekanlar:
        return _reject(
            f"RED: Keşif verisinde olmayan mekan adları kullanıldı: {', '.join(sorted(set(uygunsuz_mekanlar))[:5])}"
        )

    if re.search(r"\b(eğer|olursa|muhtemelen)\b", nihai_plan, flags=re.IGNORECASE):
        return _reject('RED: Plan koşullu ifade içeriyor ("eğer/olursa/muhtemelen" yasak).')

    # Programatik kontroller geçtiyse deterministik ONAY ver.
    # Böylece reviewer LLM'i yeni kurallar uydurup planı gereksiz yere RED edemez.
    return {"hata_mesaji": "", "siradaki_ajan": "bitir", "revizyon_sayisi": revizyon_sayisi}