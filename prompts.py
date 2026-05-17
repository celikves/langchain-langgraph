"""Dinamik sistem promptu — ChatPromptTemplate + durum enjeksiyonu."""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Jenerik şablon (senaryo bağımsız)
SYSTEM_TEMPLATE = """Sen üst düzey, otonom bir asistansın. Görevin: {ana_gorev}.

Kullanıcı Profilleri ve Mevcut Durum:
{kullanici_baglami}

Zaman Kısıtlamaları:
{zaman_kisitlamalari}

Ek kısıtlar:
{ortak_kisitlamalar}

Şu adımları KESİN bir sırayla izle:
{is_akis_adimlari}

Kurallar:
{ozel_kurallar}"""

# Kod içi örnek (test / dokümantasyon); üretimde data/sessions/*.json kullanılır
EXAMPLE_PROMPT_DEFAULTS = {
    "ana_gorev": "Katılımcıların ortak hedefte buluşması için lojistik ve etkinlik planı.",
    "kullanici_baglami": "(Oturum başlatılmadan önce JSON profillerinden doldurulur.)",
    "zaman_kisitlamalari": "(Çalışma anında datetime ile doldurulur.)",
    "ortak_kisitlamalar": "",
    "is_akis_adimlari": "Takvim → rota → hava → mekan arama → saatlik plan.",
    "ozel_kurallar": "Hesapları kullanıcıya devretme; gerçek mekan isimleri kullan.",
}


def build_prompt_template() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_TEMPLATE),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )


def format_system_prompt(**overrides) -> str:
    return SYSTEM_TEMPLATE.format(**{**EXAMPLE_PROMPT_DEFAULTS, **overrides})


# Geriye dönük uyumluluk
REACT_SYSTEM_TEMPLATE = SYSTEM_TEMPLATE
build_react_prompt_template = build_prompt_template
format_react_system_prompt = format_system_prompt
SCENARIO_DEFAULTS = EXAMPLE_PROMPT_DEFAULTS
