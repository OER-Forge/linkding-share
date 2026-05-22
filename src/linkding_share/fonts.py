"""Font detection and optional Alacritty font integration."""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

RECOMMENDED_FONTS: list[tuple[str, str, str]] = [
    ("JetBrainsMono Nerd Font", "JetBrainsMono Nerd Font", "brew install --cask font-jetbrains-mono-nerd-font"),
    ("MesloLG Nerd Font",       "MesloLG Nerd Font",       "brew install --cask font-meslo-lg-nerd-font"),
    ("FiraCode Nerd Font",      "FiraCode Nerd Font",       "brew install --cask font-fira-code-nerd-font"),
    ("Hack Nerd Font",          "Hack Nerd Font",           "brew install --cask font-hack-nerd-font"),
    ("IosevkaTerm Nerd Font",   "IosevkaTerm Nerd Font",    "brew install --cask font-iosevka-term-nerd-font"),
]


@dataclass(frozen=True)
class FontStatus:
    has_fc_list: bool
    installed: list[str]
    has_any_nerd_font: bool


def _fc_list_output() -> str | None:
    if not shutil.which("fc-list"):
        return None
    try:
        result = subprocess.run(["fc-list"], capture_output=True, text=True, timeout=5)
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def detect_fonts() -> FontStatus:
    output = _fc_list_output()
    if output is None:
        return FontStatus(has_fc_list=False, installed=[], has_any_nerd_font=False)
    installed: list[str] = []
    for display, keyword, _ in RECOMMENDED_FONTS:
        if keyword.lower() in output.lower():
            installed.append(display)
    has_nerd = "nerd font" in output.lower()
    return FontStatus(has_fc_list=True, installed=installed, has_any_nerd_font=has_nerd)


ALACRITTY_CONFIG_DIR = Path.home() / ".config" / "alacritty"
ALACRITTY_CONFIG_PATH = ALACRITTY_CONFIG_DIR / "alacritty.toml"
LINKDING_SHARE_FONT_INCLUDE = ALACRITTY_CONFIG_DIR / "linkding-share-font.toml"


def alacritty_available() -> bool:
    return ALACRITTY_CONFIG_PATH.exists()


@dataclass(frozen=True)
class AlacrittyFont:
    family: str
    size: float


def _font_from_toml(path: Path) -> AlacrittyFont | None:
    if not path.exists():
        return None
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    font_tbl = data.get("font", {})
    if not isinstance(font_tbl, dict):
        return None
    normal = font_tbl.get("normal", {})
    family = normal.get("family") if isinstance(normal, dict) else None
    size = font_tbl.get("size")
    if not isinstance(family, str) or not isinstance(size, (int, float)):
        return None
    return AlacrittyFont(family=family, size=float(size))


def read_alacritty_font() -> AlacrittyFont | None:
    f = _font_from_toml(LINKDING_SHARE_FONT_INCLUDE)
    if f is not None:
        return f
    return _font_from_toml(ALACRITTY_CONFIG_PATH)


def _toml_str(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_font_include(font: AlacrittyFont) -> str:
    size_str = str(int(font.size)) if float(font.size).is_integer() else repr(font.size)
    return f"""# Managed by linkding-share. Do not edit manually.

[font]
size = {size_str}

[font.normal]
family = {_toml_str(font.family)}
style = "Regular"

[font.bold]
family = {_toml_str(font.family)}
style = "Bold"

[font.italic]
family = {_toml_str(font.family)}
style = "Italic"

[font.bold_italic]
family = {_toml_str(font.family)}
style = "Bold Italic"
"""


def _find_section(lines: list[str], name: str) -> int | None:
    target = f"[{name}]"
    for i, line in enumerate(lines):
        if line.strip() == target:
            return i
    return None


def _section_end(lines: list[str], section_start: int) -> int:
    for j in range(section_start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("[") and stripped.endswith("]") and not stripped.startswith("[["):
            return j
    return len(lines)


def _is_inside_general_section(lines: list[str], idx: int) -> bool:
    for j in range(idx - 1, -1, -1):
        stripped = lines[j].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            return stripped == "[general]"
    return False


def _ensure_import(main_config: Path, include_path: Path) -> None:
    text = main_config.read_text()
    include_str = str(include_path)
    lines = text.splitlines()
    pruned: list[str] = []
    skip_next_blank = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "# linkding-share managed font include":
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if nxt.startswith("import") and "[" in nxt and "]" in nxt:
                skip_next_blank = True
                continue
        is_top_level_import = (
            line == line.lstrip()
            and stripped.startswith("import")
            and "[" in stripped
            and stripped.endswith("]")
            and not _is_inside_general_section(lines, i)
        )
        if is_top_level_import and "linkding-share-font.toml" in stripped:
            skip_next_blank = True
            continue
        if skip_next_blank and stripped == "":
            skip_next_blank = False
            continue
        skip_next_blank = False
        pruned.append(line)
    lines = pruned
    general_idx = _find_section(lines, "general")
    if general_idx is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("[general]")
        lines.append(f"import = [{_toml_str(include_str)}]")
    else:
        section_end = _section_end(lines, general_idx)
        import_idx = None
        for j in range(general_idx + 1, section_end):
            stripped = lines[j].strip()
            if stripped.startswith("import") and "[" in stripped and stripped.endswith("]"):
                import_idx = j
                break
        if import_idx is None:
            lines.insert(general_idx + 1, f"import = [{_toml_str(include_str)}]")
        else:
            existing = lines[import_idx]
            if include_str not in existing:
                idx = existing.rfind("]")
                prefix = existing[:idx].rstrip()
                sep = ", " if not prefix.endswith("[") else ""
                lines[import_idx] = f"{prefix}{sep}{_toml_str(include_str)}]"
    new_text = "\n".join(lines)
    if text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    main_config.write_text(new_text)


def _strip_font_section(main_config: Path) -> None:
    text = main_config.read_text()
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s == "[font]" or s.startswith("[font."):
            start = i
            break
    if start is None:
        return
    backup = main_config.with_suffix(main_config.suffix + ".bak")
    if not backup.exists():
        backup.write_text(text)
    end = start
    while end < len(lines):
        if end == start:
            end += 1
            continue
        s = lines[end].strip()
        if s.startswith("[") and s.endswith("]") and not s.startswith("[["):
            if s == "[font]" or s.startswith("[font."):
                end += 1
                continue
            break
        end += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    if start > 0 and lines[start - 1].strip() == "":
        start -= 1
    new_lines = lines[:start] + lines[end:]
    new_text = "\n".join(new_lines)
    if text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    main_config.write_text(new_text)


def write_alacritty_font(family: str, size: float) -> None:
    ALACRITTY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    include_text = _render_font_include(AlacrittyFont(family=family, size=size))
    tmp = LINKDING_SHARE_FONT_INCLUDE.with_suffix(LINKDING_SHARE_FONT_INCLUDE.suffix + ".tmp")
    tmp.write_text(include_text)
    tmp.replace(LINKDING_SHARE_FONT_INCLUDE)
    if ALACRITTY_CONFIG_PATH.exists():
        _strip_font_section(ALACRITTY_CONFIG_PATH)
        _ensure_import(ALACRITTY_CONFIG_PATH, LINKDING_SHARE_FONT_INCLUDE)


def installed_nerd_font_families() -> list[str]:
    output = _fc_list_output()
    if output is None:
        return []
    families: set[str] = set()
    for line in output.splitlines():
        if "nerd font" not in line.lower():
            continue
        try:
            after_path = line.split(": ", 1)[1]
            family_part = after_path.split(":style=", 1)[0]
            family = family_part.split(",")[0].strip()
        except IndexError:
            continue
        if family:
            families.add(family)
    return sorted(families)
