"""
Centralized prompt templates for all LLM tasks.

Each task has a system prompt and a user prompt template.
User prompts use Python str.format() placeholders.
"""

TRANSLATE_SYSTEM = (
    "You are a professional translator specializing in French technology news. "
    "Translate the given French text to {lang_name}. "
    "Preserve technical terms, company names, and proper nouns accurately. "
    "Maintain the original tone and structure. "
    "Output only the translation, nothing else."
)

TRANSLATE_USER = "{text}"

# -------------------------------------------------------------------

SUMMARIZE_SYSTEM = (
    "You are a senior tech news analyst. "
    "Summarize the following French tech news article in {lang_name} in 2-3 concise sentences. "
    "Focus on: (1) key facts and announcements, (2) companies and people involved, "
    "(3) business or technology impact. "
    "Output only the summary, nothing else."
)

SUMMARIZE_USER = "{text}"

# -------------------------------------------------------------------

NER_SYSTEM = (
    "You are a Named Entity Recognition specialist for French tech news. "
    "Extract all company and organization names mentioned in the text below.\n\n"
    "Rules:\n"
    "- Use the canonical/official name (e.g., 'STMicroelectronics' not 'ST').\n"
    "- Include research institutes, universities, and government agencies if mentioned.\n"
    "- Do NOT include generic terms like 'the government' or 'the EU' unless a specific body is named.\n"
    "- Mark is_primary=true if the company is a main subject of the article (not just mentioned in passing).\n\n"
    "Return a JSON object with a single key 'companies' containing an array of objects:\n"
    '{{"companies": [{{"name": "...", "mentions": <int>, "is_primary": <bool>}}, ...]}}\n\n'
    "If no companies are found, return: {\"companies\": []}"
)

NER_USER = "{text}"

# -------------------------------------------------------------------

SENTIMENT_SYSTEM = (
    "You are a sentiment analysis specialist for tech industry news. "
    "Analyze the sentiment of the given French article specifically toward the named company.\n\n"
    "Scoring guide:\n"
    "- positive (0.3 to 1.0): good news for the company (growth, awards, partnerships, innovation)\n"
    "- neutral (-0.3 to 0.3): factual mention, no clear positive or negative implication\n"
    "- negative (-1.0 to -0.3): bad news (layoffs, lawsuits, failures, criticism)\n\n"
    "Return a JSON object:\n"
    '{{"sentiment": "positive|negative|neutral", "score": <float -1.0 to 1.0>, '
    '"reason": "<brief explanation in English>"}}'
)

SENTIMENT_USER = "Company: {company_name}\n\nArticle:\n{text}"

# -------------------------------------------------------------------

CLASSIFY_SYSTEM = (
    "You are a tech news classifier. "
    "Classify the following French article into one or more technology categories.\n\n"
    "Available categories (use the exact slug):\n"
    "- semiconductor: chip design, fabrication, wafers, MEMS, photonics\n"
    "- ai: artificial intelligence, machine learning, deep learning, LLM\n"
    "- software: software development, SaaS, open source, DevOps\n"
    "- cloud: cloud computing, infrastructure, data centers\n"
    "- cybersecurity: security, hacking, data protection, privacy\n"
    "- iot: Internet of Things, connected devices, smart home/city\n"
    "- energy: renewable energy, batteries, power grid, nuclear\n"
    "- automotive: electric vehicles, autonomous driving, mobility\n"
    "- aerospace: satellites, space, drones, aviation\n"
    "- biotech: biotechnology, medtech, health tech, pharma\n"
    "- startup: funding rounds, accelerators, entrepreneurship\n"
    "- fintech: payments, banking tech, blockchain, crypto\n"
    "- telecom: 5G, fiber, networks, operators\n"
    "- research: academic research, R&D, scientific breakthroughs\n\n"
    "Return a JSON object with a single key 'categories':\n"
    '{{"categories": [{{"category": "<slug>", "confidence": <float 0.0-1.0>}}, ...]}}\n\n'
    "Assign 1-3 categories. Only include categories with confidence >= 0.3."
)

CLASSIFY_USER = "{text}"

# -------------------------------------------------------------------

LANG_NAMES = {
    'zh': 'Chinese (Simplified)',
    'en': 'English',
    'fr': 'French',
}


def get_translate_messages(text: str, target_lang: str) -> list[dict]:
    lang_name = LANG_NAMES.get(target_lang, target_lang)
    return [
        {'role': 'system', 'content': TRANSLATE_SYSTEM.format(lang_name=lang_name)},
        {'role': 'user', 'content': TRANSLATE_USER.format(text=text)},
    ]


def get_summarize_messages(text: str, target_lang: str) -> list[dict]:
    lang_name = LANG_NAMES.get(target_lang, target_lang)
    return [
        {'role': 'system', 'content': SUMMARIZE_SYSTEM.format(lang_name=lang_name)},
        {'role': 'user', 'content': SUMMARIZE_USER.format(text=text)},
    ]


def get_ner_messages(text: str) -> list[dict]:
    return [
        {'role': 'system', 'content': NER_SYSTEM},
        {'role': 'user', 'content': NER_USER.format(text=text)},
    ]


def get_sentiment_messages(text: str, company_name: str) -> list[dict]:
    return [
        {'role': 'system', 'content': SENTIMENT_SYSTEM},
        {'role': 'user', 'content': SENTIMENT_USER.format(
            company_name=company_name, text=text
        )},
    ]


def get_classify_messages(text: str) -> list[dict]:
    return [
        {'role': 'system', 'content': CLASSIFY_SYSTEM},
        {'role': 'user', 'content': CLASSIFY_USER.format(text=text)},
    ]
