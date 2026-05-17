# Akıllı Seyahat ve Sürpriz Buluşma Planlayıcısı (Single Agent Demo)

Bu proje, LangChain ve yerel Büyük Dil Modelleri (Ollama) kullanılarak geliştirilmiş, dış dünyayla etkileşime girebilen (Tool Calling) reaktif bir etmen (Single Agent) simülasyonudur. Etmen; seyahat mesafesi hesaplama, hava durumu kontrolü ve bütçeye uygun mekan bulma araçlarını kullanarak otonom bir şekilde planlama yapar.

## Gereksinimler

- Python 3.9+
- [Ollama](https://ollama.com/) (Yerel LLM motoru)

## Adım Adım Kurulum ve Çalıştırma

### 1. Sanal Ortam (Virtual Environment) Oluşturma
Proje kütüphanelerinin bilgisayarınızdaki diğer Python projeleriyle çakışmasını önlemek için izole bir çalışma ortamı oluşturulması şiddetle tavsiye edilir.

Terminalinizi projenin ana klasöründe açın ve aşağıdaki komutlarla sanal ortamı oluşturup aktifleştirin:

**Mac ve Linux (veya WSL) için:**
```bash
python3 -m venv .venv
source .venv/bin/activate

```

**Windows için:**

```bash
python -m venv .venv
.venv\Scripts\activate

```

### 2. Ollama'yı Kurma ve Modeli İndirme

Projenin çalışması için arka planda Ollama'nın yüklü ve modelin inmiş olması gerekmektedir.

Terminalinizi açın ve Ollama'yı kurun (Linux/WSL/Mac için):

```bash
curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh

```

### 3. Gerekli Kütüphanelerin Kurulumu

Sanal ortamınız aktifken (satır başında `(.venv)` yazarken), projenin ihtiyaç duyduğu LangChain ve web arama araçlarını yüklemek için aşağıdaki komutu çalıştırın:

```bash
pip install langchain-community duckduckgo-search

```
pip install python-dotenv
```

```


### LangSmith İzleme (Tracing) Entegrasyonu

LangSmith'i projeye dahil etmek için kodun mimarisini değiştirmemize gerek yok, sadece ortam değişkenlerini (environment variables) sisteme tanıtmamız yeterli.

#### 1. Adım: Gerekli Paketi Yükle

Terminalde çevre değişkenlerini güvenle okuyabilmemiz için `python-dotenv` paketini yükle:

```bash
pip install python-dotenv

```

#### 2. Adım: LangSmith API Anahtarı Al

1. [smith.langchain.com](https://smith.langchain.com/) adresine git ve ücretsiz bir hesap aç.
2. Sol alt köşedeki **Settings (Ayarlar)** menüsünden **API Keys** bölümüne girip yeni bir anahtar (Personal Access Token) oluştur.

#### 3. Adım: `.env` Dosyası Oluştur

Proje klasörünün ana dizininde (etmentabanlı klasörü içinde) uzantısı olmayan `.env` adında gizli bir dosya oluştur ve içine şu bilgileri yaz (API anahtarını kendi aldığın anahtarla değiştir):

```text

LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
LANGSMITH_API_KEY="lsv2_your-api-key"
LANGSMITH_PROJECT="ETGY Langchain"
GEMINI_API_KEY="your-api-key"

```


