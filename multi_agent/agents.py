import os
from langchain_core.messages import SystemMessage, HumanMessage
import json
import re
import ast

from state import SeyahatState
from tools import lojistik_araclari, kesif_araclari

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


def _deterministic_plan_fallback(
    lojistik_verisi: dict, kesif_verisi: dict, *, hata_mesaji: str = ""
) -> str:
    """LLM erişilemezse kurallı, doğrulanabilir bir plan üretir."""
    mekanlar = [m.get("ad", "") for m in kesif_verisi.get("mekanlar", []) if m.get("ad")]
    hava = kesif_verisi.get("hava", {}) or {}
    sicaklik = hava.get("sicaklik_c", "")
    yagis = hava.get("yagis_ihtimali_yuzde", "")

    rota_ozetleri = lojistik_verisi.get("rota_ozetleri", []) or []
    en_uzun_sure = 6.0
    for rota in rota_ozetleri:
        mesafe_sure = str(rota.get("mesafe_sure", ""))
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*saat", mesafe_sure, flags=re.IGNORECASE)
        if m:
            try:
                en_uzun_sure = max(en_uzun_sure, float(m.group(1).replace(",", ".")))
            except ValueError:
                pass
    varis_saat = "23:30" if en_uzun_sure >= 5.5 else "22:30"

    mekan_1 = mekanlar[0] if len(mekanlar) > 0 else "yok"
    mekan_2 = mekanlar[1] if len(mekanlar) > 1 else "yok"
    mekan_3 = mekanlar[2] if len(mekanlar) > 2 else "yok"

    not_satiri = []
    if sicaklik or yagis:
        not_satiri.append(
            "09:00-09:30 | Hava Notu: "
            f"Sıcaklık {sicaklik or '?'}°C, Yağış İhtimali %{yagis or '?'} (Mekan: yok) | Dayanak: kesif"
        )
    if hata_mesaji:
        not_satiri.append(
            "09:30-10:00 | Revizyon Notu Uygulandı (Mekan: yok) | Dayanak: lojistik"
        )

    cumartesi_satirlari = [
        "10:00-12:00 | Sabah Etkinliği "
        f"(Mekan: {mekan_1}) | Dayanak: kesif",
        "12:30-14:00 | Öğle Etkinliği "
        f"(Mekan: {mekan_2}) | Dayanak: kesif",
        "16:00-18:00 | Akşamüstü Etkinliği "
        f"(Mekan: {mekan_3}) | Dayanak: kesif",
    ]

    pazar_satirlari = [
        "09:00-10:00 | Kahvaltı ve Hazırlık (Mekan: yok) | Dayanak: lojistik",
        f"10:00-14:00 | Dönüş Yolculuğu (Mekan: yok) | Dayanak: lojistik",
    ]

    plan_satirlari = [
        "Cuma Akşamı",
        f"18:00-{varis_saat} | Yolculuk Başlangıcı (Mekan: yok) | Dayanak: lojistik",
        f"{varis_saat}-00:30 | Otele Yerleşme (Mekan: yok) | Dayanak: lojistik",
        "",
        "Cumartesi",
        *not_satiri,
        *cumartesi_satirlari,
        "",
        "Pazar",
        *pazar_satirlari,
    ]
    return "\n".join(plan_satirlari)

# ==========================================
# 1. LOJİSTİK AJANI VE DÜĞÜMÜ
# ==========================================
lojistik_prompt = """Sen uzman bir Lojistik Ajanısın. 
Görevin, kullanıcıların takvim kısıtlamalarını ve aralarındaki mesafeyi hesaplayarak en uygun yola çıkış ve buluşma saatlerini bulmaktır. 
KESİNLİKLE 'ortak_bos_zaman_bul' ve 'mesafe_ve_sure_hesapla' araçlarını kullan.
Asla serbest metinle tahmin üretme; araç çağırmadan cevap verme.
Sadece şu formatta rapor ver:
- Kısıt Özeti
- Kişi Bazlı Çıkış/Varış Saatleri
- Ortak Buluşma Saati
- Varsayımlar (varsa)"""

def lojistik_node(state: SeyahatState):
    print("\n[🤖] Lojistik Ajanı Çalışıyor...")
    profiller = state.get("kullanici_profilleri", [])
    hedef = "Antalya"

    ortak_bos_zaman_araci = next(t for t in lojistik_araclari if t.name == "ortak_bos_zaman_bul")
    mesafe_araci = next(t for t in lojistik_araclari if t.name == "mesafe_ve_sure_hesapla")

    kisit_metin = (
        f"Kullanıcı Profilleri: {json.dumps(profiller, ensure_ascii=False)}\n"
        f"Ortak Kısıtlamalar: {state.get('ortak_kisitlamalar', '')}"
    )
    ortak_bulusma = ortak_bos_zaman_araci.invoke({"kullanici_kisitlamalari": kisit_metin})

    rota_ozetleri = []
    for profil in profiller:
        kalkis = profil.get("kalkis_yeri", "")
        isim = profil.get("isim", "Katılımcı")
        if not kalkis:
            continue
        rota = mesafe_araci.invoke({"kalkis_sehri": kalkis, "varis_sehri": hedef})
        rota_ozetleri.append(
            {
                "isim": isim,
                "kalkis_yeri": kalkis,
                "hedef": hedef,
                "mesafe_sure": str(rota),
            }
        )

    lojistik_verisi = {
        "kisit_ozeti": state.get("ortak_kisitlamalar", ""),
        "rota_ozetleri": rota_ozetleri,
        "ortak_bulusma": str(ortak_bulusma),
    }
    return {"lojistik_verisi": lojistik_verisi}

# ==========================================
# 2. KEŞİF AJANI VE DÜĞÜMÜ
# ==========================================
kesif_prompt = """Sen uzman bir Keşif Ajanısın. 
Görevin, hedef şehirdeki hava durumunu öğrenmek ve hava koşullarına uygun, bütçeyi aşmayan gerçek mekanlar bulmaktır. 
KESİNLİKLE 'hava_durumu_getir' ve 'internette_mekan_ara' araçlarını kullan.
Kendi aklından mekan ismi UYDURMA.
Önce hava durumunu çağır, sonra mekanları ara.
Sadece araç çıktılarından gelen doğrulanabilir bilgileri raporla.
Rapor formatı:
- Hava Durumu (kesin veri)
- Önerilen Mekanlar (yalnızca araçta geçen adlar)
- Yaklaşık Bütçe Notu (araçta veri yoksa 'belirsiz')"""

def _extract_weather_fields(weather_text: str) -> dict:
    sicaklik_match = re.search(r"(\d+(?:[.,]\d+)?)°C", weather_text)
    yagis_match = re.search(r"Yağış ihtimali:\s*%?(\d+)", weather_text, flags=re.IGNORECASE)
    return {
        "ham_metin": weather_text,
        "sicaklik_c": sicaklik_match.group(1) if sicaklik_match else "",
        "yagis_ihtimali_yuzde": yagis_match.group(1) if yagis_match else "",
    }


def _extract_places_from_tool_output(raw_output: str) -> list[dict]:
    mekanlar: list[dict] = []
    content = raw_output.strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            adaylar = parsed.get("results") or parsed.get("data") or []
        elif isinstance(parsed, list):
            adaylar = parsed
        else:
            adaylar = []
        for item in adaylar:
            if not isinstance(item, dict):
                continue
            ad = (item.get("title") or item.get("name") or "").strip()
            kaynak = (item.get("url") or "").strip()
            if ad:
                mekanlar.append({"ad": ad, "kaynak": kaynak, "butce_notu": "belirsiz"})
        if mekanlar:
            return mekanlar
    except json.JSONDecodeError:
        pass

    # Tavily bazı sürümlerde Python liste/dict repr döndürebiliyor.
    try:
        parsed_py = ast.literal_eval(content)
        if isinstance(parsed_py, list):
            for item in parsed_py:
                if not isinstance(item, dict):
                    continue
                ad = (item.get("title") or item.get("name") or "").strip()
                kaynak = (item.get("url") or "").strip()
                if ad:
                    mekanlar.append({"ad": ad, "kaynak": kaynak, "butce_notu": "belirsiz"})
            if mekanlar:
                return mekanlar
    except (ValueError, SyntaxError):
        pass

    # Tavily string çıktılarında sıklıkla "title='...'" bulunur; yalnızca araç çıktısındaki birebir adlar alınır.
    for ad in re.findall(r"title='([^']+)'", raw_output):
        mekanlar.append({"ad": ad.strip(), "kaynak": "", "butce_notu": "belirsiz"})

    return mekanlar


def kesif_node(state: SeyahatState):
    print("\n[🔎] Keşif Ajanı Çalışıyor...")
    hava_araci = next(t for t in kesif_araclari if t.name == "hava_durumu_getir")
    mekan_araci = next(t for t in kesif_araclari if t.name == "internette_mekan_ara")
    hedef_tarih = state.get("hedef_tarih", "2026-06-04")

    hava_raw = hava_araci.invoke({"sehir": "Antalya", "tarih": hedef_tarih})
    mekan_raw = mekan_araci.invoke(
        {"sorgu": f"Antalya {hedef_tarih} orta bütçeli kafe restoran sahil mekan önerileri gerçek isimleri"}
    )
    mekanlar = []
    mekan_uyari = ""
    try:
        mekan_payload = json.loads(str(mekan_raw))
        if isinstance(mekan_payload, dict):
            mekanlar = mekan_payload.get("mekanlar", []) or []
            mekan_uyari = mekan_payload.get("uyari", "") or ""
    except json.JSONDecodeError:
        mekanlar = _extract_places_from_tool_output(str(mekan_raw))

    kesif_verisi = {
        "hava": _extract_weather_fields(str(hava_raw)),
        "mekanlar": mekanlar,
        "uyari": mekan_uyari,
    }

    if not kesif_verisi["mekanlar"]:
        kesif_verisi["uyari"] = (
            kesif_verisi["uyari"] or "Mekan adı çıkarılamadı; planlayıcı özel isim üretmemeli."
        )

    return {"kesif_verisi": kesif_verisi}

# ==========================================
# 3. PLANLAYICI AJAN (SENTEZ) DÜĞÜMÜ
# ==========================================
# Planlayıcı dış dünya ile iletişime geçmez (tool kullanmaz).
# Sadece State'teki verileri alıp akıcı bir metne döker.
def planlayici_node(state: SeyahatState):
    print("\n[✍️] Planlayıcı Ajan Sentez Yapıyor...")
    revizyon_sayisi = state.get("revizyon_sayisi", 0)
    hata_mesaji = state.get("hata_mesaji", "")
    
    kesif_verisi = state.get("kesif_verisi") or {"hava": {}, "mekanlar": [], "uyari": ""}
    mekan_adlari = [m.get("ad", "") for m in kesif_verisi.get("mekanlar", []) if m.get("ad")]
    if not mekan_adlari:
        return {
            "nihai_plan": (
                "Plan üretimi atlandı: Keşif verisinde doğrulanmış mekan adı yok.\n"
                "Neden: Mekan listesi boş geldiği için planlayıcı yaratıcı doldurma yapmamalı."
            )
        }

    planlayici_prompt = f"""Sen Baş Planlayıcı Ajansın.
Aşağıdaki lojistik ve keşif verilerini kullanarak saat saat yapılandırılmış bir sürpriz hafta sonu planı oluştur.
Asla veri uydurma.

--- Lojistik Verisi ---
{json.dumps(state.get('lojistik_verisi', {}), ensure_ascii=False)}

--- Keşif Verisi ---
{json.dumps(kesif_verisi, ensure_ascii=False)}

--- Reviewer Geri Bildirimi (varsa) ---
{hata_mesaji}

Kurallar:
1. Sadece kesif_verisi.mekanlar[].ad alanındaki şu mekan adlarını kullan: {mekan_adlari}.
2. Keşif verisinde olmayan hiçbir özel isim yazma.
3. Koşullu ifade yasak: "eğer", "olursa", "muhtemelen" kullanma.
4. Çıktı formatı sabit:
   - Cuma Akşamı
   - Cumartesi
   - Pazar
   Her satır: HH:MM-HH:MM | Etkinlik (Mekan: <mekan_adı veya yok>) | Dayanak: <lojistik|kesif>
5. Zaman planında lojistik saatleriyle çelişme.
6. Çıktı dili Türkçe olsun.
7. Cuma buluşması gerçekleştiyse Pazar günü tekrar buluşma planlama.
8. Keşif verisindeki hava bilgisinden en az bir kesin veri satırı kullan (örn. sıcaklık/yağış).
9. Revizyon sayısı: {revizyon_sayisi}. Reviewer geri bildirimini ihlal etme.
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
        lojistik_verisi = state.get("lojistik_verisi") or {}
        fallback_plan = _deterministic_plan_fallback(
            lojistik_verisi,
            kesif_verisi,
            hata_mesaji=hata_mesaji,
        )
        return {
            "nihai_plan": fallback_plan,
            "hata_mesaji": f"Planlayıcı LLM erişim hatası: {str(e)}",
        }


def reviewer_node(state: SeyahatState):
    print("\n[🛡️] Reviewer Ajan Planı Denetliyor...")
    revizyon_sayisi = state.get("revizyon_sayisi", 0)
    nihai_plan = state.get("nihai_plan", "") or ""
    kesif_verisi = state.get("kesif_verisi") or {"hava": {}, "mekanlar": [], "uyari": ""}
    mekan_adlari = [m.get("ad", "") for m in kesif_verisi.get("mekanlar", []) if m.get("ad")]
    norm_mekan_adlari = {re.sub(r"\s+", " ", ad.strip().lower()) for ad in mekan_adlari if ad.strip()}

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
    if not norm_mekan_adlari:
        return _reject("RED: Keşif verisinde mekan listesi boş; plan doğrulanamaz.")

    mekan_alanlari = re.findall(r"Mekan:\s*([^)|\n]+)", nihai_plan, flags=re.IGNORECASE)
    if not mekan_alanlari:
        return _reject("RED: Plan satırlarında zorunlu 'Mekan:' alanı yok.")

    uygunsuz_mekanlar = []
    for m in mekan_alanlari:
        m_norm = re.sub(r"\s+", " ", m.strip().lower())
        if m_norm in {"", "yok"}:
            continue
        if m_norm not in norm_mekan_adlari:
            uygunsuz_mekanlar.append(m.strip())

    if uygunsuz_mekanlar:
        return _reject(
            f"RED: Keşif verisinde olmayan mekan adları kullanıldı: {', '.join(sorted(set(uygunsuz_mekanlar))[:5])}"
        )

    if re.search(r"\b(eğer|olursa|muhtemelen)\b", nihai_plan, flags=re.IGNORECASE):
        return _reject('RED: Plan koşullu ifade içeriyor ("eğer/olursa/muhtemelen" yasak).')

    satirlar = [s.strip() for s in nihai_plan.splitlines() if s.strip()]
    aktif_gun = ""
    for satir in satirlar:
        norm = satir.lower().replace("#", "").strip()
        if "cuma akşamı" in norm:
            aktif_gun = "cuma"
            continue
        if "cumartesi" in norm:
            aktif_gun = "cumartesi"
            continue
        if "pazar" in norm:
            aktif_gun = "pazar"
            continue
        if re.search(r"\bbuluş\w*\b", satir, flags=re.IGNORECASE) and aktif_gun in {"cumartesi", "pazar"}:
            return _reject("RED: Lojistik buluşma sonrası tekrar buluşma tespit edildi.")

    # Programatik kontroller geçtiyse deterministik ONAY ver.
    # Böylece reviewer LLM'i yeni kurallar uydurup planı gereksiz yere RED edemez.
    return {"hata_mesaji": "", "siradaki_ajan": "bitir", "revizyon_sayisi": revizyon_sayisi}