import argparse
import re
import sys
import webbrowser

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from rich.text import Text
from textual.widgets import DataTable, Footer, Header, Input, Select, Static

from . import __version__
from .api import create_bookmark, delete_bookmark, fetch_bookmarks, fetch_tags, update_bookmark
from .config import CONFIG_PATH, Config, load_config
from .fetch import BLOCKED_BODY, fetch_body
from .glyphs import glyph, glyph_prefix, resolve_mode, set_glyph_mode
from .models import Bookmark
from .storage import State

ALL = "All"


class BookmarkList(DataTable):
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]


class Reader(Static):
    pass


class LinkdingShareApp(App):
    CSS = """
    Screen { layout: vertical; }
    #filters { height: 3; padding: 0 1; background: $boost; }
    #filters Select { width: 1fr; margin: 0 1; }
    #search-input { display: none; width: 1fr; margin: 0 1; }
    #search-input.visible { display: block; }
    #body { height: 1fr; }
    #list { width: 50%; border-right: solid $primary; }
    #list DataTable { height: 1fr; }
    #reader-pane { width: 1fr; padding: 1 2; overflow-y: auto; }
    #reader-pane:focus { background: $surface; }
    Reader { height: auto; }
    #status { height: 1; padding: 0 1; color: $text-muted; background: $boost; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("a", "add_bookmark", "Add"),
        Binding("e", "edit_bookmark", "Edit"),
        Binding("d", "delete_bookmark", "Delete"),
        Binding("x", "toggle_read", "Mark read"),
        Binding("z", "undo_read", "Undo"),
        Binding("o", "open_browser", "Open"),
        Binding("c", "copy_url", "Copy URL"),
        Binding("u", "cycle_read_filter", "Unread/Read"),
        Binding("question_mark", "open_help", "Help"),
        Binding("slash", "open_search", "Search"),
        Binding("escape", "close_search_or_nothing", "Escape", show=False),
        Binding("comma", "open_settings", "Settings"),
        Binding("1", "sort_by('title')", "Sort: title"),
        Binding("2", "sort_by('tags')", "Sort: tags"),
        Binding("3", "sort_by('when')", "Sort: time"),
        Binding("tab", "focus_reader", "Focus reader", show=False),
        Binding("shift+tab", "focus_list", "Focus list", show=False),
        Binding("space", "scroll_reader_page_down", "Page ↓", priority=True),
        Binding("b", "scroll_reader_page_up", "Page ↑", priority=True),
        Binding("pageup", "scroll_reader_page_up", "Page ↑", show=False, priority=True),
        Binding("pagedown", "scroll_reader_page_down", "Page ↓", show=False, priority=True),
        Binding("ctrl+u", "scroll_reader_up", "Scroll ↑", show=False, priority=True),
        Binding("ctrl+d", "scroll_reader_down", "Scroll ↓", show=False, priority=True),
        Binding("g", "scroll_reader_home", "Top", show=False, priority=True),
        Binding("G", "scroll_reader_end", "Bottom", show=False, priority=True),
    ]

    selected_tag: reactive[str] = reactive(ALL)
    view: reactive[str] = reactive("all")

    VIEW_OPTIONS: list[tuple[str, str]] = [
        ("All", "all"),
        ("Unread", "unread"),
        ("Read", "read"),
    ]

    def __init__(self, preloaded_config: Config | None = None) -> None:
        super().__init__()
        self.config: Config = preloaded_config if preloaded_config is not None else load_config()
        self.state = State(read_retention_days=self.config.reader.read_retention_days)
        self.bookmarks: list[Bookmark] = []
        self.visible_bookmarks: list[Bookmark] = []
        self.body_cache: dict[str, str] = {}
        self.current_id: str | None = None
        self.all_tags: list[str] = []
        self._mark_read_timer = None
        self._auto_refresh_timer = None
        self._loading: bool = False
        col_map = {"time": "when", "title": "title", "tags": "tags"}
        self.sort_column: str = col_map.get(self.config.sort.column, "when")
        self.sort_desc: bool = self.config.sort.direction == "desc"
        self.view = self.config.ui.default_view
        self.search_query: str = ""
        # Default to first allowed tag so the primary sharing tag is active on launch
        if self.config.tags.allowed:
            self.selected_tag = self.config.tags.allowed[0]

    def compose(self) -> ComposeResult:
        tag_options = [(ALL, ALL)] + [(t, t) for t in self.config.tags.allowed]
        yield Header(show_clock=True)
        with Horizontal(id="filters"):
            yield Select(
                self.VIEW_OPTIONS,
                value=self.view,
                allow_blank=False,
                id="view-select",
                prompt="View",
            )
            yield Select(
                tag_options,
                value=self.selected_tag,
                allow_blank=False,
                id="tag-select",
                prompt="Tag",
            )
            yield Input(placeholder="Search…", id="search-input")
        with Horizontal(id="body"):
            with Vertical(id="list"):
                table = BookmarkList(id="bookmark-table", cursor_type="row", zebra_stripes=True)
                table.add_column("", key="marker", width=2)
                table.add_column("Title", key="title")
                table.add_column("Tags", key="tags", width=22)
                table.add_column("When", key="when", width=11)
                yield table
            with VerticalScroll(id="reader-pane", can_focus=True):
                yield Reader("Loading bookmarks…", id="reader", markup=True)
        yield Static("", id="status", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"linkding-share {__version__}"
        self.sub_title = self._subtitle()
        self._register_custom_themes()
        self._apply_theme(self.config.theme)
        self._apply_glyph_mode()
        self.set_focus(self.query_one("#bookmark-table", BookmarkList))
        self._update_status_bar()
        if self.config.load_errors:
            self._flash_status(" · ".join(self.config.load_errors), seconds=8.0)
        self.load_bookmarks()
        self._restart_auto_refresh()

    def _apply_glyph_mode(self) -> None:
        from .fonts import detect_fonts
        has_nerd = detect_fonts().has_any_nerd_font
        set_glyph_mode(resolve_mode(self.config.ui.nerd_font, has_nerd))

    def _register_custom_themes(self) -> None:
        from .themes import load_custom_themes
        themes, errors = load_custom_themes()
        for theme in themes:
            try:
                self.register_theme(theme)
            except Exception as e:
                errors.append(f"register {theme.name}: {e}")
        if errors:
            self.config.load_errors.extend(errors)

    def _apply_theme(self, name: str) -> None:
        if name in self.available_themes:
            self.theme = name
        else:
            self.config.load_errors.append(f"unknown theme {name!r}; using {self.theme!r}")

    def _color(self, var: str) -> str:
        if not var.startswith("$"):
            return var
        return self.get_css_variables().get(var[1:], "white")

    def _subtitle(self) -> str:
        tags = self.config.tags.allowed
        tag_label = ", ".join(tags) if tags else "no tags configured"
        return f"{tag_label} · {self.config.timezone}"

    def _linkding_badge(self) -> str:
        muted = self._color("$text-muted")
        success = self._color("$success")
        if self.config.linkding.enabled:
            host = self.config.linkding.url.split("://", 1)[-1]
            return (
                f"[bold {success}]{glyph('linkding_on')} linkding[/] "
                f"[{muted}]→ {host}[/]"
            )
        return f"[{muted}]{glyph('linkding_off')} linkding not configured[/]"

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#status", Static).update(msg)
        except Exception:
            pass

    def _flash_status(self, msg: str, seconds: float = 4.0) -> None:
        self._set_status(f"{msg}  ·  {self._linkding_badge()}")
        self.set_timer(seconds, self._update_status_bar)

    def _update_status_bar(self) -> None:
        sort_human = {"title": "Title", "tags": "Tags", "when": "Time"}[self.sort_column]
        arrow = glyph("sort_desc") if self.sort_desc else glyph("sort_asc")
        muted = self._color("$text-muted")
        accent = self._color("$accent")
        total = len(self.bookmarks)
        visible = len(self.visible_bookmarks)
        unread = sum(1 for b in self.bookmarks if not self.state.is_read(b.local_id))
        counts = (
            f"[{muted}]{visible}/{total}[/] · "
            f"[bold {accent}]{unread}[/] [{muted}]unread[/]"
        )
        self._set_status(
            f"{counts}  ·  "
            f"[{muted}]Sort:[/] {sort_human} {arrow}  ·  "
            f"[{muted}]1/2/3 or click header to sort[/]  ·  {self._linkding_badge()}"
        )

    @work(exclusive=True)
    async def load_bookmarks(self) -> None:
        reader = self.query_one("#reader", Reader)

        if not self.config.linkding.enabled:
            muted = self._color("$text-muted")
            accent = self._color("$accent")
            reader.update(
                f"[bold]linkding-share[/]\n\n"
                f"No Linkding instance configured.\n\n"
                f"[{accent}]Option 1 — environment variables (good for sharing):[/]\n\n"
                f"  [{muted}]export[/] LINKDING_URL[{muted}]=https://linkding.example.com[/]\n"
                f"  [{muted}]export[/] LINKDING_TOKEN[{muted}]=your_api_token[/]\n"
                f"  [{muted}]export[/] LINKDING_TAGS[{muted}]=cobuild[/]\n\n"
                f"[{accent}]Option 2 — config file:[/]\n\n"
                f"  Press [{accent}],[/] to open settings, or edit:\n"
                f"  [{muted}]{CONFIG_PATH}[/]\n\n"
                f"[{muted}]Get your API token from Linkding: Settings → Integrations[/]"
            )
            return

        reader.update("Loading bookmarks…")
        self._loading = True
        try:
            # Fetch tags first for validation
            all_tags, tag_err = await fetch_tags(self.config)
            if tag_err is None:
                self.all_tags = sorted(all_tags)
                self._validate_allowed_tags(all_tags)

            bookmarks, bm_err = await fetch_bookmarks(self.config)
        except Exception as e:
            reader.update(f"[red]Failed to load: {e}[/]")
            return
        finally:
            self._loading = False

        if bm_err:
            reader.update(f"[red]Error: {bm_err}[/]")
            self._flash_status(f"⚠ {bm_err}", seconds=8.0)
            return

        # Filter to bookmarks that have at least one allowed tag
        allowed_set = set(self.config.tags.allowed)
        if allowed_set:
            self.bookmarks = [b for b in bookmarks if any(t in allowed_set for t in b.tag_names)]
        else:
            self.bookmarks = bookmarks

        self.refresh_table()
        if self.visible_bookmarks:
            reader.update("Select a bookmark to read.")
        else:
            reader.update("No bookmarks matched the current filters.")

    def _validate_allowed_tags(self, all_tags: list[str]) -> None:
        tag_set = set(all_tags)
        for tag in self.config.tags.allowed:
            if tag not in tag_set:
                self._flash_status(
                    f"⚠ Tag {tag!r} not found in linkding — create it there first",
                    seconds=8.0,
                )

    @work(exclusive=True)
    async def _auto_load_bookmarks(self) -> None:
        if self._loading:
            return
        self._loading = True
        try:
            bookmarks, err = await fetch_bookmarks(self.config)
        except Exception:
            return
        finally:
            self._loading = False
        if err:
            return
        allowed_set = set(self.config.tags.allowed)
        if allowed_set:
            new_filtered = [b for b in bookmarks if any(t in allowed_set for t in b.tag_names)]
        else:
            new_filtered = bookmarks
        old_ids = {b.id for b in self.bookmarks}
        new_ids = {b.id for b in new_filtered}
        if old_ids == new_ids:
            return
        self.bookmarks = new_filtered
        self.refresh_table(preserve_cursor=True)

    def _restart_auto_refresh(self) -> None:
        if self._auto_refresh_timer is not None:
            try:
                self._auto_refresh_timer.stop()
            except Exception:
                pass
            self._auto_refresh_timer = None
        minutes = self.config.fetch.auto_refresh_minutes
        if minutes <= 0:
            return
        self._auto_refresh_timer = self.set_interval(minutes * 60, self._auto_load_bookmarks)

    def _sort_key(self, bm: Bookmark):
        from datetime import datetime, timezone
        far_past = datetime.min.replace(tzinfo=timezone.utc)
        if self.sort_column == "title":
            return (bm.display_title.lower(), -(bm.date_added or far_past).timestamp())
        if self.sort_column == "tags":
            return (",".join(sorted(bm.tag_names)).lower(), -(bm.date_added or far_past).timestamp())
        return (-(bm.date_added or far_past).timestamp(),)

    def refresh_table(self, preserve_cursor: bool = False) -> None:
        table = self.query_one("#bookmark-table", BookmarkList)
        saved_id = self.current_id if preserve_cursor else None
        table.clear()

        tag_filter = self.selected_tag
        rows: list[Bookmark] = []
        for bm in self.bookmarks:
            if tag_filter != ALL and tag_filter not in bm.tag_names:
                continue
            if self.view == "unread" and self.state.is_read(bm.local_id):
                continue
            if self.view == "read" and not self.state.is_read(bm.local_id):
                continue
            rows.append(bm)

        if self.search_query:
            q = self.search_query.lower()
            rows = [b for b in rows if q in b.display_title.lower() or any(q in t.lower() for t in b.tag_names)]

        rows.sort(key=self._sort_key)
        if self.sort_column == "when":
            if not self.sort_desc:
                rows.reverse()
        else:
            if self.sort_desc:
                rows.reverse()

        self.visible_bookmarks = rows
        tz = self.config.timezone
        muted = self._color("$text-muted")
        accent = self._color("$accent")
        primary = self._color("$primary")
        allowed_set = set(self.config.tags.allowed)

        for bm in rows:
            is_read = self.state.is_read(bm.local_id)
            if is_read:
                marker = Text(glyph("read"), style=muted)
            else:
                marker = Text(glyph("unread"), style=f"bold {accent}")

            title_style = muted if is_read else ""
            title_cell = Text(bm.display_title, style=title_style, no_wrap=True, overflow="ellipsis")

            # Tags: allowed tags in primary color, others muted
            tags_cell = Text()
            first = True
            for tag in bm.tag_names:
                if not first:
                    tags_cell.append(" ", style="")
                color = primary if tag in allowed_set else muted
                tags_cell.append(tag, style=color)
                first = False

            when_cell = Text(bm.date_added_short(tz), style=muted)
            table.add_row(marker, title_cell, tags_cell, when_cell, key=bm.local_id)

        if rows:
            target_row = 0
            if saved_id is not None:
                idx = next((i for i, b in enumerate(rows) if b.local_id == saved_id), None)
                if idx is not None:
                    target_row = idx
            table.move_cursor(row=target_row)

        self._update_column_labels()
        self._fit_title_column()
        self._update_status_bar()

    def _fit_title_column(self) -> None:
        try:
            table = self.query_one("#bookmark-table", BookmarkList)
        except Exception:
            return
        region_width = table.region.width or table.size.width
        if region_width <= 0:
            return
        fixed = 0
        title_col = None
        for key, col in table.columns.items():
            if key.value == "title":
                title_col = col
            else:
                fixed += col.width
        if title_col is None:
            return
        available = max(20, region_width - fixed - 12)
        title_col.width = available
        title_col.auto_width = False
        try:
            table._update_dimensions(table._new_rows)
        except Exception:
            table.refresh()

    def on_resize(self, event) -> None:
        self._fit_title_column()

    def _update_column_labels(self) -> None:
        table = self.query_one("#bookmark-table", BookmarkList)
        arrow = " " + (glyph("sort_desc") if self.sort_desc else glyph("sort_asc"))
        labels = {"marker": "", "title": "Title", "tags": "Tags", "when": "When"}
        if self.sort_column in labels and self.sort_column != "marker":
            labels[self.sort_column] = labels[self.sort_column] + arrow
        for key, label in labels.items():
            try:
                col = table.columns.get(key)
                if col is not None:
                    col.label = label
            except Exception:
                pass
        try:
            table.refresh()
        except Exception:
            pass

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "tag-select":
            self.selected_tag = str(event.value)
        elif event.select.id == "view-select":
            self.view = str(event.value)
        self.refresh_table()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self.search_query = event.value
            self.refresh_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            self.set_focus(self.query_one("#bookmark-table", BookmarkList))

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_key = event.column_key.value if event.column_key else None
        if col_key not in ("title", "tags", "when"):
            return
        if self.sort_column == col_key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_column = col_key
            self.sort_desc = col_key == "when"
        self._update_status_bar()
        self.refresh_table()

    def action_sort_by(self, col: str) -> None:
        if col not in ("title", "tags", "when"):
            return
        if self.sort_column == col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_column = col
            self.sort_desc = col == "when"
        self._update_status_bar()
        self.refresh_table()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None or event.row_key.value is None:
            return
        local_id = event.row_key.value
        if local_id == self.current_id:
            return
        bm = self._find(local_id)
        if bm is None:
            return
        self._cancel_mark_read_timer()
        self.current_id = local_id
        self.show_bookmark(bm)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None or event.row_key.value is None:
            return
        if self.view == "unread":
            return
        self._mark_read(event.row_key.value)

    def _mark_read(self, local_id: str) -> None:
        if self.state.is_read(local_id):
            return
        self.state.mark_read(local_id)
        table = self.query_one("#bookmark-table", BookmarkList)
        cursor_row = table.cursor_row
        self.refresh_table()
        if 0 <= cursor_row < len(self.visible_bookmarks):
            table.move_cursor(row=cursor_row)

    def _find(self, local_id: str) -> Bookmark | None:
        for b in self.bookmarks:
            if b.local_id == local_id:
                return b
        return None

    def show_bookmark(self, bm: Bookmark) -> None:
        reader = self.query_one("#reader", Reader)
        header = self._format_header(bm)
        cached = self.body_cache.get(bm.local_id)
        if cached is not None:
            reader.update(self._render_bookmark(bm, cached))
            self._schedule_auto_mark_read(bm.local_id)
        else:
            reader.update(
                f"{header}\n\n"
                f"{self._format_body_markup(bm.description or bm.website_description or '')}\n\n"
                f"[{self._color('$text-muted')} italic]loading full article…[/]"
            )
            self.load_body(bm)
        try:
            self._reader_pane().scroll_home(animate=False)
        except Exception:
            pass

    def _render_bookmark(self, bm: Bookmark, body: str) -> str:
        header = self._format_header(bm, body if body != BLOCKED_BODY else None)
        if body == BLOCKED_BODY:
            muted = self._color("$text-muted")
            warning = self._color("$warning")
            summary = bm.description or bm.website_description or "(no description)"
            return (
                f"{header}\n\n{self._format_body_markup(summary)}\n\n"
                f"[{warning}]Publisher blocked this fetch.[/] "
                f"[{muted}]Press [bold]o[/] to open in browser.[/]"
            )
        return f"{header}\n\n{self._format_body_markup(body)}"

    def _format_body_markup(self, body: str) -> str:
        from rich.markup import escape
        if not body:
            return ""
        paragraphs = body.split("\n\n")
        out: list[str] = []
        for i, p in enumerate(paragraphs):
            esc = escape(p)
            if i == 0 and re.match(r"^[A-Z][A-Z .,'']+(\([^)]+\))? *[-–—]", p):
                m = re.match(r"^([A-Z][A-Z .,'']+(?:\([^)]+\))?\s*[-–—])\s*(.*)$", p, re.DOTALL)
                if m:
                    out.append(f"[bold]{escape(m.group(1))}[/] {escape(m.group(2))}")
                    continue
            out.append(esc)
        return "\n\n".join(out)

    @work(exclusive=False)
    async def load_body(self, bm: Bookmark) -> None:
        body = await fetch_body(bm.url)
        self.body_cache[bm.local_id] = body
        if self.current_id == bm.local_id:
            reader = self.query_one("#reader", Reader)
            reader.update(self._render_bookmark(bm, body))
            if body != BLOCKED_BODY:
                self._schedule_auto_mark_read(bm.local_id)

    def _cancel_mark_read_timer(self) -> None:
        if self._mark_read_timer is not None:
            try:
                self._mark_read_timer.stop()
            except Exception:
                pass
            self._mark_read_timer = None

    def _schedule_auto_mark_read(self, local_id: str) -> None:
        self._cancel_mark_read_timer()
        if self.state.is_read(local_id):
            return
        if self.view == "unread":
            return
        delay = self.config.reader.mark_read_seconds
        if delay < 0:
            return
        if delay == 0:
            self._auto_mark_read(local_id)
            return
        self._mark_read_timer = self.set_timer(delay, lambda: self._auto_mark_read(local_id))

    def _auto_mark_read(self, local_id: str) -> None:
        self._mark_read_timer = None
        if self.current_id != local_id:
            return
        self._mark_read(local_id)

    def _format_header(self, bm: Bookmark, body: str | None = None) -> str:
        from rich.markup import escape
        muted = self._color("$text-muted")
        accent = self._color("$accent")
        primary = self._color("$primary")
        allowed_set = set(self.config.tags.allowed)

        title = escape(bm.display_title)
        read_time = ""
        if body and body != BLOCKED_BODY:
            word_count = len(body.split())
            mins = max(1, round(word_count / 200))
            read_time = f" · [italic]~{mins} min read[/]"

        # Tags line: allowed tags in primary, others muted
        tag_parts: list[str] = []
        for tag in bm.tag_names:
            color = primary if tag in allowed_set else muted
            tag_parts.append(f"[{color}]{escape(tag)}[/]")
        tags_line = f"[{muted}]Tags:[/] " + f"[{muted}] · [/]".join(tag_parts) if tag_parts else ""

        date_str = escape(bm.date_added_str(self.config.timezone))
        return (
            f"[bold]{title}[/]\n"
            f"{tags_line}\n"
            f"[{muted}]{glyph_prefix('clock')}{date_str}{read_time}[/]\n"
            f"[{muted} italic]{glyph_prefix('link')}[/][{accent}]{escape(bm.url)}[/]"
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self.body_cache.clear()
        self.config = load_config()
        self.sub_title = self._subtitle()
        self._update_tag_select()
        self._update_status_bar()
        self.load_bookmarks()
        self._restart_auto_refresh()

    def _update_tag_select(self) -> None:
        try:
            sel = self.query_one("#tag-select", Select)
            options = [(ALL, ALL)] + [(t, t) for t in self.config.tags.allowed]
            sel.set_options(options)
            default = self.config.tags.allowed[0] if self.config.tags.allowed else ALL
            sel.value = default
            self.selected_tag = default
        except Exception:
            pass

    def action_toggle_read(self) -> None:
        if self.current_id is None:
            return
        self._cancel_mark_read_timer()
        now_read = self.state.toggle_read(self.current_id)
        table = self.query_one("#bookmark-table", BookmarkList)
        cursor_row = table.cursor_row
        self.refresh_table()
        if 0 <= cursor_row < len(self.visible_bookmarks):
            table.move_cursor(row=cursor_row)
        self._flash_status("Marked read" if now_read else "Marked unread")

    def action_undo_read(self) -> None:
        result = self.state.undo_last_read()
        if result is None:
            self._flash_status("Nothing to undo")
            return
        local_id, is_now_read = result
        bm = self._find(local_id)
        label = bm.display_title if bm else local_id
        table = self.query_one("#bookmark-table", BookmarkList)
        cursor_row = table.cursor_row
        self.refresh_table()
        if 0 <= cursor_row < len(self.visible_bookmarks):
            table.move_cursor(row=cursor_row)
        self._flash_status(f"Undo: {label!r} marked {'read' if is_now_read else 'unread'}")

    def action_open_browser(self) -> None:
        if self.current_id is None:
            return
        bm = self._find(self.current_id)
        if bm is None:
            return
        webbrowser.open(bm.url)
        if self.view != "unread":
            self._mark_read(bm.local_id)

    def action_copy_url(self) -> None:
        if self.current_id is None:
            return
        bm = self._find(self.current_id)
        if bm is None:
            return
        self.copy_to_clipboard(bm.url)
        self._flash_status("Copied URL to clipboard")

    def action_add_bookmark(self) -> None:
        if not self.config.linkding.enabled:
            self._flash_status("Linkding not configured — set URL and API key in settings (,)")
            return
        if not self.config.tags.allowed:
            self._flash_status("No allowed tags configured — set LINKDING_TAGS or [tags].allowed")
            return
        from .add_modal import AddModal
        # Pre-select whichever tag is active in the filter; fall back to first allowed
        active_tag = self.selected_tag if self.selected_tag != ALL else self.config.tags.allowed[0]
        self.push_screen(AddModal(self.config, default_tag=active_tag), self._on_add_result)

    def _on_add_result(self, result: tuple[str, str, str, list[str]] | None) -> None:
        if result is None:
            return
        url, title, description, tag_names = result
        self._do_create_bookmark(url, title, description, tag_names)

    @work(exclusive=False)
    async def _do_create_bookmark(self, url: str, title: str, description: str, tag_names: list[str]) -> None:
        self._flash_status("Saving bookmark…", seconds=10.0)
        ok, msg, new_bm = await create_bookmark(self.config, url, title, description, tag_names)
        if ok and new_bm is not None:
            allowed_set = set(self.config.tags.allowed)
            if any(t in allowed_set for t in new_bm.tag_names):
                self.bookmarks.insert(0, new_bm)
                self.refresh_table()
        self._flash_status(f"{'✓' if ok else '✗'} {msg}")

    def action_edit_bookmark(self) -> None:
        if self.current_id is None:
            self._flash_status("No bookmark selected")
            return
        bm = self._find(self.current_id)
        if bm is None:
            return
        if not self.config.linkding.enabled:
            self._flash_status("Linkding not configured")
            return
        from .edit_modal import EditModal
        self.push_screen(EditModal(self.config, bm), self._on_edit_result)

    def _on_edit_result(self, result: tuple[str, str, list[str]] | None) -> None:
        if result is None or self.current_id is None:
            return
        bm = self._find(self.current_id)
        if bm is None:
            return
        title, description, tag_names = result
        self._do_update_bookmark(bm, title, description, tag_names)

    @work(exclusive=False)
    async def _do_update_bookmark(self, bm: Bookmark, title: str, description: str, tag_names: list[str]) -> None:
        self._flash_status("Updating bookmark…", seconds=10.0)
        ok, msg, updated = await update_bookmark(self.config, bm.id, title, description, tag_names)
        if ok and updated is not None:
            # Replace in local list
            for i, b in enumerate(self.bookmarks):
                if b.id == updated.id:
                    self.bookmarks[i] = updated
                    break
            # Clear cached body since metadata changed
            self.body_cache.pop(bm.local_id, None)
            self.refresh_table(preserve_cursor=True)
            # Re-show with updated data if still selected
            if self.current_id == bm.local_id or self.current_id == updated.local_id:
                self.current_id = updated.local_id
                self.show_bookmark(updated)
        self._flash_status(f"{'✓' if ok else '✗'} {msg}")

    def action_delete_bookmark(self) -> None:
        if self.current_id is None:
            self._flash_status("No bookmark selected")
            return
        bm = self._find(self.current_id)
        if bm is None:
            return
        if not self.config.linkding.enabled:
            self._flash_status("Linkding not configured")
            return
        from .confirm_modal import ConfirmModal
        title_preview = bm.display_title[:60] + ("…" if len(bm.display_title) > 60 else "")
        self.push_screen(
            ConfirmModal(f"Delete bookmark?\n\n{title_preview}\n\nThis cannot be undone."),
            lambda confirmed: self._on_delete_confirmed(confirmed, bm),
        )

    def _on_delete_confirmed(self, confirmed: bool, bm: Bookmark) -> None:
        if not confirmed:
            return
        self._do_delete_bookmark(bm)

    @work(exclusive=False)
    async def _do_delete_bookmark(self, bm: Bookmark) -> None:
        self._flash_status("Deleting…", seconds=10.0)
        ok, msg = await delete_bookmark(self.config, bm.id)
        if ok:
            self.bookmarks = [b for b in self.bookmarks if b.id != bm.id]
            self.body_cache.pop(bm.local_id, None)
            if self.current_id == bm.local_id:
                self.current_id = None
                self.query_one("#reader", Reader).update("Bookmark deleted.")
            self.refresh_table()
        self._flash_status(f"{'✓' if ok else '✗'} {msg}")

    def action_cycle_read_filter(self) -> None:
        order = ["all", "unread", "read"]
        current = self.view if self.view in order else "all"
        self._set_view(order[(order.index(current) + 1) % len(order)])

    def _set_view(self, view: str) -> None:
        self.view = view
        try:
            sel = self.query_one("#view-select", Select)
            if str(sel.value) != view:
                sel.value = view
        except Exception:
            pass
        labels = {"all": "All bookmarks", "unread": "Unread only", "read": "Read only"}
        self._flash_status(labels.get(view, view))
        self.refresh_table()

    def action_open_help(self) -> None:
        from .help_screen import HelpScreen
        self.push_screen(HelpScreen())

    def action_open_search(self) -> None:
        search_input = self.query_one("#search-input", Input)
        search_input.add_class("visible")
        self.set_focus(search_input)

    def action_close_search(self) -> None:
        search_input = self.query_one("#search-input", Input)
        search_input.remove_class("visible")
        search_input.value = ""
        self.search_query = ""
        self.refresh_table()
        self.set_focus(self.query_one("#bookmark-table", BookmarkList))

    def action_close_search_or_nothing(self) -> None:
        try:
            search_input = self.query_one("#search-input", Input)
            if search_input.has_class("visible"):
                self.action_close_search()
        except Exception:
            pass

    def action_open_settings(self) -> None:
        from .settings_screen import SettingsScreen
        self.push_screen(
            SettingsScreen(
                self.config,
                on_save=self._apply_config,
                all_tags=self.all_tags,
                available_themes=list(self.available_themes),
            )
        )

    def _apply_config(self, new_cfg: Config) -> None:
        old = self.config
        self.config = new_cfg
        col_map = {"time": "when", "title": "title", "tags": "tags"}
        self.sort_column = col_map.get(new_cfg.sort.column, "when")
        self.sort_desc = new_cfg.sort.direction == "desc"
        if new_cfg.theme != old.theme:
            self._apply_theme(new_cfg.theme)
        if new_cfg.ui.nerd_font != old.ui.nerd_font:
            self._apply_glyph_mode()
        if new_cfg.ui.default_view != old.ui.default_view:
            self._set_view(new_cfg.ui.default_view)
        self.sub_title = self._subtitle()
        self._update_tag_select()
        self._update_status_bar()
        tags_changed = set(old.tags.allowed) != set(new_cfg.tags.allowed)
        if tags_changed or old.linkding.url != new_cfg.linkding.url or old.linkding.api_key != new_cfg.linkding.api_key:
            self.body_cache.clear()
            self.load_bookmarks()
        else:
            self.refresh_table()
        if old.fetch.auto_refresh_minutes != new_cfg.fetch.auto_refresh_minutes:
            self._restart_auto_refresh()
        self._flash_status("Settings saved")

    def _reader_pane(self) -> VerticalScroll:
        return self.query_one("#reader-pane", VerticalScroll)

    def action_scroll_reader_up(self) -> None:
        self._reader_pane().scroll_relative(y=-10, animate=False)

    def action_scroll_reader_down(self) -> None:
        self._reader_pane().scroll_relative(y=10, animate=False)

    def action_scroll_reader_page_up(self) -> None:
        self._reader_pane().scroll_page_up(animate=False)

    def action_scroll_reader_page_down(self) -> None:
        self._reader_pane().scroll_page_down(animate=False)

    def action_scroll_reader_home(self) -> None:
        self._reader_pane().scroll_home(animate=False)

    def action_scroll_reader_end(self) -> None:
        self._reader_pane().scroll_end(animate=False)

    def action_focus_reader(self) -> None:
        self.set_focus(self._reader_pane())

    def action_focus_list(self) -> None:
        self.set_focus(self.query_one("#bookmark-table", BookmarkList))


def main() -> None:
    parser = argparse.ArgumentParser(prog="linkding-share", description="TUI for sharing linkding bookmarks.")
    parser.add_argument("--show-config", action="store_true", help="Print config path and exit.")
    parser.add_argument("--print-default-config", action="store_true", help="Print default config TOML and exit.")
    args = parser.parse_args()

    if args.print_default_config:
        from .config import DEFAULT_CONFIG_TEXT
        sys.stdout.write(DEFAULT_CONFIG_TEXT)
        return

    cfg = load_config()
    status = "created" if cfg.just_created else "loaded"
    print(f"linkding-share · config {status}: {CONFIG_PATH}", file=sys.stderr)
    if cfg.load_errors:
        for err in cfg.load_errors:
            print(f"  warning: {err}", file=sys.stderr)

    if args.show_config:
        return

    LinkdingShareApp(preloaded_config=cfg).run()


if __name__ == "__main__":
    main()
