import os
import shutil

import pythoncom
import win32com.client

from handlers.base import BaseFileHandler, register_handler


@register_handler
class WordFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".docx", ".doc"]

    def extract_texts(self, file_path: str) -> list[dict]:
        abs_path = os.path.abspath(file_path)
        pythoncom.CoInitialize()
        word = None
        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False
            doc = word.Documents.Open(abs_path, ReadOnly=True)
            results = []

            # Body paragraphs (exclude those inside tables)
            for p_idx in range(1, doc.Paragraphs.Count + 1):
                para = doc.Paragraphs(p_idx)
                # wdWithInTable = 12
                if para.Range.Information(12):
                    continue
                text = para.Range.Text
                text = text.rstrip("\r\n\x0b\x07")
                if text.strip():
                    results.append({
                        "text": text,
                        "page": 0,
                        "location": {"type": "paragraph", "p_idx": p_idx},
                    })

            # Tables
            for t_idx in range(1, doc.Tables.Count + 1):
                table = doc.Tables(t_idx)
                for r_idx in range(1, table.Rows.Count + 1):
                    for c_idx in range(1, table.Columns.Count + 1):
                        try:
                            cell = table.Cell(r_idx, c_idx)
                            text = cell.Range.Text
                            text = text.rstrip("\r\n\x07")
                            if text.strip():
                                results.append({
                                    "text": text,
                                    "page": t_idx,
                                    "location": {
                                        "type": "table",
                                        "t_idx": t_idx,
                                        "r_idx": r_idx,
                                        "c_idx": c_idx,
                                    },
                                })
                        except Exception:
                            continue

            doc.Close(False)
            return results
        finally:
            if word:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        shutil.copy2(file_path, output_path)
        abs_output = os.path.abspath(output_path)
        pythoncom.CoInitialize()
        word = None
        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False
            doc = word.Documents.Open(abs_output)

            for t in translations:
                loc = t["location"]
                if loc["type"] == "paragraph":
                    para = doc.Paragraphs(loc["p_idx"])
                    rng = para.Range
                    # Exclude trailing paragraph mark
                    rng.End = rng.End - 1
                    rng.Text = t["text"]
                elif loc["type"] == "table":
                    table = doc.Tables(loc["t_idx"])
                    cell = table.Cell(loc["r_idx"], loc["c_idx"])
                    rng = cell.Range
                    # Cell range ends with \r\x07, exclude those
                    rng.End = rng.End - 2
                    rng.Text = t["text"]

            doc.Save()
            doc.Close()
        finally:
            if word:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()
