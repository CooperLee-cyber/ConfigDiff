"""Manual large-text UI smoke check: python -m tests.smoke_ui."""

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from configdiff.ui.main_window import MainWindow


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    old = [f"interface Ethernet0/{i}  description 配置{i}" for i in range(10000)]
    new = old[:5000] + [f" inserted route {i}" for i in range(50)] + old[5000:]
    window.old_editor.setPlainText("\n".join(old) + "\n")
    window.new_editor.setPlainText("\n".join(new) + "\n")
    window.show()
    started = time.perf_counter()
    window._compare()
    state = {"done": False}

    def check() -> None:
        result = window._result
        if result and window.diff_view._next_row == len(result.rows):
            assert (result.additions, result.deletions, result.modifications) == (50, 0, 0)
            assert window.diff_view.blockCount() == 10050
            print(f"UI render: {time.perf_counter() - started:.2f}s, {window.diff_view.blockCount()} rows")
            state["done"] = True
            app.quit()

    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(100)
    QTimer.singleShot(30000, app.quit)
    app.exec()
    assert state["done"], "large-text UI rendering timed out"


if __name__ == "__main__":
    main()
