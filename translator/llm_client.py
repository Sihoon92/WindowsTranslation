import json
import logging
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


class LLMClient:
    # JSON 배치 번역 실패 시 재시도 횟수
    BATCH_PARSE_RETRIES = 2

    def __init__(self, api_url: str, api_key: str, model_name: str, request_timeout: int = 300):
        base_url = api_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        self.llm = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            temperature=0.3,
            request_timeout=request_timeout,
            max_retries=3,
        )
        self._api_call_count = 0

    @property
    def api_call_count(self) -> int:
        return self._api_call_count

    def reset_api_call_count(self):
        self._api_call_count = 0

    def _invoke(self, messages: list, temperature: float = 0.3) -> str:
        self.llm.temperature = temperature
        self._api_call_count += 1
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

    @staticmethod
    def _try_parse_json_array(response: str, expected_len: int) -> list[str] | None:
        """응답에서 JSON 배열을 추출하여 파싱 시도"""
        # 먼저 그대로 파싱
        for text in [response, response.strip("`").strip()]:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list) and len(parsed) == expected_len:
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                continue

        # 코드블록 내 JSON 추출 시도
        match = re.search(r"```(?:json)?\s*(\[.*?])\s*```", response, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, list) and len(parsed) == expected_len:
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                pass

        # 응답 내 JSON 배열 패턴 추출
        match = re.search(r"\[.*]", response, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list) and len(parsed) == expected_len:
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                pass

        return None

    def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        if not texts:
            return []

        non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        if not non_empty:
            return list(texts)

        # 텍스트 1개면 단건 호출 (JSON 배열 불필요)
        if len(non_empty) == 1:
            results = list(texts)
            idx, t = non_empty[0]
            results[idx] = self.translate(t, source_lang, target_lang)
            return results

        # 항상 JSON 배치로 요청 (슬라이드당 1회 API 호출)
        items = [t for _, t in non_empty]
        json_input = json.dumps(items, ensure_ascii=False)

        system_prompt = (
            f"You are a professional translator. "
            f"Translate each text in the JSON array from {source_lang} to {target_lang}. "
            f"Return ONLY a JSON array with the translated texts in the same order. "
            f"The output array MUST have exactly {len(items)} elements. "
            f"Preserve numbers, special characters, and line breaks. "
            f"Do not add any explanation or formatting outside the JSON array."
        )

        # 첫 시도 + 재시도 (reprompt)
        for attempt in range(1 + self.BATCH_PARSE_RETRIES):
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=json_input),
            ]

            if attempt > 0:
                messages.append(HumanMessage(content=(
                    f"Your previous response was not a valid JSON array "
                    f"with exactly {len(items)} elements. "
                    f"Please try again. Return ONLY a JSON array."
                )))
                logger.warning(
                    "JSON 배치 번역 재시도 %d/%d (파싱 실패)",
                    attempt, self.BATCH_PARSE_RETRIES,
                )

            response = self._invoke(messages)
            parsed = self._try_parse_json_array(response, len(non_empty))

            if parsed is not None:
                results = list(texts)
                for (idx, _), trans in zip(non_empty, parsed):
                    results[idx] = trans
                return results

        # 최종 실패 시에만 개별 호출 fallback
        logger.warning(
            "JSON 배치 번역 %d회 실패 → 개별 호출 fallback (%d건)",
            1 + self.BATCH_PARSE_RETRIES, len(non_empty),
        )
        results = list(texts)
        for idx, t in non_empty:
            results[idx] = self.translate(t, source_lang, target_lang)
        return results
