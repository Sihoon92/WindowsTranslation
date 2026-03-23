import os
from collections import OrderedDict

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.settings import load_settings, save_settings
from handlers import get_handler, get_supported_extensions
from translator.llm_client import LLMClient


LANGUAGES = [
    "한국어",
    "English",
    "日本語",
    "中文(简体)",
    "中文(繁體)",
    "Deutsch",
    "Français",
    "Español",
    "Português",
    "Русский",
    "العربية",
    "Tiếng Việt",
    "ภาษาไทย",
    "Bahasa Indonesia",
]


class TranslationWorker(QThread):
    progress = pyqtSignal(int, int)  # current, total
    log = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)  # success, message

    def __init__(self, client, file_path, source_lang, target_lang, output_path):
        super().__init__()
        self.client = client
        self.file_path = file_path
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.output_path = output_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            handler = get_handler(self.file_path)
            if handler is None:
                ext = os.path.splitext(self.file_path)[1]
                self.finished_signal.emit(False, f"지원하지 않는 파일 형식: {ext}")
                return

            self.log.emit("텍스트 추출 중...")
            texts = handler.extract_texts(self.file_path)

            if not texts:
                self.finished_signal.emit(False, "번역할 텍스트가 없습니다.")
                return

            total = len(texts)
            self.log.emit(f"총 {total}개 텍스트 블록 추출 완료")

            # Group texts by page for efficient API calls
            page_groups = OrderedDict()
            for idx, item in enumerate(texts):
                page_key = item.get("page", 0)
                if page_key not in page_groups:
                    page_groups[page_key] = []
                page_groups[page_key].append(idx)

            self.log.emit(
                f"{len(page_groups)}개 페이지로 그룹화 → 예상 API 호출 {len(page_groups)}회"
            )
            self.client.reset_api_call_count()

            translated = 0
            for page_key, indices in page_groups.items():
                if self._is_cancelled:
                    self.finished_signal.emit(False, "번역이 취소되었습니다.")
                    return

                batch_texts = [texts[i]["text"] for i in indices]

                self.log.emit(
                    f"번역 중... 페이지 {page_key} "
                    f"({translated + len(indices)}/{total}, "
                    f"블록 {len(indices)}개)"
                )

                translated_texts = self.client.translate_batch(
                    batch_texts, self.source_lang, self.target_lang
                )

                for i, trans_text in zip(indices, translated_texts):
                    texts[i]["text"] = trans_text

                translated += len(indices)
                self.progress.emit(translated, total)

            self.log.emit(
                f"번역 완료 (실제 API 호출: {self.client.api_call_count}회)"
            )
            self.log.emit("번역 결과 적용 중...")
            handler.apply_translations(self.file_path, texts, self.output_path)

            self.finished_signal.emit(True, f"번역 완료!\n저장: {self.output_path}")

        except Exception as e:
            self.finished_signal.emit(False, f"오류 발생: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.worker = None
        self._init_ui()
        self._load_settings_to_ui()

    def _init_ui(self):
        self.setWindowTitle("LLM 파일 번역기")
        self.setMinimumSize(600, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- API Settings ---
        api_group = QGroupBox("API 설정")
        api_layout = QVBoxLayout(api_group)

        row = QHBoxLayout()
        row.addWidget(QLabel("API URL:"))
        self.api_url_input = QLineEdit()
        self.api_url_input.setPlaceholderText("예: http://localhost:8000")
        row.addWidget(self.api_url_input)
        api_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("API 키를 입력하세요")
        row.addWidget(self.api_key_input)
        api_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("모델명:"))
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("예: gpt-3.5-turbo")
        row.addWidget(self.model_input)
        api_layout.addLayout(row)

        self.test_btn = QPushButton("연결 테스트")
        self.test_btn.clicked.connect(self._test_connection)
        api_layout.addWidget(self.test_btn, alignment=Qt.AlignRight)

        layout.addWidget(api_group)

        # --- Translation Settings ---
        trans_group = QGroupBox("번역 설정")
        trans_layout = QVBoxLayout(trans_group)

        row = QHBoxLayout()
        row.addWidget(QLabel("파일:"))
        self.file_input = QLineEdit()
        self.file_input.setReadOnly(True)
        row.addWidget(self.file_input)
        browse_btn = QPushButton("찾기")
        browse_btn.clicked.connect(self._browse_file)
        row.addWidget(browse_btn)
        trans_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("원본 언어:"))
        self.source_lang = QComboBox()
        self.source_lang.addItems(LANGUAGES)
        row.addWidget(self.source_lang)
        row.addWidget(QLabel("번역 언어:"))
        self.target_lang = QComboBox()
        self.target_lang.addItems(LANGUAGES)
        row.addWidget(self.target_lang)
        trans_layout.addLayout(row)

        layout.addWidget(trans_group)

        # --- Action ---
        btn_layout = QHBoxLayout()
        self.translate_btn = QPushButton("번역 시작")
        self.translate_btn.setMinimumHeight(40)
        self.translate_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.translate_btn.clicked.connect(self._start_translation)
        btn_layout.addWidget(self.translate_btn)

        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_translation)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

        # --- Progress ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # --- Log ---
        log_group = QGroupBox("로그")
        log_layout = QVBoxLayout(log_group)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(200)
        log_layout.addWidget(self.log_output)
        layout.addWidget(log_group)

        # Supported formats label
        exts = ", ".join(get_supported_extensions())
        layout.addWidget(QLabel(f"지원 형식: {exts}"))

    def _load_settings_to_ui(self):
        self.api_url_input.setText(self.settings.get("api_url", ""))
        self.api_key_input.setText(self.settings.get("api_key", ""))
        self.model_input.setText(self.settings.get("model_name", ""))

        source = self.settings.get("source_lang", "한국어")
        target = self.settings.get("target_lang", "English")
        idx = self.source_lang.findText(source)
        if idx >= 0:
            self.source_lang.setCurrentIndex(idx)
        idx = self.target_lang.findText(target)
        if idx >= 0:
            self.target_lang.setCurrentIndex(idx)

    def _save_current_settings(self):
        self.settings.update({
            "api_url": self.api_url_input.text().strip(),
            "api_key": self.api_key_input.text().strip(),
            "model_name": self.model_input.text().strip(),
            "source_lang": self.source_lang.currentText(),
            "target_lang": self.target_lang.currentText(),
        })
        save_settings(self.settings)

    def _get_client(self) -> LLMClient | None:
        url = self.api_url_input.text().strip()
        key = self.api_key_input.text().strip()
        model = self.model_input.text().strip()

        if not url:
            QMessageBox.warning(self, "경고", "API URL을 입력하세요.")
            return None
        if not key:
            QMessageBox.warning(self, "경고", "API Key를 입력하세요.")
            return None
        if not model:
            QMessageBox.warning(self, "경고", "모델명을 입력하세요.")
            return None

        return LLMClient(url, key, model)

    def _test_connection(self):
        client = self._get_client()
        if not client:
            return

        self._save_current_settings()
        self.test_btn.setEnabled(False)
        self.test_btn.setText("테스트 중...")

        # Run in a simple thread
        class TestThread(QThread):
            result = pyqtSignal(bool, str)

            def __init__(self, c):
                super().__init__()
                self.c = c

            def run(self):
                ok, msg = self.c.test_connection()
                self.result.emit(ok, msg)

        self._test_thread = TestThread(client)
        self._test_thread.result.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, success, message):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("연결 테스트")
        if success:
            QMessageBox.information(self, "성공", message)
        else:
            QMessageBox.critical(self, "실패", message)

    def _browse_file(self):
        exts = get_supported_extensions()
        filter_parts = [f"*{e}" for e in exts]
        file_filter = f"지원 파일 ({' '.join(filter_parts)});;모든 파일 (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "번역할 파일 선택", "", file_filter)
        if path:
            self.file_input.setText(path)

    def _start_translation(self):
        client = self._get_client()
        if not client:
            return

        file_path = self.file_input.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "경고", "번역할 파일을 선택하세요.")
            return

        source = self.source_lang.currentText()
        target = self.target_lang.currentText()
        if source == target:
            QMessageBox.warning(self, "경고", "원본 언어와 번역 언어가 같습니다.")
            return

        self._save_current_settings()

        # Generate output path in the same directory as the original file
        base, ext = os.path.splitext(file_path)
        output_path = f"{base}_translated{ext}"

        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.translate_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self.worker = TranslationWorker(client, file_path, source, target, output_path)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._on_log)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _cancel_translation(self):
        if self.worker:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, current, total):
        percent = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)

    def _on_log(self, message):
        self.log_output.append(message)

    def _on_finished(self, success, message):
        self.translate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if success:
            self.progress_bar.setValue(100)
            self.log_output.append(message)
            QMessageBox.information(self, "완료", message)
        else:
            self.log_output.append(f"[오류] {message}")
            QMessageBox.critical(self, "오류", message)

    def closeEvent(self, event):
        self._save_current_settings()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        event.accept()
