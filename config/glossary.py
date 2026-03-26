import json
import os

GLOSSARY_FILE = os.path.join(
    os.path.expanduser("~"), ".llm_translator", "glossary.json"
)


def load_glossary() -> list[dict]:
    """용어집 로드. [{source: str, target: str}, ...]"""
    if os.path.exists(GLOSSARY_FILE):
        with open(GLOSSARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_glossary(entries: list[dict]):
    os.makedirs(os.path.dirname(GLOSSARY_FILE), exist_ok=True)
    with open(GLOSSARY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def glossary_to_prompt(entries: list[dict]) -> str:
    """용어집을 시스템 프롬프트용 마크다운 테이블로 변환"""
    if not entries:
        return ""
    lines = [
        "\n\n## Domain Glossary (You MUST use these exact translations when the source term appears):",
        "| Source Term | Target Translation |",
        "|---|---|",
    ]
    for e in entries:
        lines.append(f"| {e['source']} | {e['target']} |")
    return "\n".join(lines)
