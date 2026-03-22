import json
import time
import requests


class LLMClient:
    def __init__(self, api_url: str, api_key: str, model_name: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = 60
        self.max_retries = 3

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _chat_completion(self, messages: list[dict], temperature: float = 0.3) -> str:
        url = f"{self.api_url}/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            except requests.exceptions.HTTPError as e:
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    time.sleep(wait)
                    last_error = e
                    continue
                raise
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise

        raise last_error

    def test_connection(self) -> tuple[bool, str]:
        try:
            result = self._chat_completion(
                [{"role": "user", "content": "Hi, respond with 'OK'."}],
                temperature=0,
            )
            return True, f"연결 성공: {result}"
        except Exception as e:
            return False, f"연결 실패: {e}"

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text or not text.strip():
            return text

        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a professional translator. "
                    f"Translate the following text from {source_lang} to {target_lang}. "
                    f"Return ONLY the translated text without any explanation, "
                    f"prefix, or additional formatting. "
                    f"Preserve numbers, special characters, and line breaks as-is."
                ),
            },
            {"role": "user", "content": text},
        ]
        return self._chat_completion(messages)

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
            {
                "role": "system",
                "content": (
                    f"You are a professional translator. "
                    f"Translate each text in the JSON array from {source_lang} to {target_lang}. "
                    f"Return ONLY a JSON array with the translated texts in the same order. "
                    f"Preserve numbers, special characters, and line breaks. "
                    f"Do not add any explanation or formatting outside the JSON array."
                ),
            },
            {"role": "user", "content": json_input},
        ]

        response = self._chat_completion(messages)

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
