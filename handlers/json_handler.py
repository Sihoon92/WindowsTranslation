import json

from handlers.base import BaseFileHandler, register_handler


@register_handler
class JsonFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".json"]

    def extract_texts(self, file_path: str) -> list[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        results = []
        self._extract_recursive(data, [], results)
        return results

    def _extract_recursive(self, obj, path: list, results: list):
        if isinstance(obj, str):
            if obj.strip():
                results.append({"text": obj, "page": 0, "location": {"path": list(path)}})
        elif isinstance(obj, dict):
            for key, value in obj.items():
                self._extract_recursive(value, path + [key], results)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self._extract_recursive(item, path + [i], results)

    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for t in translations:
            self._set_value(data, t["location"]["path"], t["text"])

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _set_value(self, obj, path: list, value: str):
        for key in path[:-1]:
            obj = obj[key]
        obj[path[-1]] = value
