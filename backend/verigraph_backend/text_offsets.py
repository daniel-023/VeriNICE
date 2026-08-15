from __future__ import annotations


def utf16_offset(text: str, code_point_offset: int) -> int:
    """Convert a Python code-point offset into a browser UTF-16 offset."""
    if code_point_offset < 0 or code_point_offset > len(text):
        raise ValueError("code point offset is outside the supplied text")
    return len(text[:code_point_offset].encode("utf-16-le")) // 2
