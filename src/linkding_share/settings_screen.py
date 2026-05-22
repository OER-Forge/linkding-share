"""Settings modal screen."""

from __future__ import annotations

from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from . import __version__
from .config import (
    Config,
    FetchConfig,
    LinkdingConfig,
    ReaderConfig,
    SortConfig,
    TagsConfig,
    UIConfig,
    save_config,
)
from .fonts import (
    alacritty_available,
    installed_nerd_font_families,
    read_alacritty_font,
    write_alacritty_font,
)

COMMON_TIMEZONES = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Anchorage",
    "America/Honolulu",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Australia/Sydney",
]


class SettingsScreen(ModalScreen[bool]):
    """Modal settings editor. Dismisses True if config was saved."""

    CSS = """
    SettingsScreen { align: center middle; }
    #settings-dialog {
        width: 100%;
        height: 100%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #settings-title { text-style: bold; color: $text; padding-bottom: 1; }
    #settings-scroll {
        height: 1fr;
        scrollbar-size-vertical: 2;
        scrollbar-color: $accent;
        scrollbar-background: $boost;
    }
    .field-row { height: 3; padding: 0 0 1 0; }
    .field-label { width: 22; padding: 1 1 0 0; color: $text; text-style: bold; }
    .field-input { width: 1fr; }
    .section-header {
        text-style: bold;
        color: $text;
        background: $primary 30%;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    .tag-cb { height: auto; min-height: 1; padding: 0 0 0 1; }
    #settings-buttons { height: 3; align: right middle; padding-top: 1; }
    #settings-buttons Button { margin-left: 1; }
    #error-line { color: $error; height: 1; padding-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(
        self,
        config: Config,
        on_save: Callable[[Config], None],
        all_tags: list[str] | None = None,
        available_themes: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._on_save = on_save
        self._all_tags = sorted(all_tags or [])
        self._available_themes = sorted(available_themes or [])

    def compose(self) -> ComposeResult:
        cfg = self._config
        tz_name = str(getattr(cfg.timezone, "key", cfg.timezone))
        tz_options = list(dict.fromkeys(COMMON_TIMEZONES + [tz_name]))

        with Vertical(id="settings-dialog"):
            yield Static(
                f"Settings  ·  linkding-share v{__version__}  ·  scroll for more  ·  Ctrl+S save  ·  Esc cancel",
                id="settings-title",
            )
            with VerticalScroll(id="settings-scroll"):
                # Appearance
                yield Static("Appearance", classes="section-header")
                with Horizontal(classes="field-row"):
                    yield Label("Theme", classes="field-label")
                    theme_options = self._available_themes or [cfg.theme]
                    if cfg.theme not in theme_options:
                        theme_options = [cfg.theme] + theme_options
                    yield Select(
                        [(t, t) for t in theme_options],
                        value=cfg.theme,
                        allow_blank=False,
                        id="theme-select",
                        classes="field-input",
                    )
                with Horizontal(classes="field-row"):
                    yield Label("Nerd Font glyphs", classes="field-label")
                    yield Select(
                        [("auto (detect)", "auto"), ("on (force)", "on"), ("off (ASCII)", "off")],
                        value=cfg.ui.nerd_font,
                        allow_blank=False,
                        id="nerd-font-select",
                        classes="field-input",
                    )
                with Horizontal(classes="field-row"):
                    yield Label("Default view", classes="field-label")
                    yield Select(
                        [("All", "all"), ("Unread", "unread"), ("Read", "read")],
                        value=cfg.ui.default_view,
                        allow_blank=False,
                        id="default-view-select",
                        classes="field-input",
                    )

                # Alacritty font (only if detected)
                if alacritty_available():
                    yield Static("Alacritty font  (live-reloads on save)", classes="section-header")
                    families = installed_nerd_font_families()
                    current = read_alacritty_font()
                    current_family = current.family if current else (families[0] if families else "JetBrainsMono Nerd Font")
                    current_size = current.size if current else 13.0
                    family_options = list(dict.fromkeys(families + [current_family]))
                    with Horizontal(classes="field-row"):
                        yield Label("Family", classes="field-label")
                        yield Select(
                            [(f, f) for f in family_options],
                            value=current_family,
                            allow_blank=False,
                            id="font-family",
                            classes="field-input",
                        )
                    with Horizontal(classes="field-row"):
                        yield Label("Size (pt)", classes="field-label")
                        yield Input(value=str(current_size), placeholder="e.g. 13", id="font-size", classes="field-input")

                # Linkding
                yield Static("Linkding", classes="section-header")
                with Horizontal(classes="field-row"):
                    yield Label("URL", classes="field-label")
                    yield Input(value=cfg.linkding.url, placeholder="https://linkding.example.com", id="ld-url", classes="field-input")
                with Horizontal(classes="field-row"):
                    yield Label("API key", classes="field-label")
                    yield Input(value=cfg.linkding.api_key, placeholder="REST API token", password=True, id="ld-key", classes="field-input")

                # Tags
                yield Static(
                    "Tags  (must already exist in linkding — ON = accessible in this tool)",
                    classes="section-header",
                )
                if self._all_tags:
                    for i, tag in enumerate(self._all_tags):
                        on = tag in cfg.tags.allowed
                        yield Checkbox(tag, value=on, id=f"alltag-{i}", classes="tag-cb")
                else:
                    yield Static("[dim]No tags found in linkding (refresh to load)[/]", classes="tag-cb")

                # Sort
                yield Static("Default sort", classes="section-header")
                with Horizontal(classes="field-row"):
                    yield Label("Column", classes="field-label")
                    yield Select(
                        [("time", "time"), ("title", "title"), ("tags", "tags")],
                        value=cfg.sort.column,
                        allow_blank=False,
                        id="sort-col",
                        classes="field-input",
                    )
                with Horizontal(classes="field-row"):
                    yield Label("Direction", classes="field-label")
                    yield Select(
                        [("desc", "desc"), ("asc", "asc")],
                        value=cfg.sort.direction,
                        allow_blank=False,
                        id="sort-dir",
                        classes="field-input",
                    )

                # Fetch
                yield Static("Fetch", classes="section-header")
                with Horizontal(classes="field-row"):
                    yield Label("Auto-refresh (min)", classes="field-label")
                    yield Input(value=str(cfg.fetch.auto_refresh_minutes), placeholder="0 disables, min 1", id="auto-refresh", classes="field-input")

                # Reader
                yield Static("Reader", classes="section-header")
                with Horizontal(classes="field-row"):
                    yield Label("Mark-read seconds", classes="field-label")
                    yield Input(value=str(cfg.reader.mark_read_seconds), placeholder="-1 disables, 0 immediate", id="mark-read", classes="field-input")
                with Horizontal(classes="field-row"):
                    yield Label("Read retention (days)", classes="field-label")
                    yield Input(value=str(cfg.reader.read_retention_days), placeholder="0 keeps forever", id="read-retention", classes="field-input")

                # Timezone
                yield Static("Timezone", classes="section-header")
                with Horizontal(classes="field-row"):
                    yield Label("Preset", classes="field-label")
                    yield Select([(t, t) for t in tz_options], value=tz_name, allow_blank=False, id="tz-select", classes="field-input")
                with Horizontal(classes="field-row"):
                    yield Label("Custom IANA", classes="field-label")
                    yield Input(value=tz_name, placeholder="e.g. America/New_York", id="tz-input", classes="field-input")

            yield Static("", id="error-line")
            with Horizontal(id="settings-buttons"):
                yield Button("Cancel", id="btn-cancel", variant="default")
                yield Button("Save", id="btn-save", variant="primary")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "tz-select" and event.value:
            self.query_one("#tz-input", Input).value = str(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.action_cancel()
        elif event.button.id == "btn-save":
            self.action_save()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_save(self) -> None:
        new_cfg = self._build_config()
        if new_cfg is None:
            return
        font_change = self._read_font_fields()
        if font_change == "invalid":
            return
        try:
            save_config(new_cfg)
        except OSError as e:
            self._show_error(f"Failed to write config: {e}")
            return
        if isinstance(font_change, tuple):
            family, size = font_change
            try:
                write_alacritty_font(family, size)
            except OSError as e:
                self._show_error(f"Saved config; Alacritty font write failed: {e}")
                return
        self._on_save(new_cfg)
        self.dismiss(True)

    def _read_font_fields(self) -> tuple[str, float] | None | str:
        if not alacritty_available():
            return None
        try:
            family_select = self.query_one("#font-family", Select)
            size_input = self.query_one("#font-size", Input)
        except Exception:
            return None
        family = str(family_select.value).strip()
        raw_size = size_input.value.strip()
        try:
            size = float(raw_size)
        except ValueError:
            self._show_error(f"Font size must be a number, got {raw_size!r}")
            return "invalid"
        if size <= 0 or size > 96:
            self._show_error(f"Font size {size} out of range (1–96)")
            return "invalid"
        return (family, size)

    def _show_error(self, msg: str) -> None:
        self.query_one("#error-line", Static).update(msg)

    def _build_config(self) -> Config | None:
        tz_name = self.query_one("#tz-input", Input).value.strip() or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            self._show_error(f"Unknown timezone: {tz_name!r}")
            return None

        raw = self.query_one("#mark-read", Input).value.strip() or "-1"
        try:
            mark_read = float(raw)
        except ValueError:
            self._show_error(f"Mark-read seconds must be a number, got {raw!r}")
            return None

        raw_ret = self.query_one("#read-retention", Input).value.strip() or "0"
        try:
            retention = int(raw_ret)
            if retention < 0:
                raise ValueError
        except ValueError:
            self._show_error(f"Read retention must be a non-negative integer, got {raw_ret!r}")
            return None

        raw_auto = self.query_one("#auto-refresh", Input).value.strip() or "0"
        try:
            auto_min = int(raw_auto)
        except ValueError:
            self._show_error(f"Auto-refresh must be an integer, got {raw_auto!r}")
            return None
        if auto_min < 0:
            self._show_error("Auto-refresh must be 0 (off) or a positive integer")
            return None

        ld = LinkdingConfig(
            url=self.query_one("#ld-url", Input).value.strip().rstrip("/"),
            api_key=self.query_one("#ld-key", Input).value.strip(),
        )

        # Collect allowed tags from checkboxes
        allowed_tags: list[str] = []
        for i, tag in enumerate(self._all_tags):
            try:
                cb = self.query_one(f"#alltag-{i}", Checkbox)
                if cb.value:
                    allowed_tags.append(tag)
            except Exception:
                pass

        sort_col = str(self.query_one("#sort-col", Select).value)
        sort_dir = str(self.query_one("#sort-dir", Select).value)
        theme = str(self.query_one("#theme-select", Select).value)
        nerd = str(self.query_one("#nerd-font-select", Select).value)
        default_view = str(self.query_one("#default-view-select", Select).value)

        return Config(
            linkding=ld,
            tags=TagsConfig(allowed=allowed_tags),
            timezone=tz,
            sort=SortConfig(column=sort_col, direction=sort_dir),
            reader=ReaderConfig(mark_read_seconds=mark_read, read_retention_days=retention),
            fetch=FetchConfig(auto_refresh_minutes=auto_min),
            theme=theme,
            ui=UIConfig(nerd_font=nerd, default_view=default_view),
        )
