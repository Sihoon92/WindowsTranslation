import shutil

from pptx import Presentation
from pptx.util import Inches

from handlers.base import BaseFileHandler, register_handler


@register_handler
class PptxFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".pptx"]

    def extract_texts(self, file_path: str) -> list[dict]:
        prs = Presentation(file_path)
        results = []

        for s_idx, slide in enumerate(prs.slides):
            for sh_idx, shape in enumerate(slide.shapes):
                if shape.has_text_frame:
                    self._extract_text_frame(results, s_idx, sh_idx, "shape", shape.text_frame)
                if shape.has_table:
                    table = shape.table
                    for row_idx, row in enumerate(table.rows):
                        for col_idx, cell in enumerate(row.cells):
                            self._extract_text_frame(
                                results, s_idx, sh_idx, "table",
                                cell.text_frame,
                                row_idx=row_idx, col_idx=col_idx,
                            )

        return results

    def _extract_text_frame(self, results, s_idx, sh_idx, loc_type, text_frame, **extra):
        for p_idx, para in enumerate(text_frame.paragraphs):
            for r_idx, run in enumerate(para.runs):
                if run.text.strip():
                    loc = {
                        "type": loc_type,
                        "s_idx": s_idx,
                        "sh_idx": sh_idx,
                        "p_idx": p_idx,
                        "r_idx": r_idx,
                        **extra,
                    }
                    results.append({"text": run.text, "location": loc})

    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        shutil.copy2(file_path, output_path)
        prs = Presentation(output_path)

        for t in translations:
            loc = t["location"]
            slide = prs.slides[loc["s_idx"]]
            shape = slide.shapes[loc["sh_idx"]]

            if loc["type"] == "shape":
                run = shape.text_frame.paragraphs[loc["p_idx"]].runs[loc["r_idx"]]
                run.text = t["text"]
            elif loc["type"] == "table":
                cell = shape.table.rows[loc["row_idx"]].cells[loc["col_idx"]]
                run = cell.text_frame.paragraphs[loc["p_idx"]].runs[loc["r_idx"]]
                run.text = t["text"]

        prs.save(output_path)
