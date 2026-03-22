import json
import os


DEFAULT_CONFIG = {
    "api_url": "",
    "api_key": "",
    "model_name": "gpt-3.5-turbo",
    "source_lang": "한국어",
    "target_lang": "English",
}

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".llm_translator")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_settings() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        config = {**DEFAULT_CONFIG, **saved}
        return config
    return dict(DEFAULT_CONFIG)


def save_settings(settings: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
