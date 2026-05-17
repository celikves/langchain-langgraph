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