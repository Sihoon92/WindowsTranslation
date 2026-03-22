import csv
import io
import os

from handlers.base import BaseFileHandler, register_handler


@register_handler
class TextFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".txt"]

    def extract_texts(self, file_path: str) -> list[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by double newlines into paragraphs
        paragraphs = content.split("\n\n")
        results = []
        for i, para in enumerate(paragraphs):
            if para.strip():
                results.append({"text": para, "location": {"index": i}})
        return results

    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        paragraphs = content.split("\n\n")
        trans_map = {t["location"]["index"]: t["text"] for t in translations}

        for idx in trans_map:
            if 0 <= idx < len(paragraphs):
                paragraphs[idx] = trans_map[idx]

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(paragraphs))


@register_handler
class CsvFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".csv"]

    def extract_texts(self, file_path: str) -> list[dict]:
        results = []
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader):
                for col_idx, cell in enumerate(row):
                    if cell.strip():
                        results.append({
                            "text": cell,
                            "location": {"row": row_idx, "col": col_idx},
                        })
        return results

    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        trans_map = {
            (t["location"]["row"], t["location"]["col"]): t["text"]
            for t in translations
        }

        for (row_idx, col_idx), text in trans_map.items():
            if 0 <= row_idx < len(rows) and 0 <= col_idx < len(rows[row_idx]):
                rows[row_idx][col_idx] = text

        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
