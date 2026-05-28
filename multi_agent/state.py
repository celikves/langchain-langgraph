from typing import TypedDict, Annotated, List, Dict, Any
import operator
from langchain_core.messages import BaseMessage

class SeyahatState(TypedDict):
    """
    Multi-Agent sistemin ortak hafızası.
    Tüm ajanlar buradaki verileri okur ve sadece kendi yetki alanlarındaki kısımları günceller.
    """
    
    # LangGraph'ın temel gereksinimi: Mesaj geçmişi
    # operator.add, yeni gelen mesajların öncekilerin üzerine yazılmasını engeller, listeye ekler.
    messages: Annotated[list[BaseMessage], operator.add]
    
    # --- DİNAMİK BAĞLAM (Dışarıdan Beslenecek) ---
    kullanici_profilleri: List[Dict[str, Any]] # 2, 3 veya N adet kullanıcının JSON profili
    ortak_kisitlamalar: str                    # Örn: "Cuma 17:00 mesai bitişi"
    
    # --- AJANLARIN ÇALIŞMA ALANLARI ---
    # Lojistik Ajanı rotaları hesaplayıp buraya yazar
    lojistik_verisi: str
    
    # Keşif Ajanı hava durumunu ve mekanları bulup buraya yazar
    kesif_verisi: str
    
    # Planlayıcı Ajan nihai taslağı oluşturup buraya yazar
    nihai_plan: str
    
    # --- ORKESTRASYON VE KONTROL ---
    hata_mesaji: str       # Reviewer bir kısıt ihlali bulursa hatayı buraya yazar
    siradaki_ajan: str     # Supervisor'ın yönlendirmeyi yapacağı değişken