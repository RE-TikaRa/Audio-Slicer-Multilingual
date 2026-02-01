import os
import shutil
import subprocess
import tempfile

import soundfile
import numpy as np

from typing import List
from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from audio_slicer.utils.slicer2 import Slicer

from audio_slicer.gui.Ui_MainWindow import Ui_MainWindow
from audio_slicer.utils.preview import SlicingPreview
from audio_slicer.modules import i18n

APP_VERSION = "1.4.0"


class _FallbackBridge(QObject):
    request = Signal(str, str)

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window = window
        self.mutex = QMutex()
        self.cond = QWaitCondition()
        self.choice: str | None = None
        self.request.connect(self._on_request)

    @Slot(str, str)
    def _on_request(self, filename: str, error: str):
        choice = self.window._show_fallback_dialog("process_read_failed", filename, error)
        self.mutex.lock()
        self.choice = choice
        self.cond.wakeAll()
        self.mutex.unlock()


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.ui.btnAddFiles.clicked.connect(self._on_add_audio_files)
        self.ui.btnBrowse.clicked.connect(self._on_browse_output_dir)
        self.ui.btnRemove.clicked.connect(self._on_remove_audio_file)
        self.ui.btnClearList.clicked.connect(self._on_clear_audio_list)
        self.ui.btnAbout.clicked.connect(self._on_about)
        self.ui.btnPreviewSelection.clicked.connect(self._on_preview_selection)
        self.ui.btnStart.clicked.connect(self._on_start)
        # self.ui.twImages.tabCloseRequested.connect(self._on_tab_close_requested)

        # tab = QLabel()
        # pix = QPixmap('preview.png')
        # scalH = int(tab.height() * 1.25)
        # scalW = pix.scaledToHeight(scalH).width()
        # if (self.ui.twImages.width() < scalW):
        #     scalW = int(tab.width() * 1.25)
        #     scalH = pix.scaledToWidth(scalW).height()
        # tab.setPixmap(pix.scaled(scalW, scalH))
        # self.ui.twImages.addTab(tab, "preview.png")

        self.ui.progressBar.setMinimum(0)
        self.ui.progressBar.setMaximum(100)
        self.ui.progressBar.setValue(0)
        self.ui.btnStart.setDefault(True)

        validator = QRegularExpressionValidator(QRegularExpression(r"\d+"))
        self.ui.leThreshold.setValidator(QDoubleValidator())
        self.ui.leMinLen.setValidator(validator)
        self.ui.leMinInterval.setValidator(validator)
        self.ui.leHopSize.setValidator(validator)
        self.ui.leMaxSilence.setValidator(validator)

        self.ui.lwTaskList.setAlternatingRowColors(True)

        # State variables
        self.workers: list[QThread] = []
        self.workCount = 0
        self.workFinished = 0
        self.processing = False
        self.last_output_dir: str | None = None

        # Language setup
        self.current_language = i18n.normalize_language(QLocale.system().name())
        self._init_language_selector()
        self._apply_language()
        self._fallback_bridge = _FallbackBridge(self)

        # Must set to accept drag and drop events
        self.setAcceptDrops(True)

        # Get available formats/extensions supported
        self.availableFormats = [str(formatExt).lower()
                                 for formatExt in soundfile.available_formats().keys()]
        # libsndfile supports Opus in Ogg container
        # .opus is a valid extension and recommended for Ogg Opus (see RFC 7845, Section 9)
        # append opus for convenience as tools like youtube-dl(p) extract to .opus by default
        self.availableFormats.append("opus")
        self.formatAllFilter = " ".join(
            [f"*.{formatExt}" for formatExt in self.availableFormats])
        self.formatIndividualFilter = ";;".join(
            [f"{formatExt} (*.{formatExt})" for formatExt in sorted(self.availableFormats)])

    def _on_tab_close_requested(self, index):
        self.ui.twImages.removeTab(index)

    def _on_browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Browse Output Directory", ".")
        if path != "":
            self.ui.leOutputDir.setText(QDir.toNativeSeparators(path))

    def _on_add_audio_files(self):
        if self.processing:
            self._warningProcessNotFinished()
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            i18n.text("select_audio_files", self.current_language),
            ".",
            f"Audio ({self.formatAllFilter});;{self.formatIndividualFilter}",
        )
        for path in paths:
            item = QListWidgetItem()
            item.setSizeHint(QSize(200, 24))
            item.setText(QFileInfo(path).fileName())
            # Save full path at custom role
            item.setData(Qt.ItemDataRole.UserRole + 1, path)
            self.ui.lwTaskList.addItem(item)

    def _on_remove_audio_file(self):
        item = self.ui.lwTaskList.currentItem()
        if item is None:
            return
        self.ui.lwTaskList.takeItem(self.ui.lwTaskList.row(item))
        return

    def _on_clear_audio_list(self):
        if self.processing:
            self._warningProcessNotFinished()
            return

        self.ui.lwTaskList.clear()

    def _on_about(self):
        language_label = i18n.LANGUAGES.get(self.current_language, self.current_language)
        QMessageBox.information(
            self,
            i18n.text("about", self.current_language),
            i18n.text("about_text", self.current_language).format(
                version=APP_VERSION,
                language=language_label,
            ),
        )

    def _on_start(self):
        if self.processing:
            self._warningProcessNotFinished()
            return

        item_count = self.ui.lwTaskList.count()
        if item_count == 0:
            return

        output_format = self._get_output_format()
        if output_format == "mp3":
            ret = QMessageBox.warning(
                self,
                i18n.text("warning_title", self.current_language),
                i18n.text("mp3_warning", self.current_language),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if ret == QMessageBox.Cancel:
                return

        class WorkThread(QThread):
            oneFinished = Signal()
            errorOccurred = Signal(str, str)

            def __init__(self, filenames: List[str], window: MainWindow, output_ext: str):
                super().__init__()

                self.filenames = filenames
                self.win = window
                self.output_ext = output_ext

            def run(self):
                for filename in self.filenames:
                    try:
                        ok = self._process_file(filename)
                        if not ok:
                            self.errorOccurred.emit(filename, "Skipped by user.")
                    finally:
                        self.oneFinished.emit()

            def _process_file(self, filename: str) -> bool:
                try:
                    audio, sr = soundfile.read(filename, dtype=np.float32)
                    self._process_audio(filename, audio, sr, filename)
                    return True
                except Exception as exc:
                    choice = self.win._request_fallback_choice(filename, str(exc))
                    if choice == "ffmpeg":
                        return self._process_with_ffmpeg(filename)
                    if choice == "librosa":
                        return self._process_with_librosa(filename)
                    return False

            def _process_audio(self, source_filename: str, audio: np.ndarray, sr: int, preview_source: str):
                is_mono = True
                if len(audio.shape) > 1:
                    is_mono = False
                    audio = audio.T
                slicer = Slicer(
                    sr=sr,
                    threshold=float(self.win.ui.leThreshold.text()),
                    min_length=int(self.win.ui.leMinLen.text()),
                    min_interval=int(self.win.ui.leMinInterval.text()),
                    hop_size=int(self.win.ui.leHopSize.text()),
                    max_sil_kept=int(self.win.ui.leMaxSilence.text())
                )
                sil_tags, total_frames, waveform_shape = slicer.get_slice_tags(audio)

                preview = SlicingPreview(
                    filename=preview_source,
                    sil_tags=sil_tags,
                    hop_size=int(self.win.ui.leHopSize.text()),
                    total_frames=total_frames,
                    waveform_shape=waveform_shape,
                    theme=self.win._get_theme(),
                    language=self.win.current_language,
                )
                preview.save_plot('preview.png')

                chunks = slicer.slice(audio, sil_tags, total_frames)
                out_dir = self.win.ui.leOutputDir.text()
                if out_dir == '':
                    out_dir = os.path.dirname(os.path.abspath(source_filename))
                else:
                    # Make dir if not exists
                    info = QDir(out_dir)
                    if not info.exists():
                        info.mkpath(out_dir)

                self.win.last_output_dir = out_dir
                base_name = os.path.basename(source_filename).rsplit('.', maxsplit=1)[0]

                for i, chunk in enumerate(chunks):
                    path = os.path.join(out_dir, f'{base_name}_{i}.{self.output_ext}')
                    if not is_mono:
                        chunk = chunk.T
                    soundfile.write(path, chunk, sr)

            def _process_with_ffmpeg(self, filename: str) -> bool:
                if not shutil.which("ffmpeg"):
                    self.errorOccurred.emit(
                        filename,
                        i18n.text("ffmpeg_not_found", self.win.current_language),
                    )
                    return False
                with tempfile.NamedTemporaryFile(
                    prefix="audio_slicer_decode_",
                    suffix=".wav",
                    delete=False,
                ) as tmp:
                    temp_path = tmp.name
                try:
                    result = subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            filename,
                            "-vn",
                            "-acodec",
                            "pcm_s16le",
                            temp_path,
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        self.errorOccurred.emit(
                            filename,
                            i18n.text("ffmpeg_failed", self.win.current_language).format(
                                error=result.stderr.strip() or result.stdout.strip(),
                            ),
                        )
                        return False
                    audio, sr = soundfile.read(temp_path, dtype=np.float32)
                    self._process_audio(filename, audio, sr, temp_path)
                    return True
                finally:
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

            def _process_with_librosa(self, filename: str) -> bool:
                try:
                    import librosa
                except Exception as exc:
                    self.errorOccurred.emit(filename, str(exc))
                    return False
                try:
                    audio, sr = librosa.load(filename, sr=None, mono=False)
                    audio_for_process = audio.T if audio.ndim > 1 else audio
                    with tempfile.NamedTemporaryFile(
                        prefix="audio_slicer_decode_",
                        suffix=".wav",
                        delete=False,
                    ) as tmp:
                        temp_path = tmp.name
                    soundfile.write(temp_path, audio_for_process, sr)
                    self._process_audio(filename, audio_for_process, sr, temp_path)
                    return True
                except Exception as exc:
                    self.errorOccurred.emit(filename, str(exc))
                    return False
                finally:
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

        # Collect paths
        paths: list[str] = []
        for i in range(0, item_count):
            item = self.ui.lwTaskList.item(i)
            path = item.data(Qt.ItemDataRole.UserRole + 1)  # Get full path
            paths.append(path)

        self.ui.progressBar.setMaximum(item_count)
        self.ui.progressBar.setValue(0)

        self.workCount = item_count
        self.workFinished = 0
        self._setProcessing(True)

        # Start work thread
        worker = WorkThread(paths, self, output_format)
        worker.oneFinished.connect(self._oneFinished)
        worker.errorOccurred.connect(self._on_worker_error)
        worker.finished.connect(self._threadFinished)
        worker.start()

        self.workers.append(worker)  # Collect in case of auto deletion

    def _oneFinished(self):
        self.workFinished += 1
        self.ui.progressBar.setValue(self.workFinished)

    def _on_worker_error(self, filename: str, error: str):
        QMessageBox.warning(
            self,
            i18n.text("warning_title", self.current_language),
            i18n.text("read_failed", self.current_language).format(
                file=filename,
                error=error,
            ),
        )

    def _request_fallback_choice(self, filename: str, error: str) -> str:
        bridge = self._fallback_bridge
        bridge.mutex.lock()
        bridge.choice = None
        bridge.request.emit(filename, error)
        while bridge.choice is None:
            bridge.cond.wait(bridge.mutex)
        choice = bridge.choice or "cancel"
        bridge.mutex.unlock()
        return choice

    def _threadFinished(self):
        # Join all workers
        for worker in self.workers:
            worker.wait()
        self.workers.clear()
        self._setProcessing(False)

        QMessageBox.information(
            self,
            QApplication.applicationName(),
            i18n.text("slicing_complete", self.current_language),
        )
        if self.ui.cbxOpenOutuptDirectory.isChecked() and self.last_output_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_output_dir))

    def _warningProcessNotFinished(self):
        QMessageBox.warning(
            self,
            QApplication.applicationName(),
            i18n.text("process_not_finished", self.current_language),
        )

    def _setProcessing(self, processing: bool):
        is_enabled = not processing
        self.ui.btnStart.setText(
            i18n.text("slicing", self.current_language) if processing else i18n.text("start", self.current_language))
        self.ui.btnStart.setEnabled(is_enabled)
        self.ui.btnPreviewSelection.setEnabled(is_enabled)
        self.ui.btnAddFiles.setEnabled(is_enabled)
        self.ui.lwTaskList.setEnabled(is_enabled)
        self.ui.btnClearList.setEnabled(is_enabled)
        self.ui.leThreshold.setEnabled(is_enabled)
        self.ui.leMinLen.setEnabled(is_enabled)
        self.ui.leMinInterval.setEnabled(is_enabled)
        self.ui.leHopSize.setEnabled(is_enabled)
        self.ui.leMaxSilence.setEnabled(is_enabled)
        self.ui.leOutputDir.setEnabled(is_enabled)
        self.ui.btnBrowse.setEnabled(is_enabled)
        self.ui.cbLanguage.setEnabled(is_enabled)
        self.processing = processing

    def _init_language_selector(self):
        self.ui.cbLanguage.clear()
        for code, label in i18n.LANGUAGES.items():
            self.ui.cbLanguage.addItem(label, code)
        idx = self.ui.cbLanguage.findData(self.current_language)
        if idx >= 0:
            self.ui.cbLanguage.setCurrentIndex(idx)
        self.ui.cbLanguage.currentIndexChanged.connect(self._on_language_changed)

    def _on_language_changed(self, index: int):
        code = self.ui.cbLanguage.itemData(index)
        if isinstance(code, str) and code:
            self.current_language = code
            self._apply_language()

    def _apply_language(self):
        self.setWindowTitle(i18n.text("window_title", self.current_language))
        self.ui.btnAddFiles.setText(i18n.text("add_files", self.current_language))
        self.ui.btnAbout.setText(i18n.text("about", self.current_language))
        self.ui.groupBox.setTitle(i18n.text("task_list", self.current_language))
        self.ui.btnRemove.setText(i18n.text("remove", self.current_language))
        self.ui.btnClearList.setText(i18n.text("clear_list", self.current_language))
        self.ui.groupBox_2.setTitle(i18n.text("settings", self.current_language))
        self.ui.label_2.setText(i18n.text("threshold", self.current_language))
        self.ui.label_3.setText(i18n.text("min_length", self.current_language))
        self.ui.label_4.setText(i18n.text("min_interval", self.current_language))
        self.ui.label_5.setText(i18n.text("hop_size", self.current_language))
        self.ui.label_6.setText(i18n.text("max_silence", self.current_language))
        self.ui.labelLanguage.setText(i18n.text("language", self.current_language))
        self.ui.btnPreviewSelection.setText(i18n.text("preview_selection", self.current_language))
        self.ui.label_7.setText(i18n.text("output_directory", self.current_language))
        self.ui.btnBrowse.setText(i18n.text("browse", self.current_language))
        self.ui.labelOutputFormat.setText(i18n.text("output_format", self.current_language))
        self.ui.cbxOpenOutuptDirectory.setText(i18n.text("open_output_directory", self.current_language))
        self.ui.btnStart.setText(
            i18n.text("slicing", self.current_language) if self.processing else i18n.text("start", self.current_language)
        )

    def _get_output_format(self) -> str:
        checked = self.ui.outputFormatGroup.checkedButton()
        if checked is None:
            return "wav"
        return checked.text()

    def _get_theme(self) -> str:
        color = self.palette().color(QPalette.Window)
        return "dark" if color.value() < 128 else "light"

    def _on_preview_selection(self):
        if self.processing:
            self._warningProcessNotFinished()
            return
        item = self.ui.lwTaskList.currentItem()
        if item is None:
            QMessageBox.information(
                self,
                QApplication.applicationName(),
                i18n.text("preview_no_selection", self.current_language),
            )
            return
        filename = item.data(Qt.ItemDataRole.UserRole + 1)
        if not filename:
            return
        try:
            self._preview_with_file(filename)
        except Exception as exc:
            self._on_preview_error(filename, str(exc))

    def _preview_with_file(self, filename: str):
        audio, sr = soundfile.read(filename, dtype=np.float32)
        if len(audio.shape) > 1:
            audio = audio.T
        slicer = Slicer(
            sr=sr,
            threshold=float(self.ui.leThreshold.text()),
            min_length=int(self.ui.leMinLen.text()),
            min_interval=int(self.ui.leMinInterval.text()),
            hop_size=int(self.ui.leHopSize.text()),
            max_sil_kept=int(self.ui.leMaxSilence.text()),
        )
        sil_tags, total_frames, waveform_shape = slicer.get_slice_tags(audio)
        preview = SlicingPreview(
            filename=filename,
            sil_tags=sil_tags,
            hop_size=int(self.ui.leHopSize.text()),
            total_frames=total_frames,
            waveform_shape=waveform_shape,
            theme=self._get_theme(),
            language=self.current_language,
        )
        preview_path = os.path.join(tempfile.gettempdir(), "audio_slicer_preview.png")
        preview.save_plot(preview_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(preview_path))

    def _on_preview_error(self, filename: str, error: str):
        choice = self._show_fallback_dialog("preview_read_failed", filename, error)
        if choice == "ffmpeg":
            self._preview_with_ffmpeg(filename)
        elif choice == "librosa":
            self._preview_with_librosa(filename)

    def _show_fallback_dialog(self, prompt_key: str, filename: str, error: str) -> str:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle(i18n.text("warning_title", self.current_language))
        msg.setText(
            i18n.text(prompt_key, self.current_language).format(
                file=filename,
                error=error,
            )
        )
        btn_ffmpeg = msg.addButton(
            i18n.text("preview_use_ffmpeg", self.current_language),
            QMessageBox.ActionRole,
        )
        btn_librosa = msg.addButton(
            i18n.text("preview_use_librosa", self.current_language),
            QMessageBox.ActionRole,
        )
        msg.addButton(QMessageBox.Cancel)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_ffmpeg:
            return "ffmpeg"
        if clicked == btn_librosa:
            return "librosa"
        return "cancel"

    def _preview_with_ffmpeg(self, filename: str):
        if not shutil.which("ffmpeg"):
            QMessageBox.warning(
                self,
                i18n.text("warning_title", self.current_language),
                i18n.text("ffmpeg_not_found", self.current_language),
            )
            return
        with tempfile.NamedTemporaryFile(
            prefix="audio_slicer_preview_",
            suffix=".wav",
            delete=False,
        ) as tmp:
            temp_path = tmp.name
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                filename,
                "-vn",
                "-acodec",
                "pcm_s16le",
                temp_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            QMessageBox.warning(
                self,
                i18n.text("warning_title", self.current_language),
                i18n.text("ffmpeg_failed", self.current_language).format(
                    error=result.stderr.strip() or result.stdout.strip(),
                ),
            )
            return
        try:
            self._preview_with_file(temp_path)
        except Exception as exc:
            QMessageBox.warning(
                self,
                i18n.text("warning_title", self.current_language),
                i18n.text("read_failed", self.current_language).format(
                    file=filename,
                    error=str(exc),
                ),
            )

    def _preview_with_librosa(self, filename: str):
        try:
            import librosa
        except Exception as exc:
            QMessageBox.warning(
                self,
                i18n.text("warning_title", self.current_language),
                i18n.text("read_failed", self.current_language).format(
                    file=filename,
                    error=str(exc),
                ),
            )
            return
        try:
            audio, sr = librosa.load(filename, sr=None, mono=False)
            if audio.ndim > 1:
                audio_to_write = audio.T
            else:
                audio_to_write = audio
            with tempfile.NamedTemporaryFile(
                prefix="audio_slicer_preview_",
                suffix=".wav",
                delete=False,
            ) as tmp:
                temp_path = tmp.name
            soundfile.write(temp_path, audio_to_write, sr)
            self._preview_with_file(temp_path)
        except Exception as exc:
            QMessageBox.warning(
                self,
                i18n.text("warning_title", self.current_language),
                i18n.text("read_failed", self.current_language).format(
                    file=filename,
                    error=str(exc),
                ),
            )

    # Event Handlers
    def closeEvent(self, event):
        if self.processing:
            self._warningProcessNotFinished()
            event.ignore()

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        has_wav = False
        for url in urls:
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1]
            if ext[1:].lower() in self.availableFormats:
                has_wav = True
                break
        if has_wav:
            event.accept()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        for url in urls:
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1]
            if ext[1:].lower() not in self.availableFormats:
                continue
            item = QListWidgetItem()
            item.setSizeHint(QSize(200, 24))
            item.setText(QFileInfo(path).fileName())
            item.setData(Qt.ItemDataRole.UserRole + 1,
                         path)
            self.ui.lwTaskList.addItem(item)
