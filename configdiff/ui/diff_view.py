"""Incremental, color-coded display of comparison results."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor

from configdiff.core.diff_engine import DiffResult, DiffRow
from configdiff.ui.text_editor import TextEditor


COLORS = {
    "equal": ("#c5c9ce", "#202226"),
    "added": ("#a6c9ad", "#26382e"),
    "deleted": ("#d2aaa8", "#3a2b2d"),
    "modified_old": ("#d4b09e", "#3b302b"),
    "modified_new": ("#d8c89a", "#3a3529"),
    "eof": ("#d8c89a", "#3a3529"),
}
PREFIXES = {
    "equal": "  ", "added": "+ ", "deleted": "- ",
    "modified_old": "- ", "modified_new": "+ ", "eof": "~ ",
}


class DiffView(TextEditor):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, read_only=True)
        self.setObjectName("diffView")
        self.setPlaceholderText("在上方粘贴或打开两份文本，然后点击“开始对比”。")
        self._result: DiffResult | None = None
        self._next_row = 0
        self._cursor = QTextCursor(self.document())
        self._render_callback = None
        self._generation = 0

    def clear_result(self) -> None:
        self._generation += 1
        self._result = None
        self._render_callback = None
        self.setUpdatesEnabled(True)
        self.clear()

    def show_result(self, result: DiffResult, callback=None) -> None:
        self._generation += 1
        generation = self._generation
        self._result = result
        self._next_row = 0
        self._render_callback = callback
        self.clear()
        self._cursor = QTextCursor(self.document())
        self.setUpdatesEnabled(False)
        QTimer.singleShot(0, lambda: self._render_chunk(generation))

    def _render_chunk(self, generation: int) -> None:
        if generation != self._generation:
            return
        result = self._result
        if result is None:
            return
        end = min(self._next_row + 250, len(result.rows))
        self._cursor.beginEditBlock()
        for index in range(self._next_row, end):
            if index:
                self._cursor.insertBlock()
            self._insert_row(result.rows[index])
        self._cursor.endEditBlock()
        self._next_row = end
        if end < len(result.rows):
            QTimer.singleShot(0, lambda: self._render_chunk(generation))
        else:
            self.setUpdatesEnabled(True)
            self.viewport().update()
            self.moveCursor(QTextCursor.MoveOperation.Start)
            if self._render_callback:
                self._render_callback()

    def _insert_row(self, row: DiffRow) -> None:
        foreground, background = COLORS[row.kind]
        block_format = QTextBlockFormat()
        block_format.setBackground(QColor(background))
        self._cursor.setBlockFormat(block_format)
        base_format = QTextCharFormat()
        base_format.setForeground(QColor(foreground))
        prefix_format = QTextCharFormat(base_format)
        prefix_format.setFontWeight(QFont.Weight.Bold)
        self._cursor.insertText(PREFIXES[row.kind], prefix_format)
        position = 0
        for start, stop in row.changed_spans:
            if start > position:
                self._cursor.insertText(row.text[position:start], base_format)
            emphasis = QTextCharFormat(base_format)
            emphasis.setForeground(QColor("#f2e1bb" if row.kind == "modified_new" else "#edc4b1"))
            emphasis.setBackground(QColor("#65533a" if row.kind == "modified_new" else "#69433c"))
            emphasis.setFontWeight(QFont.Weight.Bold)
            self._cursor.insertText(row.text[start:stop], emphasis)
            position = stop
        if position < len(row.text):
            self._cursor.insertText(row.text[position:], base_format)

    def jump_to_row(self, row_number: int) -> None:
        block = self.document().findBlockByNumber(row_number)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus()
