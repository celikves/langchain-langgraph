# Akıllı Seyahat ve Sürpriz Buluşma Planlayıcısı (Single Agent Demo)

Bu proje, LangChain ve yerel Büyük Dil Modelleri (Ollama) kullanılarak geliştirilmiş, dış dünyayla etkileşime girebilen (Tool Calling) reaktif bir etmen (Single Agent) simülasyonudur. Etmen; seyahat mesafesi hesaplama, hava durumu kontrolü ve bütçeye uygun mekan bulma araçlarını kullanarak otonom bir şekilde planlama yapar.

## Gereksinimler

- Python 3.9+
- [Ollama](https://ollama.com/) (Yerel LLM motoru)

## Adım Adım Kurulum ve Çalıştırma

### 1. Ollama'yı Kurma ve Modeli İndirme
Projenin çalışması için arka planda Ollama'nın yüklü ve modelin inmiş olması gerekmektedir. 

Terminalinizi açın ve Ollama'yı kurun (Linux/WSL/Mac için):
```bash
curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh