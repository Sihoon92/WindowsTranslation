import shutil

from handlers.base import BaseFileHandler, register_handler


@register_handler
class ExcelFileHandler(BaseFileHandler):
    @classmethod
    def supported_extensions(cls) -> list[str]:
        return [".xlsx", ".xls"]

    def extract_texts(self, file_path: str) -> list[dict]:
        import xlwings as xw

        app = xw.App(visible=False)
        app.display_alerts = False
        try:
            book = app.books.open(file_path)
            results = []

            for sheet in book.sheets:
                used = sheet.used_range
                if used is None:
                    continue
                for row in range(used.row, used.row + used.rows.count):
                    for col in range(used.column, used.column + used.columns.count):
                        cell = sheet.cells(row, col)
                        value = cell.value
                        if isinstance(value, str) and value.strip():
                            results.append({
                                "text": value,
                                "location": {
                                    "sheet": sheet.name,
                                    "row": row,
                                    "col": col,
                                },
                            })

            book.close()
            return results
        finally:
            app.quit()

    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        import xlwings as xw

        shutil.copy2(file_path, output_path)

        app = xw.App(visible=False)
        app.display_alerts = False
        try:
            book = app.books.open(output_path)

            for t in translations:
                loc = t["location"]
                sheet = book.sheets[loc["sheet"]]
                sheet.cells(loc["row"], loc["col"]).value = t["text"]

            book.save()
            book.close()
        finally:
            app.quit()
