"""Custom theme loading."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path

from textual.theme import Theme

from .config import CONFIG_DIR

THEME_FIELDS = ("primary", "secondary", "accent", "warning", "error", "success", "background", "surface", "panel", "foreground")


def _theme_from_dict(d: dict, source: str, errors: list[str]) -> Theme | None:
    name = d.get("name")
    if not isinstance(name, str) or not name:
        errors.append(f"{source}: theme entry missing 'name'")
        return None
    primary = d.get("primary")
    if not isinstance(primary, str) or not primary:
        errors.append(f"{source}: theme {name!r} missing required 'primary' color")
        return None
    kwargs: dict[str, object] = {"name": name, "primary": primary}
    for field in THEME_FIELDS[1:]:
        if field in d and isinstance(d[field], str) and d[field]:
            kwargs[field] = d[field]
    if "dark" in d and isinstance(d["dark"], bool):
        kwargs["dark"] = d["dark"]
    try:
        return Theme(**kwargs)  # type: ignore[arg-type]
    except Exception as e:
        errors.append(f"{source}: theme {name!r} invalid: {e}")
        return None


def _load_file(path: Path, source: str, errors: list[str]) -> list[Theme]:
    try:
        text = path.read_text()
    except OSError as e:
        errors.append(f"{source}: read failed: {e}")
        return []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        errors.append(f"{source}: parse error: {e}")
        return []
    raw = data.get("theme", [])
    if not isinstance(raw, list):
        errors.append(f"{source}: expected [[theme]] array")
        return []
    out: list[Theme] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        theme = _theme_from_dict(entry, source, errors)
        if theme is not None:
            out.append(theme)
    return out


def load_custom_themes() -> tuple[list[Theme], list[str]]:
    errors: list[str] = []
    themes: list[Theme] = []
    try:
        bundled = files("linkding_share").joinpath("themes.toml")
        with bundled.open("rb") as fh:
            data = tomllib.loads(fh.read().decode("utf-8"))
        for entry in data.get("theme", []):
            if isinstance(entry, dict):
                theme = _theme_from_dict(entry, "bundled themes.toml", errors)
                if theme is not None:
                    themes.append(theme)
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError) as e:
        errors.append(f"bundled themes.toml: {e}")
    user_path = CONFIG_DIR / "themes.toml"
    if user_path.exists():
        themes.extend(_load_file(user_path, "user themes.toml", errors))
    return themes, errors
