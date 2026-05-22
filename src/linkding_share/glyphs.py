"""Glyph registry — maps semantic names to ASCII / Nerd Font pairs."""

from __future__ import annotations

GLYPHS: dict[str, tuple[str, str]] = {
    "unread":       ("●",  "\U000f0765"),  # nf-md-record
    "read":         ("·",  "\U000f12fc"),  # nf-md-circle_small_outline
    "sort_asc":     ("↑",  "\U000f005d"),  # nf-md-arrow_up
    "sort_desc":    ("↓",  "\U000f0045"),  # nf-md-arrow_down
    "link":         ("",   "\U000f0337"),  # nf-md-link_variant
    "clock":        ("",   "\U000f0150"),  # nf-md-clock_outline
    "tag":          ("",   "\U000f04f9"),  # nf-md-tag_outline
    "toggle_on":    ("●",  "\U000f0521"),  # nf-md-toggle_switch
    "toggle_off":   ("○",  "\U000f0522"),  # nf-md-toggle_switch_off_outline
    "linkding_on":  ("●",  "\U000f0339"),  # nf-md-link_box_variant
    "linkding_off": ("○",  "\U000f0337"),  # nf-md-link_variant
    "add":          ("+",  "\U000f0415"),  # nf-md-plus_circle_outline
    "delete":       ("x",  "\U000f0a7a"),  # nf-md-delete_outline
    "edit":         ("~",  "\U000f03eb"),  # nf-md-pencil_outline
}

_mode = "ascii"


def set_glyph_mode(mode: str) -> None:
    global _mode
    _mode = "nerd" if mode == "nerd" else "ascii"


def get_glyph_mode() -> str:
    return _mode


def glyph(name: str) -> str:
    pair = GLYPHS.get(name)
    if pair is None:
        return ""
    ascii_g, nerd_g = pair
    return nerd_g if _mode == "nerd" else ascii_g


def glyph_prefix(name: str) -> str:
    g = glyph(name)
    return f"{g} " if g else ""


def resolve_mode(setting: str, has_nerd_font: bool) -> str:
    if setting == "on":
        return "nerd"
    if setting == "off":
        return "ascii"
    return "nerd" if has_nerd_font else "ascii"
