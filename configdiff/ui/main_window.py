"""Main window, actions, background comparison, and result navigation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy,
    QSplitter, QSplitterHandle, QVBoxLayout, QWidget,
)

from configdiff.core.diff_engine import DiffResult, compare_text
from configdiff.core.file_io import read_text_file
from configdiff.ui.diff_view import DiffView
from configdiff.ui.text_editor import TextEditor


STYLE = """
QMainWindow, QWidget { background: #1b1e22; color: #c9ced4; }
QFrame#toolbar { background: #24282d; border: 1px solid #343a40; border-radius: 7px; }
QLabel#brandMark { background: #536f80; color: #f2f5f7; border-radius: 6px;
                    font-size: 11px; font-weight: 700; }
QLabel#brandTitle { color: #e5e8eb; font-size: 16px; font-weight: 650; }
QLabel#brandSubtitle { color: #929ba4; font-size: 11px; }
QFrame#panel { background: #23272b; border: 1px solid #363d43; border-radius: 7px; }
QLabel#panelTitle { font-size: 13px; font-weight: 600; color: #e0e4e8; }
QLabel#muted { color: #a4adb5; }
QLabel#countBadge { color: #aab4bd; background: #2b3035; border-radius: 8px;
                     padding: 2px 7px; font-size: 11px; }
QFrame#toolbarDivider { background: #41484e; max-width: 1px; min-width: 1px; }
QLabel#added { color: #a6c9ad; }
QLabel#deleted { color: #d2aaa8; }
QLabel#modified { color: #d8c89a; }
QPlainTextEdit { background: #1e2226; color: #cbd1d7; border: 0; selection-background-color: #455c6b; }
QPushButton { background: #30363c; border: 1px solid #454d54; border-radius: 5px;
              padding: 6px 10px; color: #d2d8dd; }
QPushButton:hover { background: #3b434a; border-color: #59636c; }
QPushButton:pressed { background: #464f57; }
QPushButton:disabled { color: #818990; background: #292e33; border-color: #373e44; }
QPushButton#primary { background: #577386; border-color: #68889a; color: #f5f7f8;
                      font-weight: 600; padding-left: 15px; padding-right: 15px; }
QPushButton#primary:hover { background: #648398; border-color: #7d9dad; }
QPushButton#quietButton { background: transparent; border-color: transparent; }
QPushButton#quietButton:hover { background: #343a40; border-color: #434b52; }
QCheckBox { color: #cbd1d7; spacing: 7px; padding: 5px 4px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #7b8993;
                       border-radius: 4px; background: #292f34; }
QCheckBox::indicator:checked { background: #648398; border-color: #a1bac8; }
QStatusBar { background: #22262a; color: #adb5bc; border-top: 1px solid #363d43; }
QScrollBar:vertical { background: #262c31; border: 1px solid #414a51; width: 14px; margin: 1px; }
QScrollBar:horizontal { background: #262c31; border: 1px solid #414a51; height: 14px; margin: 1px; }
QScrollBar::handle:vertical { background: #687c89; border: 1px solid #8298a6;
                              border-radius: 5px; margin: 2px 1px; min-height: 34px; }
QScrollBar::handle:horizontal { background: #687c89; border: 1px solid #8298a6;
                                border-radius: 5px; margin: 1px 2px; min-width: 34px; }
QScrollBar::handle:hover { background: #829aa8; border-color: #a9bdc8; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


class GripSplitterHandle(QSplitterHandle):
    """A visible, compact resize grip for the vertical editor stack."""

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self.setCursor(Qt.CursorShape.SizeVerCursor)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#343b41"))
        center_x = self.width() // 2
        center_y = self.height() // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#9caab4" if self.underMouse() else "#788792"))
        for offset in (-9, 0, 9):
            painter.drawRoundedRect(center_x + offset - 2, center_y - 2, 4, 4, 2, 2)


class GripSplitter(QSplitter):
    def createHandle(self) -> QSplitterHandle:  # noqa: N802 - Qt API
        return GripSplitterHandle(self.orientation(), self)


def _monospace_font() -> QFont:
    available = set(QFontDatabase.families())
    for family in ("Cascadia Code", "Consolas", "JetBrains Mono", "Courier New"):
        if family in available:
            font = QFont(family, 10)
            font.setStyleHint(QFont.StyleHint.Monospace)
            return font
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(10)
    return font


def _line_count(text: str) -> int:
    if not text:
        return 0
    return len(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")) - int(text.endswith(("\r", "\n")))


class CompareThread(QThread):
    def __init__(self, old: str, new: str, revision: int, parent=None) -> None:
        super().__init__(parent)
        self.old = old
        self.new = new
        self.revision = revision
        self.result: DiffResult | None = None
        self.error: Exception | None = None

    def run(self) -> None:
        try:
            self.result = compare_text(self.old, self.new)
        except Exception as exc:  # keep a malformed input from crashing the GUI
            self.error = exc


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Config Diff - 配置文本对比工具")
        self.resize(1200, 850)
        self.setMinimumSize(650, 520)
        self.setStyleSheet(STYLE)
        self._revision = 0
        self._worker: CompareThread | None = None
        self._result: DiffResult | None = None
        self._current_change = -1
        self._suppress_recompute = False
        self._build_ui()
        self.statusBar().showMessage("粘贴文本或打开文件，然后点击“开始对比”。")

    def _button(self, label: str, callback, *, primary: bool = False) -> QPushButton:
        button = QPushButton(label)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        return button

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 12, 14, 9)
        layout.setSpacing(8)

        brand = QHBoxLayout()
        brand.setContentsMargins(2, 0, 2, 0)
        mark = QLabel("CD")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(30, 30)
        brand.addWidget(mark)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_title = QLabel("Config Diff")
        brand_title.setObjectName("brandTitle")
        brand_subtitle = QLabel("配置文本对比")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_text.addWidget(brand_title)
        brand_text.addWidget(brand_subtitle)
        brand.addLayout(brand_text)
        brand.addStretch()
        layout.addLayout(brand)

        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setSpacing(6)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.compare_button = self._button("开始对比", self._compare, primary=True)
        actions.addWidget(self.compare_button)
        actions.addWidget(self._button("交换", self._swap))
        clear_button = self._button("清空", self._clear)
        clear_button.setObjectName("quietButton")
        actions.addWidget(clear_button)
        toolbar_layout.addLayout(actions)
        divider = QFrame()
        divider.setObjectName("toolbarDivider")
        divider.setFixedHeight(22)
        toolbar_layout.addWidget(divider)
        self.wrap_checkbox = QCheckBox("自动换行：关")
        self.wrap_checkbox.setToolTip("仅改变显示方式，不修改原文或对比结果")
        toolbar_layout.addWidget(self.wrap_checkbox)
        toolbar_layout.addStretch(1)
        self.copy_button = self._button("复制 Diff", self._copy_diff)
        self.copy_button.setObjectName("quietButton")
        self.save_button = self._button("保存 Diff", self._save_diff)
        toolbar_layout.addWidget(self.copy_button)
        toolbar_layout.addWidget(self.save_button)
        layout.addWidget(toolbar)

        splitter = GripSplitter(Qt.Orientation.Vertical, central)
        splitter.setHandleWidth(13)
        splitter.setChildrenCollapsible(False)
        splitter.setOpaqueResize(True)
        self.old_editor, self.old_count, old_panel = self._input_panel("原配置", "打开文件…")
        self.new_editor, self.new_count, new_panel = self._input_panel("新配置", "打开文件…")
        old_panel.findChild(QPushButton).clicked.connect(lambda: self._open_file(self.old_editor))
        new_panel.findChild(QPushButton).clicked.connect(lambda: self._open_file(self.new_editor))
        self.old_editor.textChanged.connect(lambda: self._input_changed(self.old_editor, self.old_count))
        self.new_editor.textChanged.connect(lambda: self._input_changed(self.new_editor, self.new_count))

        result_panel = QFrame()
        result_panel.setObjectName("panel")
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(10, 7, 10, 9)
        result_layout.setSpacing(6)
        result_header = QHBoxLayout()
        result_header.setSpacing(9)
        title = QLabel("对比结果 / Diff")
        title.setObjectName("panelTitle")
        result_header.addWidget(title)
        self.stats = QLabel("等待对比")
        self.stats.setObjectName("muted")
        result_header.addWidget(self.stats)
        result_header.addStretch()
        self.previous_button = self._button("上一个差异", self._previous_change)
        self.next_button = self._button("下一个差异", self._next_change)
        self.position_label = QLabel("差异 0 / 0")
        self.position_label.setObjectName("muted")
        result_header.addWidget(self.previous_button)
        result_header.addWidget(self.next_button)
        result_header.addWidget(self.position_label)
        result_layout.addLayout(result_header)
        self.diff_view = DiffView()
        result_layout.addWidget(self.diff_view)

        for panel in (old_panel, new_panel, result_panel):
            panel.setMinimumHeight(100)
            splitter.addWidget(panel)
        splitter.setSizes([240, 240, 350])
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)
        font = _monospace_font()
        for editor in (self.old_editor, self.new_editor, self.diff_view):
            editor.set_monospace_font(font)
        self.wrap_checkbox.toggled.connect(self._set_word_wrap)
        self._update_result_actions()
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._compare)
        QShortcut(QKeySequence("F7"), self, activated=self._previous_change)
        QShortcut(QKeySequence("F8"), self, activated=self._next_change)

    def _set_word_wrap(self, enabled: bool) -> None:
        self.wrap_checkbox.setText("自动换行：开" if enabled else "自动换行：关")
        mode = (QPlainTextEdit.LineWrapMode.WidgetWidth if enabled
                else QPlainTextEdit.LineWrapMode.NoWrap)
        for editor in (self.old_editor, self.new_editor, self.diff_view):
            editor.setLineWrapMode(mode)

    def _input_panel(self, name: str, open_label: str) -> tuple[TextEditor, QLabel, QFrame]:
        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 7, 10, 9)
        panel_layout.setSpacing(6)
        header = QHBoxLayout()
        title = QLabel(name)
        title.setObjectName("panelTitle")
        count = QLabel("0 行")
        count.setObjectName("countBadge")
        header.addWidget(title)
        header.addWidget(count)
        header.addStretch()
        header.addWidget(self._button(open_label, lambda: None))
        panel_layout.addLayout(header)
        editor = TextEditor()
        editor.setPlaceholderText("在此粘贴或输入" + name + "…")
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel_layout.addWidget(editor)
        return editor, count, panel

    def _input_changed(self, editor: TextEditor, label: QLabel) -> None:
        label.setText(f"{_line_count(editor.toPlainText())} 行")
        self._revision += 1
        if self._result is not None:
            self._result = None
            self.diff_view.clear_result()
            self.stats.setText("输入已更改，请重新对比")
            self._current_change = -1
            self._update_result_actions()

    def _compare(self) -> None:
        if self._worker is not None:
            return
        self._suppress_recompute = False
        self.compare_button.setEnabled(False)
        self.stats.setText("正在计算…")
        self.statusBar().showMessage("正在计算差异…")
        self._worker = CompareThread(self.old_editor.toPlainText(), self.new_editor.toPlainText(), self._revision, self)
        self._worker.finished.connect(self._comparison_finished)
        self._worker.start()

    def _comparison_finished(self) -> None:
        worker = self._worker
        if worker is None:
            return
        self._worker = None
        worker.deleteLater()
        if worker.revision != self._revision:
            if self._suppress_recompute:
                self.compare_button.setEnabled(True)
            else:
                self._compare()
            return
        self.compare_button.setEnabled(True)
        if worker.error is not None:
            self.stats.setText("对比失败")
            QMessageBox.critical(self, "对比失败", str(worker.error))
            return
        self._result = worker.result
        self._current_change = -1
        result = self._result
        if result is None:
            return
        if result.identical:
            self.stats.setText("✓ 两份配置完全一致")
            self.diff_view.setPlaceholderText("✓ 两份配置完全一致")
        else:
            self.stats.setText(f"新增：{result.additions} 行    删除：{result.deletions} 行    修改：{result.modifications} 行")
            self.diff_view.setPlaceholderText("")
        self.diff_view.show_result(result, self._render_finished)
        self._update_result_actions()
        self.statusBar().showMessage("对比完成。")

    def _render_finished(self) -> None:
        if self._result and self._result.change_positions:
            self._current_change = 0
            self._update_result_actions()
            self.diff_view.jump_to_row(self._result.change_positions[0])

    def _update_result_actions(self) -> None:
        has_result = self._result is not None
        self.copy_button.setEnabled(has_result)
        self.save_button.setEnabled(has_result)
        count = len(self._result.change_positions) if self._result else 0
        self.previous_button.setEnabled(count > 0)
        self.next_button.setEnabled(count > 0)
        self.position_label.setText(f"差异 {self._current_change + 1 if count else 0} / {count}")

    def _navigate(self, direction: int) -> None:
        if not self._result or not self._result.change_positions:
            return
        self._current_change = (self._current_change + direction) % len(self._result.change_positions)
        self.diff_view.jump_to_row(self._result.change_positions[self._current_change])
        self._update_result_actions()

    def _previous_change(self) -> None:
        self._navigate(-1)

    def _next_change(self) -> None:
        self._navigate(1)

    def _open_file(self, editor: TextEditor) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开文本文件", "", "文本及配置文件 (*.txt *.cfg *.conf *.log *.config);;所有文件 (*)")
        if not path:
            return
        try:
            content, encoding = read_text_file(path)
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, "打开失败", str(exc))
            return
        editor.setPlainText(content)
        editor.setFocus()
        self.statusBar().showMessage(f"已打开 {Path(path).name} · {encoding}")
        if "替换" in encoding:
            QMessageBox.information(self, "编码提示", "文件包含无法识别的字节，已使用替换字符显示。请核对内容。")

    def _swap(self) -> None:
        old, new = self.old_editor.toPlainText(), self.new_editor.toPlainText()
        had_result = self._result is not None
        self.old_editor.setPlainText(new)
        self.new_editor.setPlainText(old)
        if had_result and self._worker is None:
            self._compare()

    def _clear(self) -> None:
        self._suppress_recompute = True
        self.old_editor.clear()
        self.new_editor.clear()
        self._result = None
        self.diff_view.clear_result()
        self.stats.setText("等待对比")
        self._current_change = -1
        self._update_result_actions()
        self.statusBar().showMessage("已清空。")

    def _copy_diff(self) -> None:
        if self._result is None:
            return
        QApplication.clipboard().setText(self._result.display_text)
        self.statusBar().showMessage("Diff 已复制到剪贴板。")

    def _save_diff(self) -> None:
        if self._result is None:
            return
        path, selected_filter = QFileDialog.getSaveFileName(self, "保存 Diff", "ConfigDiff.txt", "文本文件 (*.txt);;Unified Diff (*.diff)")
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".diff" if "*.diff" in selected_filter else ".txt")
        is_unified = target.suffix.lower() == ".diff"
        data = self._result.unified_text if is_unified else self._result.display_text
        try:
            target.write_text(data, encoding="utf-8" if is_unified else "utf-8-sig")
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.statusBar().showMessage(f"已保存到 {target}")

    def closeEvent(self, event):  # noqa: N802 - Qt API
        if self._worker is not None:
            self._worker.wait()
        super().closeEvent(event)
