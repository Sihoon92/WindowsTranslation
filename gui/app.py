import os
import time
from collections import OrderedDict

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.settings import load_settings, save_settings
from handlers import get_handler, get_supported_extensions
from translator.llm_client import LLMClient


# (표시명, API에 전달할 언어명) 쌍
LANGUAGES = [
    ("한국어", "한국어"),
    ("영어", "English"),
    ("일본어", "日本語"),
    ("중국어(간체)", "中文(简体)"),
    ("중국어(번체)", "中文(繁體)"),
    ("독일어", "Deutsch"),
    ("프랑스어", "Français"),
    ("스페인어", "Español"),
    ("포르투갈어", "Português"),
    ("러시아어", "Русский"),
    ("아랍어", "العربية"),
    ("베트남어", "Tiếng Việt"),
    ("태국어", "ภาษาไทย"),
    ("인도네시아어", "Bahasa Indonesia"),
    ("헝가리어", "Magyar"),
]


class TranslationWorker(QThread):
    progress = pyqtSignal(int, int)  # current, total  (overall across all files)
    log = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)  # success, message

    def __init__(self, client, file_paths, source_lang, target_lang, api_delay=0.0, pages_per_batch=2):
        super().__init__()
        self.client = client
        self.file_paths = file_paths
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.api_delay = api_delay
        self.pages_per_batch = max(1, pages_per_batch)
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _translate_single_file(self, file_path, output_path, file_idx, file_count, completed_files_blocks, total_blocks):
        """Translate a single file. Returns number of text blocks processed."""
        file_name = os.path.basename(file_path)
        self.log.emit(f"\n{'='*40}")
        self.log.emit(f"[{file_idx + 1}/{file_count}] {file_name}")
        self.log.emit(f"{'='*40}")

        handler = get_handler(file_path)
        if handler is None:
            ext = os.path.splitext(file_path)[1]
            self.log.emit(f"[건너뜀] 지원하지 않는 파일 형식: {ext}")
            return 0, False

        self.log.emit("텍스트 추출 중...")
        texts = handler.extract_texts(file_path)

        if not texts:
            self.log.emit("[건너뜀] 번역할 텍스트가 없습니다.")
            return 0, True

        file_total = len(texts)
        self.log.emit(f"총 {file_total}개 텍스트 블록 추출 완료")

        # Group texts by page
        page_groups = OrderedDict()
        for idx, item in enumerate(texts):
            page_key = item.get("page", 0)
            if page_key not in page_groups:
                page_groups[page_key] = []
            page_groups[page_key].append(idx)

        # Merge consecutive page groups into batches of `pages_per_batch`
        ppb = self.pages_per_batch
        page_keys = list(page_groups.keys())
        batches = []  # list of (label, indices)
        for i in range(0, len(page_keys), ppb):
            chunk_keys = page_keys[i : i + ppb]
            merged_indices = []
            for pk in chunk_keys:
                merged_indices.extend(page_groups[pk])
            if len(chunk_keys) == 1:
                label = f"페이지 {chunk_keys[0]}"
            else:
                label = f"페이지 {chunk_keys[0]}-{chunk_keys[-1]}"
            batches.append((label, merged_indices))

        self.log.emit(
            f"{len(page_groups)}개 페이지 → {ppb}페이지씩 묶어 {len(batches)}회 API 호출 예정"
        )
        self.client.reset_api_call_count()

        translated = 0
        is_first_batch = True
        for batch_label, indices in batches:
            if self._is_cancelled:
                return translated, False

            if not is_first_batch and self.api_delay > 0:
                self.log.emit(f"API 딜레이 {self.api_delay}초 대기 중...")
                time.sleep(self.api_delay)
            is_first_batch = False

            batch_texts = [texts[i]["text"] for i in indices]

            self.log.emit(
                f"번역 중... {batch_label} "
                f"({translated + len(indices)}/{file_total}, "
                f"블록 {len(indices)}개)"
            )

            translated_texts = self.client.translate_batch(
                batch_texts, self.source_lang, self.target_lang
            )

            for i, trans_text in zip(indices, translated_texts):
                texts[i]["text"] = trans_text

            translated += len(indices)
            self.progress.emit(completed_files_blocks + translated, total_blocks)

        self.log.emit(
            f"번역 완료 (실제 API 호출: {self.client.api_call_count}회)"
        )
        self.log.emit("번역 결과 적용 중...")
        handler.apply_translations(file_path, texts, output_path)
        self.log.emit(f"저장: {output_path}")

        return translated, True

    def run(self):
        file_count = len(self.file_paths)

        # 1단계: 전체 텍스트 블록 수를 미리 파악하여 정확한 진행률 계산
        self.log.emit(f"총 {file_count}개 파일 처리 시작")

        succeeded = []
        failed = []
        completed_blocks = 0

        # 전체 블록 수를 미리 알 수 없으므로 파일 단위 진행률 사용
        total_files = file_count

        for file_idx, file_path in enumerate(self.file_paths):
            if self._is_cancelled:
                self.log.emit("번역이 취소되었습니다.")
                break

            file_name = os.path.basename(file_path)
            base, ext = os.path.splitext(file_path)
            output_path = f"{base}_translated{ext}"

            try:
                blocks, success = self._translate_single_file(
                    file_path, output_path, file_idx, file_count, 0, 0
                )
                if success:
                    succeeded.append(file_name)
                else:
                    if self._is_cancelled:
                        break
                    failed.append(file_name)
            except Exception as e:
                self.log.emit(f"[오류] {file_name}: {e}")
                failed.append(file_name)

            # 파일 단위 진행률
            self.progress.emit(file_idx + 1, total_files)

        if self._is_cancelled:
            self.finished_signal.emit(False, "번역이 취소되었습니다.")
            return

        # 결과 요약
        summary_lines = [f"전체 완료: {len(succeeded)}/{file_count}개 파일 성공"]
        if succeeded:
            summary_lines.append(f"성공: {', '.join(succeeded)}")
        if failed:
            summary_lines.append(f"실패: {', '.join(failed)}")

        summary = "\n".join(summary_lines)
        self.log.emit(f"\n{summary}")

        if failed:
            self.finished_signal.emit(False, summary)
        else:
            self.finished_signal.emit(True, summary)


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

        row = QHBoxLayout()
        row.addWidget(QLabel("API 딜레이(초):"))
        self.api_delay_input = QDoubleSpinBox()
        self.api_delay_input.setRange(0.0, 60.0)
        self.api_delay_input.setSingleStep(0.5)
        self.api_delay_input.setDecimals(1)
        self.api_delay_input.setSuffix(" 초")
        self.api_delay_input.setToolTip("페이지 간 API 호출 사이 대기 시간 (Rate Limit 방지)")
        row.addWidget(self.api_delay_input)
        api_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("페이지 묶음:"))
        self.pages_per_batch_input = QSpinBox()
        self.pages_per_batch_input.setRange(1, 10)
        self.pages_per_batch_input.setValue(2)
        self.pages_per_batch_input.setSuffix(" 페이지/호출")
        self.pages_per_batch_input.setToolTip("한 번의 API 호출에 몇 페이지를 묶어서 보낼지 설정 (Rate Limit 방지)")
        row.addWidget(self.pages_per_batch_input)
        api_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("요청 타임아웃:"))
        self.request_timeout_input = QSpinBox()
        self.request_timeout_input.setRange(30, 600)
        self.request_timeout_input.setValue(300)
        self.request_timeout_input.setSingleStep(30)
        self.request_timeout_input.setSuffix(" 초")
        self.request_timeout_input.setToolTip("API 요청 최대 대기 시간 (큰 파일일수록 높게 설정)")
        row.addWidget(self.request_timeout_input)
        api_layout.addLayout(row)

        self.test_btn = QPushButton("연결 테스트")
        self.test_btn.clicked.connect(self._test_connection)
        api_layout.addWidget(self.test_btn, alignment=Qt.AlignRight)

        layout.addWidget(api_group)

        # --- Translation Settings ---
        trans_group = QGroupBox("번역 설정")
        trans_layout = QVBoxLayout(trans_group)

        trans_layout.addWidget(QLabel("파일 목록:"))
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(120)
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        trans_layout.addWidget(self.file_list)

        btn_row = QHBoxLayout()
        browse_btn = QPushButton("파일 추가")
        browse_btn.clicked.connect(self._browse_files)
        btn_row.addWidget(browse_btn)
        remove_btn = QPushButton("선택 제거")
        remove_btn.clicked.connect(self._remove_selected_files)
        btn_row.addWidget(remove_btn)
        clear_btn = QPushButton("전체 제거")
        clear_btn.clicked.connect(self._clear_files)
        btn_row.addWidget(clear_btn)
        trans_layout.addLayout(btn_row)

        row = QHBoxLayout()
        row.addWidget(QLabel("원본 언어:"))
        self.source_lang = QComboBox()
        for display, value in LANGUAGES:
            self.source_lang.addItem(display, value)
        row.addWidget(self.source_lang)
        row.addWidget(QLabel("번역 언어:"))
        self.target_lang = QComboBox()
        for display, value in LANGUAGES:
            self.target_lang.addItem(display, value)
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

        self.api_delay_input.setValue(float(self.settings.get("api_delay", 0.0)))
        self.pages_per_batch_input.setValue(int(self.settings.get("pages_per_batch", 2)))
        self.request_timeout_input.setValue(int(self.settings.get("request_timeout", 300)))

        source = self.settings.get("source_lang", "한국어")
        target = self.settings.get("target_lang", "English")
        idx = self.source_lang.findData(source)
        if idx >= 0:
            self.source_lang.setCurrentIndex(idx)
        idx = self.target_lang.findData(target)
        if idx >= 0:
            self.target_lang.setCurrentIndex(idx)

    def _save_current_settings(self):
        self.settings.update({
            "api_url": self.api_url_input.text().strip(),
            "api_key": self.api_key_input.text().strip(),
            "model_name": self.model_input.text().strip(),
            "source_lang": self.source_lang.currentData(),
            "target_lang": self.target_lang.currentData(),
            "api_delay": self.api_delay_input.value(),
            "pages_per_batch": self.pages_per_batch_input.value(),
            "request_timeout": self.request_timeout_input.value(),
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

        timeout = self.request_timeout_input.value()
        return LLMClient(url, key, model, request_timeout=timeout)

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

    def _browse_files(self):
        exts = get_supported_extensions()
        filter_parts = [f"*{e}" for e in exts]
        file_filter = f"지원 파일 ({' '.join(filter_parts)});;모든 파일 (*.*)"
        paths, _ = QFileDialog.getOpenFileNames(self, "번역할 파일 선택", "", file_filter)
        if paths:
            existing = set(self.file_list.item(i).text() for i in range(self.file_list.count()))
            for path in paths:
                if path not in existing:
                    self.file_list.addItem(path)

    def _remove_selected_files(self):
        for item in reversed(self.file_list.selectedItems()):
            self.file_list.takeItem(self.file_list.row(item))

    def _clear_files(self):
        self.file_list.clear()

    def _start_translation(self):
        client = self._get_client()
        if not client:
            return

        file_paths = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        if not file_paths:
            QMessageBox.warning(self, "경고", "번역할 파일을 추가하세요.")
            return

        missing = [p for p in file_paths if not os.path.exists(p)]
        if missing:
            QMessageBox.warning(self, "경고", f"파일을 찾을 수 없습니다:\n{chr(10).join(missing)}")
            return

        source = self.source_lang.currentData()
        target = self.target_lang.currentData()
        if source == target:
            QMessageBox.warning(self, "경고", "원본 언어와 번역 언어가 같습니다.")
            return

        self._save_current_settings()

        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.translate_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        api_delay = self.api_delay_input.value()
        pages_per_batch = self.pages_per_batch_input.value()
        self.worker = TranslationWorker(client, file_paths, source, target, api_delay, pages_per_batch)
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
