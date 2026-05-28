from langgraph.graph import StateGraph, START, END
from state import SeyahatState
from agents import lojistik_node, kesif_node, planlayici_node

# ==========================================
# 1. GRAPH'IN (AKISIN) İNŞASI
# ==========================================

# State (Hafıza) sınıfımızı baz alan bir grafik başlatıyoruz
workflow = StateGraph(SeyahatState)

# Düğümleri (Ajanları) ekliyoruz
workflow.add_node("lojistik", lojistik_node)
workflow.add_node("kesif", kesif_node)
workflow.add_node("planlayici", planlayici_node)

# Kenarları (Akış Sırasını) bağlıyoruz
workflow.add_edge(START, "lojistik")        # Başlangıç -> Lojistik Ajanı
workflow.add_edge("lojistik", "kesif")      # Lojistik Ajanı -> Keşif Ajanı
workflow.add_edge("kesif", "planlayici")    # Keşif Ajanı -> Planlayıcı Ajan
workflow.add_edge("planlayici", END)        # Planlayıcı Ajan -> Bitiş

# Sistemi derleyip çalıştırılabilir hale getiriyoruz
app = workflow.compile()

# ==========================================
# 2. ÇALIŞTIRMA VE TEST
# ==========================================

if __name__ == "__main__":
    print("\n[🚀] Multi-Agent Seyahat Sistemi Başlatılıyor...\n")
    
    # Sistemin dışarıdan alacağı dinamik bağlamı (JSON mantığıyla) simüle ediyoruz
    baslangic_durumu = {
        "messages": [],
        "kullanici_profilleri": [
            {"isim": "Vesile", "kalkis_yeri": "Akhisar", "mesai_bitis": "17:00", "rol": "Sürprizi organize eden"},
            {"isim": "Kız Arkadaşı", "kalkis_yeri": "Ankara", "mesai_bitis": "Serbest", "rol": "Sürpriz yapılacak kişi"}
        ],
        "ortak_kisitlamalar": "Hedef şehir Antalya. Sürpriz bir hafta sonu tatili. Bütçe: Orta. Cuma günü 17:00 mesai bitişi kesinlikle hesaba katılmalı."
    }
    
    # Ajanların adım adım neler yaptığını görmek için stream kullanıyoruz
    print("Sistem adımları izleniyor...\n" + "-"*50)
    for cikti in app.stream(baslangic_durumu):
        for dugum_adi, dugum_verisi in cikti.items():
            print(f"✅ {dugum_adi.upper()} DÜĞÜMÜ GÖREVİNİ TAMAMLADI.")
            
    # Tüm işlemler bittikten sonra graph'tan çıkan son durumu (State) alıyoruz
    # stream yerine invoke kullansaydık doğrudan son state'i alırdık, 
    # ancak stream ile adım adım izledikten sonra son state'i almak için tekrar invoke edebilir 
    # veya çıktının en son elemanını yakalayabiliriz. En temizi doğrudan invoke etmektir.
    
    print("\n" + "="*70)
    print("=== 🎯 NİHAİ SÜRPRİZ PLANI ===")
    print("="*70 + "\n")
    
    # Nihai çıktıyı tam metin olarak almak için invoke
    sonuc_state = app.invoke(baslangic_durumu)
    print(sonuc_state.get("nihai_plan", "Plan oluşturulamadı."))