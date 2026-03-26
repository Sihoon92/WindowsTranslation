import json
import logging
import re

from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


class TranslationResult(BaseModel):
    """배치 번역 결과를 담는 Pydantic 모델"""
    translations: list[str]


class LLMClient:
    # 프롬프트 기반 JSON 배치 번역 실패 시 재시도 횟수
    BATCH_PARSE_RETRIES = 2

    def __init__(self, api_url: str, api_key: str, model_name: str, request_timeout: int = 300,
                 glossary_prompt: str = ""):
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
        self._structured_output_supported: bool | None = None
        self._glossary_prompt = glossary_prompt

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
                f"{self._glossary_prompt}"
            )),
            HumanMessage(content=text),
        ]
        return self._invoke(messages)

    # ── Structured Output (Pydantic) ────────────────────────────

    def _translate_batch_structured(
        self, items: list[str], source_lang: str, target_lang: str
    ) -> list[str] | None:
        """with_structured_output을 사용한 배치 번역. 미지원 서버면 None 반환."""
        if self._structured_output_supported is False:
            return None

        system_prompt = (
            f"You are a professional translator. "
            f"Translate each text from {source_lang} to {target_lang}. "
            f"The input is a JSON array of {len(items)} texts. "
            f"Return exactly {len(items)} translated texts in the same order. "
            f"Preserve numbers, special characters, and line breaks."
            f"{self._glossary_prompt}"
        )
        json_input = json.dumps(items, ensure_ascii=False)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json_input),
        ]

        try:
            structured_llm = self.llm.with_structured_output(TranslationResult)
            self._api_call_count += 1
            result: TranslationResult = structured_llm.invoke(messages)

            if len(result.translations) == len(items):
                self._structured_output_supported = True
                logger.info("Structured output 배치 번역 성공 (%d건)", len(items))
                return result.translations

            logger.warning(
                "Structured output 배열 길이 불일치: 기대 %d, 실제 %d",
                len(items), len(result.translations),
            )
            return None

        except Exception as e:
            if self._structured_output_supported is None:
                self._structured_output_supported = False
                logger.info(
                    "Structured output 미지원 → 프롬프트 방식으로 전환: %s", e
                )
            else:
                logger.warning("Structured output 실패: %s", e)
            return None

    # ── Prompt 기반 JSON 파싱 (fallback) ────────────────────────

    @staticmethod
    def _try_parse_json_array(response: str, expected_len: int) -> list[str] | None:
        """응답에서 JSON 배열을 추출하여 파싱 시도"""
        for text in [response, response.strip("`").strip()]:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list) and len(parsed) == expected_len:
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                continue

        match = re.search(r"```(?:json)?\s*(\[.*?])\s*```", response, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, list) and len(parsed) == expected_len:
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                pass

        match = re.search(r"\[.*]", response, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list) and len(parsed) == expected_len:
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                pass

        return None

    def _translate_batch_prompt(
        self, items: list[str], source_lang: str, target_lang: str
    ) -> list[str] | None:
        """프롬프트 기반 JSON 배치 번역 (기존 방식)"""
        json_input = json.dumps(items, ensure_ascii=False)

        system_prompt = (
            f"You are a professional translator. "
            f"Translate each text in the JSON array from {source_lang} to {target_lang}. "
            f"Return ONLY a JSON array with the translated texts in the same order. "
            f"The output array MUST have exactly {len(items)} elements. "
            f"Preserve numbers, special characters, and line breaks. "
            f"Do not add any explanation or formatting outside the JSON array."
            f"{self._glossary_prompt}"
        )

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
            parsed = self._try_parse_json_array(response, len(items))

            if parsed is not None:
                return parsed

        return None

    # ── 공개 API ────────────────────────────────────────────────

    def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        if not texts:
            return []

        non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        if not non_empty:
            return list(texts)

        # 텍스트 1개면 단건 호출
        if len(non_empty) == 1:
            results = list(texts)
            idx, t = non_empty[0]
            results[idx] = self.translate(t, source_lang, target_lang)
            return results

        items = [t for _, t in non_empty]

        # 1차: Structured Output (Pydantic)
        translated = self._translate_batch_structured(items, source_lang, target_lang)

        # 2차: 프롬프트 기반 JSON 파싱
        if translated is None:
            translated = self._translate_batch_prompt(items, source_lang, target_lang)

        # 3차: 개별 호출 fallback
        if translated is None:
            logger.warning(
                "배치 번역 모두 실패 → 개별 호출 fallback (%d건)", len(non_empty),
            )
            results = list(texts)
            for idx, t in non_empty:
                results[idx] = self.translate(t, source_lang, target_lang)
            return results

        # 결과 조립
        results = list(texts)
        for (idx, _), trans in zip(non_empty, translated):
            results[idx] = trans
        return results
