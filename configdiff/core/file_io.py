"""Robust loading of ordinary text and configuration files."""

from __future__ import annotations

import locale
from pathlib import Path


def read_text_file(path: str | Path) -> tuple[str, str]:
    data = Path(path).read_bytes()
    if b"\x00" in data and not (data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff")):
        raise ValueError("文件似乎是二进制文件，无法作为纯文本打开。")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "UTF-16"
    encodings = ["utf-8-sig", locale.getpreferredencoding(False), "gb18030"]
    for encoding in dict.fromkeys(encodings):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace"), "UTF-8（含替换字符）"
