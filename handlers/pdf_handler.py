import pdfplumber
from fpdf import FPDF

from handlers.base import BaseFileHandler, register_handler


@register_handler
class PdfFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".pdf"]

    def extract_texts(self, file_path: str) -> list[dict]:
        results = []
        with pdfplumber.open(file_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    results.append({
                        "text": text,
                        "page": page_idx,
                        "location": {"page": page_idx},
                    })
        return results

    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Try to add a Unicode-capable font; fall back to built-in if unavailable
        try:
            import os
            # Common Windows font paths
            font_candidates = [
                os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "malgun.ttf"),
                os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msgothic.ttc"),
                os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
            ]
            font_added = False
            for font_path in font_candidates:
                if os.path.exists(font_path):
                    pdf.add_font("CustomFont", "", font_path, uni=True)
                    pdf.set_font("CustomFont", size=10)
                    font_added = True
                    break
            if not font_added:
                pdf.set_font("Helvetica", size=10)
        except Exception:
            pdf.set_font("Helvetica", size=10)

        # Sort by page order
        sorted_trans = sorted(translations, key=lambda t: t["location"]["page"])

        for t in sorted_trans:
            pdf.add_page()
            pdf.multi_cell(0, 6, t["text"])

        pdf.output(output_path)
