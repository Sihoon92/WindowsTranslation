import os
import shutil

import pythoncom
import win32com.client

from handlers.base import BaseFileHandler, register_handler


@register_handler
class PptxFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".pptx", ".ppt"]

    def extract_texts(self, file_path: str) -> list[dict]:
        abs_path = os.path.abspath(file_path)
        pythoncom.CoInitialize()
        ppt = None
        try:
            ppt = win32com.client.Dispatch("PowerPoint.Application")
            prs = ppt.Presentations.Open(abs_path, ReadOnly=True, WithWindow=False)
            results = []

            for s_idx in range(1, prs.Slides.Count + 1):
                slide = prs.Slides(s_idx)
                for sh_idx in range(1, slide.Shapes.Count + 1):
                    shape = slide.Shapes(sh_idx)
                    try:
                        if shape.HasTextFrame:
                            self._extract_from_textframe(
                                results, shape.TextFrame, s_idx, sh_idx, "shape"
                            )
                        if shape.HasTable:
                            table = shape.Table
                            for r_idx in range(1, table.Rows.Count + 1):
                                for c_idx in range(1, table.Columns.Count + 1):
                                    cell = table.Cell(r_idx, c_idx)
                                    self._extract_from_textframe(
                                        results, cell.Shape.TextFrame,
                                        s_idx, sh_idx, "table",
                                        r_idx=r_idx, c_idx=c_idx,
                                    )
                    except Exception:
                        continue

            prs.Close()
            return results
        finally:
            if ppt:
                try:
                    ppt.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    def _extract_from_textframe(self, results, text_frame, s_idx, sh_idx, loc_type, **extra):
        try:
            text_range = text_frame.TextRange
            para_count = text_range.Paragraphs().Count
        except Exception:
            return

        for p_idx in range(1, para_count + 1):
            try:
                para = text_range.Paragraphs(p_idx)
                text = para.Text.strip()
                if text:
                    loc = {
                        "type": loc_type,
                        "s_idx": s_idx,
                        "sh_idx": sh_idx,
                        "p_idx": p_idx,
                        **extra,
                    }
                    results.append({"text": text, "location": loc})
            except Exception:
                continue

    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        shutil.copy2(file_path, output_path)
        abs_output = os.path.abspath(output_path)
        pythoncom.CoInitialize()
        ppt = None
        try:
            ppt = win32com.client.Dispatch("PowerPoint.Application")
            prs = ppt.Presentations.Open(abs_output, WithWindow=False)

            for t in translations:
                loc = t["location"]
                slide = prs.Slides(loc["s_idx"])
                shape = slide.Shapes(loc["sh_idx"])

                try:
                    if loc["type"] == "shape":
                        para = shape.TextFrame.TextRange.Paragraphs(loc["p_idx"])
                        para.Text = t["text"]
                    elif loc["type"] == "table":
                        cell = shape.Table.Cell(loc["r_idx"], loc["c_idx"])
                        para = cell.Shape.TextFrame.TextRange.Paragraphs(loc["p_idx"])
                        para.Text = t["text"]
                except Exception:
                    continue

            prs.Save()
            prs.Close()
        finally:
            if ppt:
                try:
                    ppt.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()
