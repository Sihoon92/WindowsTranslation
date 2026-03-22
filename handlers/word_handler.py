import shutil

from docx import Document

from handlers.base import BaseFileHandler, register_handler


@register_handler
class WordFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".docx"]

    def extract_texts(self, file_path: str) -> list[dict]:
        doc = Document(file_path)
        results = []

        # Body paragraphs
        for p_idx, para in enumerate(doc.paragraphs):
            for r_idx, run in enumerate(para.runs):
                if run.text.strip():
                    results.append({
                        "text": run.text,
                        "location": {"type": "paragraph", "p_idx": p_idx, "r_idx": r_idx},
                    })

        # Tables
        for t_idx, table in enumerate(doc.tables):
            for row_idx, row in enumerate(table.rows):
                for col_idx, cell in enumerate(row.cells):
                    for p_idx, para in enumerate(cell.paragraphs):
                        for r_idx, run in enumerate(para.runs):
                            if run.text.strip():
                                results.append({
                                    "text": run.text,
                                    "location": {
                                        "type": "table",
                                        "t_idx": t_idx,
                                        "row_idx": row_idx,
                                        "col_idx": col_idx,
                                        "p_idx": p_idx,
                                        "r_idx": r_idx,
                                    },
                                })

        return results

    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        shutil.copy2(file_path, output_path)
        doc = Document(output_path)

        for t in translations:
            loc = t["location"]
            if loc["type"] == "paragraph":
                run = doc.paragraphs[loc["p_idx"]].runs[loc["r_idx"]]
                run.text = t["text"]
            elif loc["type"] == "table":
                cell = doc.tables[loc["t_idx"]].rows[loc["row_idx"]].cells[loc["col_idx"]]
                run = cell.paragraphs[loc["p_idx"]].runs[loc["r_idx"]]
                run.text = t["text"]

        doc.save(output_path)
