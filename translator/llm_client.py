import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


class LLMClient:
    def __init__(self, api_url: str, api_key: str, model_name: str):
        base_url = api_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        self.llm = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            temperature=0.3,
            request_timeout=60,
            max_retries=3,
        )

    def _invoke(self, messages: list, temperature: float = 0.3) -> str:
        self.llm.temperature = temperature
        response = self.llm.invoke(messages)
        return response.content.strip()

    def test_connection(self) -> tuple[bool, str]:
        try:
            result = self._invoke(
                [HumanMessage(content="Hi, respond with 'OK'.")],
                temperature=0,
            )
            return True, f"연결 성공: {result}"
        except Exception as e:
            return False, f"연결 실패: {e}"

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text or not text.strip():
            return text

        messages = [
            SystemMessage(content=(
                f"You are a professional translator. "
                f"Translate the following text from {source_lang} to {target_lang}. "
                f"Return ONLY the translated text without any explanation, "
                f"prefix, or additional formatting. "
                f"Preserve numbers, special characters, and line breaks as-is."
            )),
            HumanMessage(content=text),
        ]
        return self._invoke(messages)

    def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        if not texts:
            return []

        non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        if not non_empty:
            return list(texts)

        # For small batches, translate one by one for reliability
        if len(non_empty) <= 3:
            results = list(texts)
            for idx, t in non_empty:
                results[idx] = self.translate(t, source_lang, target_lang)
            return results

        # For larger batches, use JSON array format
        items = [t for _, t in non_empty]
        json_input = json.dumps(items, ensure_ascii=False)

        messages = [
            SystemMessage(content=(
                f"You are a professional translator. "
                f"Translate each text in the JSON array from {source_lang} to {target_lang}. "
                f"Return ONLY a JSON array with the translated texts in the same order. "
                f"Preserve numbers, special characters, and line breaks. "
                f"Do not add any explanation or formatting outside the JSON array."
            )),
            HumanMessage(content=json_input),
        ]

        response = self._invoke(messages)

        try:
            translated = json.loads(response)
            if isinstance(translated, list) and len(translated) == len(non_empty):
                results = list(texts)
                for (idx, _), trans in zip(non_empty, translated):
                    results[idx] = str(trans)
                return results
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: translate one by one
        results = list(texts)
        for idx, t in non_empty:
            results[idx] = self.translate(t, source_lang, target_lang)
        return results
