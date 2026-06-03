import os
import json
import re
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langsmith import traceable

from multi_agent.state import SeyahatState
from multi_agent.tools import lojistik_araclari
from multi_agent.tracing import invoke_tool

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
@traceable(name="Lojistik Ajanı", run_type="chain", tags=["multi-agent", "lojistik"])
def lojistik_node(state: SeyahatState, config: RunnableConfig):
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
            invoke_tool(
                trafik_araci,
                {
                    "kalkis_sehir": kalkis,
                    "varis_sehir": varis,
                    "kalkis_saati": saat,
                    "tarih": tarih,
                },
                config,
            )
        )

    def bilet_fn(tarih: str, kalkis: str, varis: str, tercih: str) -> str:
        return str(
            invoke_tool(
                bilet_araci,
                {"tarih": tarih, "kalkis": kalkis, "varis": varis, "tercih": tercih},
                config,
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
        "son_dugum": "lojistik",
    }

# ==========================================
# 2. KEŞİF AJANI — kesif_subgraph.py (paralel tür uzmanları)
# ==========================================
# Eski tek düğüm: multi_agent/kesif_subgraph.py içindeki Send + merge mimarisine taşındı.
# 3. PLANLAYICI AJAN (SENTEZ) DÜĞÜMÜ
# ==========================================
# Planlayıcı dış dünya ile iletişime geçmez (tool kullanmaz).
# Sadece State'teki verileri alıp akıcı bir metne döker.
@traceable(name="Planlayıcı Ajanı", run_type="llm", tags=["multi-agent", "planlayici"])
def planlayici_node(state: SeyahatState, config: RunnableConfig):
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

    from multi_agent.plan_builder import deterministik_plan_olustur

    if revizyon_sayisi == 0 and not (hata_mesaji or "").strip():
        try:
            plan = deterministik_plan_olustur(state)
            if plan and "**Keşif:**" in plan:
                print("  ✓ Deterministik plan (iskelet + slot yerleştirme)")
                return {"nihai_plan": plan, "son_dugum": "planlayici"}
        except Exception as e:
            print(f"  (i) Deterministik plan atlandı, LLM yedeği: {e}")

    aktivite_ozet = [
        {
            "tur": a.get("tur"),
            "ad": a.get("ad"),
            "sure_dakika": a.get("sure_dakika"),
            "mekan": a.get("mekan") or "",
            "mekan_zorunlu": a.get("mekan_zorunlu", True),
            "tercih_sahibi": a.get("tercih_sahibi", ""),
        }
        for a in aktiviteler
    ]
    izinli_adlar = [a.get("ad", "") for a in aktiviteler if a.get("ad")]
    tercih_ozeti = kesif_verisi.get("tercih_ozeti") or []

    iskelet = ""
    try:
        iskelet = deterministik_plan_olustur(state)
    except Exception:
        pass

    planlayici_prompt = f"""Sen Baş Planlayıcı Ajansın.
Aşağıdaki lojistik ve keşif verilerini kullanarak saat saat yapılandırılmış bir sürpriz hafta sonu planı oluştur.
Asla veri uydurma.

--- Deterministik iskelet (Lojistik satırlarını AYNEN koru; yalnızca Keşif satırlarını düzelt) ---
{iskelet or "(iskelet üretilemedi)"}

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

--- İZİNLİ aktivite adları (satırda BİREBİR kopyala) ---
{chr(10).join(f"- {ad}" for ad in izinli_adlar)}

--- Reviewer Geri Bildirimi (varsa) ---
{hata_mesaji}

Kurallar:
1. Keşif satırında etkinlik metni = aktiviteler[].ad (birebir kopyala). Liste dışı etiket uydurma.
2. Mekan kuralları:
   - mekan_zorunlu=true → (Mekan: <ad>) zorunlu; aktivite.mekan ile birebir eşleşmeli.
   - mekan_zorunlu=false → (Mekan: yok) yazılabilir; mekan yazsan da aktivite.mekan ile eşleşmeli.
   - Plaj aktiviteleri "Plaj/yüzme — <mekan adı>" biçimindedir; adı birebir kopyala.
3. Lojistik: Dayanak: lojistik. Cuma akşamı yalnızca lojistik (keşif yok).
4. Format (revizyonda da AYNEN koru — değiştirme):
   - **Keşif:** HH:MM-HH:MM | <aktivite_adı> (Mekan: <ad veya yok>) | Dayanak: kesif
   - **Lojistik:** HH:MM-HH:MM | <açıklama> | Dayanak: lojistik
   Yasak: - **HH:MM-HH:MM** | ... veya Dayanak: keşif (Türkçe ş) — yalnızca yukarıdaki format geçerli.
5. Ortak boş zamanlara uy; sure_dakika'ya yakın süreler; koşullu ifade yasak.
6. Hava verisinden en az bir satır. Revizyon: {revizyon_sayisi}. Geri bildirim: {hata_mesaji}
"""

    try:
        sonuc = llm.invoke(
            [
                SystemMessage(content="Sen deneyimli bir seyahat planlayıcısısın."),
                HumanMessage(content=planlayici_prompt),
            ],
            config=config,
        )
        return {"nihai_plan": sonuc.content, "son_dugum": "planlayici"}
    except Exception as e:
        return _halt_payload(f"Planlayıcı LLM erişim hatası: {e}")


@traceable(name="Reviewer Ajanı", run_type="chain", tags=["multi-agent", "reviewer"])
def reviewer_node(state: SeyahatState, config: RunnableConfig):
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
        aktivite_bul,
        eksik_turleri_hesapla,
        gecerli_aktivite_adlari,
        gecerli_mekan_degerleri,
    )
    from multi_agent.plan_validate import (
        kesif_satir_dogrula,
        kesif_satir_mi,
        plan_satirlari,
        satir_etkinlik_adi,
        satir_mekan_degeri,
        uydurma_etiket_mi,
    )

    norm_mekan_izinli = gecerli_mekan_degerleri(kesif_verisi)
    norm_aktivite_adlari = gecerli_aktivite_adlari(kesif_verisi)
    kategoriler = state.get("kesif_kategorileri") or []
    profiller = state.get("kullanici_profilleri") or []
    eksik_turler = eksik_turleri_hesapla(kesif_verisi, kategoriler, profiller)

    def _reject(reason: str, kontrol: str = "") -> dict:
        yeni_sayi = revizyon_sayisi + 1
        if eksik_turler and yeni_sayi < 2:
            sonraki: str = "hedefli_kesif"
        elif yeni_sayi >= 2:
            sonraki = "basarisiz_kapanis"
        else:
            sonraki = "yeniden_planla"
        kalite_raporu = {
            "onay": False,
            "eksik_turler": eksik_turler,
            "hata_kodu": kontrol,
            "mesaj": reason,
        }
        print(f"  ✗ RED [{kontrol or 'dogrulama'}]: {reason}")
        if eksik_turler:
            print(f"  → Eksik türler: {', '.join(eksik_turler)}")
        print(f"  → Revizyon {yeni_sayi}/2 — yönlendirme: {sonraki}")
        if yeni_sayi >= 2:
            return {
                "hata_mesaji": reason,
                "siradaki_ajan": "basarisiz_kapanis",
                "revizyon_sayisi": yeni_sayi,
                "kalite_raporu": kalite_raporu,
                "son_dugum": "reviewer",
                "nihai_plan": (
                    "Plan doğrulanamadı\n"
                    f"Hata: {reason}\n"
                    f"Son deneme çıktısı:\n{nihai_plan}"
                ),
            }
        return {
            "hata_mesaji": reason,
            "siradaki_ajan": sonraki,
            "revizyon_sayisi": yeni_sayi,
            "kalite_raporu": kalite_raporu,
            "son_dugum": "reviewer",
        }

    tum_satirlar = plan_satirlari(nihai_plan)
    kesif_satirlari = [s for s in tum_satirlar if kesif_satir_mi(s)]
    print(f"  → Parser: {len(tum_satirlar)} zaman satırı, {len(kesif_satirlari)} keşif satırı")

    if not norm_aktivite_adlari and not norm_mekan_izinli:
        return _reject(
            "RED: Keşif verisinde aktivite/mekan listesi boş; plan doğrulanamaz.",
            kontrol="kesif_verisi",
        )

    if not kesif_satirlari:
        ornek = [
            ln.strip()[:100]
            for ln in nihai_plan.splitlines()
            if re.search(r"\d{2}:\d{2}-\d{2}:\d{2}", ln)
        ][:2]
        if ornek:
            print(f"  (i) Ham satır örneği: {ornek[0]}")
        return _reject(
            "RED: Planda Dayanak: kesif satırı veya (Mekan: ...) içeren keşif aktivitesi yok.",
            kontrol="kesif_satir_sayisi",
        )

    uygunsuz_aktiviteler: list[str] = []
    uygunsuz_mekanlar: list[str] = []
    uygunsuz_sehir_mekanlar: list[str] = []
    hedef_sehir = (kesif_verisi.get("hedef_sehir") or state.get("hedef_sehir") or "").strip()
    for satir in kesif_satirlari:
        etkinlik = satir_etkinlik_adi(satir)
        mekan = satir_mekan_degeri(satir)
        ok, tur = kesif_satir_dogrula(satir, kesif_verisi)
        if ok:
            continue
        if tur == "aktivite":
            if uydurma_etiket_mi(etkinlik, kesif_verisi):
                uygunsuz_aktiviteler.append(f"{etkinlik} (uydurma etiket)")
            else:
                uygunsuz_aktiviteler.append(etkinlik or "(boş)")
        elif tur == "mekan_sehir":
            uygunsuz_sehir_mekanlar.append(
                f"{mekan or '(eksik)'} — hedef dışı şehir (hedef: {hedef_sehir or '?'})"
            )
        elif tur == "mekan":
            beklenen = (aktivite_bul(kesif_verisi, etkinlik, plan_mekan=mekan) or {}).get("mekan") or "?"
            uygunsuz_mekanlar.append(
                f"{mekan or '(eksik)'} — '{etkinlik}' (beklenen: {beklenen})"
            )
        else:
            uygunsuz_aktiviteler.append("(satır parse edilemedi)")

    if uygunsuz_aktiviteler:
        ornek_ad = [a.get("ad", "") for a in (kesif_verisi.get("aktiviteler") or [])[:4]]
        return _reject(
            "RED: Etkinlik adı keşif listesinde yok veya uydurma: "
            f"{', '.join(uygunsuz_aktiviteler[:5])}. "
            f"İzinli örnekler: {', '.join(ornek_ad)}",
            kontrol="aktivite_adi",
        )

    if uygunsuz_sehir_mekanlar:
        return _reject(
            "RED: Mekan hedef şehirle uyumsuz (başka şehir adı içeriyor): "
            f"{', '.join(uygunsuz_sehir_mekanlar[:5])}",
            kontrol="mekan_sehir",
        )

    if uygunsuz_mekanlar:
        return _reject(
            "RED: Mekan satırı aktivite kaydıyla uyuşmuyor: "
            f"{', '.join(uygunsuz_mekanlar[:5])}",
            kontrol="mekan_adi",
        )

    if re.search(r"\b(eğer|olursa|muhtemelen)\b", nihai_plan, flags=re.IGNORECASE):
        return _reject(
            'RED: Plan koşullu ifade içeriyor ("eğer/olursa/muhtemelen" yasak).',
            kontrol="kosullu_ifade",
        )

    pencere = state.get("ortak_bulusma_penceresi") or {}
    erken = pencere.get("erken_gelen_aksiyonlari") or []
    if erken:
        plan_lower = nihai_plan.lower()
        if not any((a.get("isim") or "").lower() in plan_lower for a in erken):
            return _reject(
                "RED: Erken gelen katılımcılar için otel bekleme lojistik satırı planda yok.",
                kontrol="erken_gelen",
            )

    gece_bas = (pencere.get("gece_otel_baslangic_saat_metin") or "").strip()
    gece_bit = (pencere.get("gece_otel_bitis_saat_metin") or "").strip()
    if gece_bas and gece_bit and f"{gece_bas}-{gece_bit}" not in nihai_plan:
        if gece_bas not in nihai_plan or "otel" not in nihai_plan.lower():
            return _reject(
                f"RED: Gece otel dinlenme penceresi ({gece_bas}–{gece_bit}) planda eksik.",
                kontrol="gece_otel",
            )

    slots = state.get("ortak_bos_zamanlar") or []
    donus_slot = next(
        (
            s
            for s in reversed(slots)
            if datetime.fromisoformat(s["baslangic"]).weekday() == 6
            and datetime.fromisoformat(s["baslangic"]).hour >= 20
        ),
        None,
    )
    if donus_slot:
        donus_aralik = (
            f"{datetime.fromisoformat(donus_slot['baslangic']).strftime('%H:%M')}-"
            f"{datetime.fromisoformat(donus_slot['bitis']).strftime('%H:%M')}"
        )
        lojistik_satirlar = [
            s
            for s in tum_satirlar
            if re.search(r"Dayanak:\s*lojistik", s, re.I) and donus_aralik in s
        ]
        if not lojistik_satirlar:
            return _reject(
                f"RED: Pazar dönüş lojistik penceresi ({donus_aralik}) planda eksik.",
                kontrol="pazar_donus",
            )

    print(f"  ✓ ONAY — {len(kesif_satirlari)} keşif satırı doğrulandı")
    return {
        "hata_mesaji": "",
        "siradaki_ajan": "bitir",
        "revizyon_sayisi": revizyon_sayisi,
        "kalite_raporu": {
            "onay": True,
            "eksik_turler": [],
            "hata_kodu": "",
            "mesaj": "",
        },
        "son_dugum": "reviewer",
    }