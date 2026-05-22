"""Modal for adding a new bookmark with URL scraping."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static

from .config import Config


class AddModal(ModalScreen[tuple[str, str, str, list[str]] | None]):
    """Returns (url, title, description, tag_names) or None on cancel."""

    CSS = """
    AddModal { align: center middle; }
    #add-dialog {
        width: 84;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #add-dialog-title { text-style: bold; color: $text; padding-bottom: 1; }
    .field-row { height: 3; padding: 0 0 1 0; }
    .field-label { width: 16; padding: 1 1 0 0; color: $text; text-style: bold; }
    .field-input { width: 1fr; }
    #scrape-status { color: $text-muted; height: 1; padding-bottom: 1; }
    .tags-label { text-style: bold; color: $text; padding-bottom: 0; }
    .tag-cb { height: auto; min-height: 1; }
    #add-error { color: $error; height: 1; padding-top: 1; }
    #add-buttons { height: 3; align: right middle; padding-top: 1; }
    #add-buttons Button { margin-left: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, config: Config, default_tag: str | None = None) -> None:
        super().__init__()
        self._config = config
        self._default_tag = default_tag

    def compose(self) -> ComposeResult:
        with Vertical(id="add-dialog"):
            yield Static(
                "Add Bookmark  ·  Enter in URL field to scrape title  ·  Ctrl+S save  ·  Esc cancel",
                id="add-dialog-title",
            )
            with Horizontal(classes="field-row"):
                yield Label("URL", classes="field-label")
                yield Input(placeholder="https://…", id="url-input", classes="field-input")
            yield Static("", id="scrape-status")
            with Horizontal(classes="field-row"):
                yield Label("Title", classes="field-label")
                yield Input(placeholder="Auto-filled from URL", id="title-input", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("Description", classes="field-label")
                yield Input(placeholder="Optional", id="desc-input", classes="field-input")
            yield Label("Tags", classes="tags-label")
            for i, tag in enumerate(self._config.tags.allowed):
                pre_checked = tag == self._default_tag
                yield Checkbox(tag, value=pre_checked, id=f"tag-idx-{i}", classes="tag-cb")
            yield Static("", id="add-error")
            with Horizontal(id="add-buttons"):
                yield Button("Cancel", id="btn-cancel", variant="default")
                yield Button("Save", id="btn-save", variant="primary")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "url-input":
            url = event.value.strip()
            if url:
                self._do_scrape(url)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self.action_save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        url = self.query_one("#url-input", Input).value.strip()
        if not url:
            self._set_error("URL is required")
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            self._set_error("URL must start with http:// or https://")
            return
        title = self.query_one("#title-input", Input).value.strip()
        desc = self.query_one("#desc-input", Input).value.strip()
        tags = [
            self._config.tags.allowed[i]
            for i in range(len(self._config.tags.allowed))
            if self.query_one(f"#tag-idx-{i}", Checkbox).value
        ]
        if not tags:
            self._set_error("Select at least one tag")
            return
        self.dismiss((url, title, desc, tags))

    def _set_error(self, msg: str) -> None:
        self.query_one("#add-error", Static).update(msg)

    @work(exclusive=True)
    async def _do_scrape(self, url: str) -> None:
        from .fetch import scrape_title
        status = self.query_one("#scrape-status", Static)
        status.update("[italic]Scraping…[/]")
        try:
            title, description = await scrape_title(url)
        except Exception:
            status.update("[dim]Could not scrape title — fill in manually[/]")
            return
        title_input = self.query_one("#title-input", Input)
        desc_input = self.query_one("#desc-input", Input)
        if title and not title_input.value:
            title_input.value = title
        if description and not desc_input.value:
            desc_input.value = description
        if title:
            status.update("[dim]Title scraped from URL[/]")
        else:
            status.update("[dim]Could not extract title — fill in manually[/]")
