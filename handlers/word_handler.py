import os
import shutil

import pythoncom
import win32com.client

from handlers.base import BaseFileHandler, register_handler

# Word Shape type constants
MSO_GROUP = 6  # msoGroup


@register_handler
class WordFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".docx", ".doc"]

    # ------------------------------------------------------------------
    # extract_texts
    # ------------------------------------------------------------------
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

            self._extract_body_paragraphs(doc, results)
            self._extract_tables(doc, results)
            self._extract_shapes(doc, results)
            self._extract_headers_footers(doc, results)
            self._extract_footnotes(doc, results)
            self._extract_endnotes(doc, results)
            self._extract_comments(doc, results)
            self._extract_content_controls(doc, results)

            doc.Close(False)
            return results
        finally:
            if word:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    # --- Body paragraphs (exclude those inside tables) ---
    def _extract_body_paragraphs(self, doc, results):
        for p_idx in range(1, doc.Paragraphs.Count + 1):
            para = doc.Paragraphs(p_idx)
            # wdWithInTable = 12
            if para.Range.Information(12):
                continue
            text = para.Range.Text
            text = text.rstrip("\r\n\x0b\x07")
            if text.strip():
                page_num = para.Range.Information(3)  # wdActiveEndPageNumber
                results.append({
                    "text": text,
                    "page": page_num,
                    "location": {"type": "paragraph", "p_idx": p_idx},
                })

    # --- Tables ---
    def _extract_tables(self, doc, results):
        for t_idx in range(1, doc.Tables.Count + 1):
            table = doc.Tables(t_idx)
            for r_idx in range(1, table.Rows.Count + 1):
                for c_idx in range(1, table.Columns.Count + 1):
                    try:
                        cell = table.Cell(r_idx, c_idx)
                        text = cell.Range.Text
                        text = text.rstrip("\r\n\x07")
                        if text.strip():
                            page_num = cell.Range.Information(3)
                            results.append({
                                "text": text,
                                "page": page_num,
                                "location": {
                                    "type": "table",
                                    "t_idx": t_idx,
                                    "r_idx": r_idx,
                                    "c_idx": c_idx,
                                },
                            })
                    except Exception:
                        continue

    # --- Shapes (text boxes, diagrams, grouped shapes) ---
    def _extract_shapes(self, doc, results):
        for sh_idx in range(1, doc.Shapes.Count + 1):
            shape = doc.Shapes(sh_idx)
            self._process_shape(results, shape, [sh_idx])

    def _process_shape(self, results, shape, shape_path):
        try:
            if shape.Type == MSO_GROUP:
                for gi_idx in range(1, shape.GroupItems.Count + 1):
                    child = shape.GroupItems(gi_idx)
                    self._process_shape(results, child, shape_path + [gi_idx])
                return

            if shape.HasTextFrame:
                tf = shape.TextFrame
                try:
                    text_range = tf.TextRange
                    text = text_range.Text.strip()
                except Exception:
                    text = ""
                if text:
                    try:
                        page_num = shape.Anchor.Information(3)
                    except Exception:
                        page_num = 0
                    results.append({
                        "text": text,
                        "page": page_num,
                        "location": {"type": "shape", "shape_path": shape_path},
                    })
        except Exception:
            pass

    # --- Headers & Footers ---
    def _extract_headers_footers(self, doc, results):
        for sec_idx in range(1, doc.Sections.Count + 1):
            section = doc.Sections(sec_idx)
            # Headers: wdHeaderFooterPrimary=1, wdHeaderFooterFirstPage=2, wdHeaderFooterEvenPages=3
            for hf_type in (1, 2, 3):
                try:
                    header = section.Headers(hf_type)
                    if header.Exists:
                        self._extract_header_footer_text(
                            results, header.Range, sec_idx, "header", hf_type
                        )
                        # Extract shapes (text boxes) inside this header
                        self._extract_hf_shapes(
                            results, header, sec_idx, "header", hf_type
                        )
                except Exception:
                    continue
            # Footers
            for hf_type in (1, 2, 3):
                try:
                    footer = section.Footers(hf_type)
                    if footer.Exists:
                        self._extract_header_footer_text(
                            results, footer.Range, sec_idx, "footer", hf_type
                        )
                        # Extract shapes (text boxes) inside this footer
                        self._extract_hf_shapes(
                            results, footer, sec_idx, "footer", hf_type
                        )
                except Exception:
                    continue

    def _extract_hf_shapes(self, results, hf, sec_idx, kind, hf_type):
        """Extract text from shapes (text boxes) inside a header or footer."""
        try:
            shapes = hf.Shapes
            for sh_idx in range(1, shapes.Count + 1):
                shape = shapes(sh_idx)
                self._process_hf_shape(
                    results, shape, sec_idx, kind, hf_type, [sh_idx]
                )
        except Exception:
            pass

    def _process_hf_shape(self, results, shape, sec_idx, kind, hf_type, shape_path):
        try:
            if shape.Type == MSO_GROUP:
                for gi_idx in range(1, shape.GroupItems.Count + 1):
                    child = shape.GroupItems(gi_idx)
                    self._process_hf_shape(
                        results, child, sec_idx, kind, hf_type,
                        shape_path + [gi_idx],
                    )
                return

            if shape.HasTextFrame:
                tf = shape.TextFrame
                try:
                    text = tf.TextRange.Text.strip()
                except Exception:
                    text = ""
                if text:
                    results.append({
                        "text": text,
                        "page": 0,
                        "location": {
                            "type": f"{kind}_shape",
                            "sec_idx": sec_idx,
                            "hf_type": hf_type,
                            "shape_path": shape_path,
                        },
                    })
        except Exception:
            pass

    def _extract_header_footer_text(self, results, rng, sec_idx, kind, hf_type):
        text = rng.Text.rstrip("\r\n\x0b\x07")
        if text.strip():
            results.append({
                "text": text,
                "page": 0,
                "location": {
                    "type": kind,
                    "sec_idx": sec_idx,
                    "hf_type": hf_type,
                },
            })

    # --- Footnotes ---
    def _extract_footnotes(self, doc, results):
        for fn_idx in range(1, doc.Footnotes.Count + 1):
            try:
                fn = doc.Footnotes(fn_idx)
                text = fn.Range.Text.rstrip("\r\n\x0b\x07")
                if text.strip():
                    page_num = fn.Range.Information(3)
                    results.append({
                        "text": text,
                        "page": page_num,
                        "location": {"type": "footnote", "fn_idx": fn_idx},
                    })
            except Exception:
                continue

    # --- Endnotes ---
    def _extract_endnotes(self, doc, results):
        for en_idx in range(1, doc.Endnotes.Count + 1):
            try:
                en = doc.Endnotes(en_idx)
                text = en.Range.Text.rstrip("\r\n\x0b\x07")
                if text.strip():
                    page_num = en.Range.Information(3)
                    results.append({
                        "text": text,
                        "page": page_num,
                        "location": {"type": "endnote", "en_idx": en_idx},
                    })
            except Exception:
                continue

    # --- Comments ---
    def _extract_comments(self, doc, results):
        for cm_idx in range(1, doc.Comments.Count + 1):
            try:
                comment = doc.Comments(cm_idx)
                text = comment.Range.Text.rstrip("\r\n\x0b\x07")
                if text.strip():
                    results.append({
                        "text": text,
                        "page": 0,
                        "location": {"type": "comment", "cm_idx": cm_idx},
                    })
            except Exception:
                continue

    # --- Content Controls (rich text boxes, plain text boxes) ---
    def _extract_content_controls(self, doc, results):
        for cc_idx in range(1, doc.ContentControls.Count + 1):
            try:
                cc = doc.ContentControls(cc_idx)
                text = cc.Range.Text.rstrip("\r\n\x0b\x07")
                if text.strip():
                    page_num = cc.Range.Information(3)
                    results.append({
                        "text": text,
                        "page": page_num,
                        "location": {"type": "content_control", "cc_idx": cc_idx},
                    })
            except Exception:
                continue

    # ------------------------------------------------------------------
    # apply_translations
    # ------------------------------------------------------------------
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
                try:
                    if loc["type"] == "paragraph":
                        para = doc.Paragraphs(loc["p_idx"])
                        rng = para.Range
                        rng.End = rng.End - 1  # exclude trailing paragraph mark
                        rng.Text = t["text"]

                    elif loc["type"] == "table":
                        table = doc.Tables(loc["t_idx"])
                        cell = table.Cell(loc["r_idx"], loc["c_idx"])
                        rng = cell.Range
                        rng.End = rng.End - 2  # cell range ends with \r\x07
                        rng.Text = t["text"]

                    elif loc["type"] == "shape":
                        shape = self._get_shape_by_path(doc, loc["shape_path"])
                        shape.TextFrame.TextRange.Text = t["text"]

                    elif loc["type"] in ("header", "footer"):
                        section = doc.Sections(loc["sec_idx"])
                        if loc["type"] == "header":
                            hf = section.Headers(loc["hf_type"])
                        else:
                            hf = section.Footers(loc["hf_type"])
                        rng = hf.Range
                        rng.Text = t["text"]

                    elif loc["type"] == "footnote":
                        fn = doc.Footnotes(loc["fn_idx"])
                        fn.Range.Text = t["text"]

                    elif loc["type"] == "endnote":
                        en = doc.Endnotes(loc["en_idx"])
                        en.Range.Text = t["text"]

                    elif loc["type"] == "comment":
                        comment = doc.Comments(loc["cm_idx"])
                        comment.Range.Text = t["text"]

                    elif loc["type"] in ("header_shape", "footer_shape"):
                        section = doc.Sections(loc["sec_idx"])
                        if loc["type"] == "header_shape":
                            hf = section.Headers(loc["hf_type"])
                        else:
                            hf = section.Footers(loc["hf_type"])
                        shape = hf.Shapes(loc["shape_path"][0])
                        for gi_idx in loc["shape_path"][1:]:
                            shape = shape.GroupItems(gi_idx)
                        shape.TextFrame.TextRange.Text = t["text"]

                    elif loc["type"] == "content_control":
                        cc = doc.ContentControls(loc["cc_idx"])
                        cc.Range.Text = t["text"]

                except Exception:
                    continue

            doc.Save()
            doc.Close()
        finally:
            if word:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    def _get_shape_by_path(self, doc, shape_path):
        shape = doc.Shapes(shape_path[0])
        for gi_idx in shape_path[1:]:
            shape = shape.GroupItems(gi_idx)
        return shape
