"""Modal for editing an existing bookmark's metadata."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static

from .config import Config
from .models import Bookmark


class EditModal(ModalScreen[tuple[str, str, list[str]] | None]):
    """Returns (title, description, full_tag_names) or None on cancel.

    full_tag_names preserves tags outside the allowed set and replaces the
    allowed-tag subset with whatever the user selected.
    """

    CSS = """
    EditModal { align: center middle; }
    #edit-dialog {
        width: 84;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #edit-dialog-title { text-style: bold; color: $text; padding-bottom: 1; }
    .field-row { height: 3; padding: 0 0 1 0; }
    .field-label { width: 16; padding: 1 1 0 0; color: $text; text-style: bold; }
    .field-input { width: 1fr; }
    .tags-label { text-style: bold; color: $text; padding-bottom: 0; }
    .tag-cb { height: auto; min-height: 1; }
    #other-tags { color: $text-muted; height: 1; padding: 0 0 1 0; }
    #edit-error { color: $error; height: 1; padding-top: 1; }
    #edit-buttons { height: 3; align: right middle; padding-top: 1; }
    #edit-buttons Button { margin-left: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, config: Config, bookmark: Bookmark) -> None:
        super().__init__()
        self._config = config
        self._bookmark = bookmark
        self._other_tags = [t for t in bookmark.tag_names if t not in config.tags.allowed]

    def compose(self) -> ComposeResult:
        bm = self._bookmark
        with Vertical(id="edit-dialog"):
            yield Static(
                "Edit Bookmark  ·  Ctrl+S save  ·  Esc cancel",
                id="edit-dialog-title",
            )
            with Horizontal(classes="field-row"):
                yield Label("Title", classes="field-label")
                yield Input(value=bm.title, id="title-input", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Label("Description", classes="field-label")
                yield Input(value=bm.description, id="desc-input", classes="field-input")
            yield Label("Tags", classes="tags-label")
            for i, tag in enumerate(self._config.tags.allowed):
                checked = tag in bm.tag_names
                yield Checkbox(tag, value=checked, id=f"tag-idx-{i}", classes="tag-cb")
            if self._other_tags:
                yield Static(
                    f"Other tags (preserved): {', '.join(self._other_tags)}",
                    id="other-tags",
                )
            yield Static("", id="edit-error")
            with Horizontal(id="edit-buttons"):
                yield Button("Cancel", id="btn-cancel", variant="default")
                yield Button("Save", id="btn-save", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self.action_save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        title = self.query_one("#title-input", Input).value.strip()
        desc = self.query_one("#desc-input", Input).value.strip()
        selected_allowed = [
            self._config.tags.allowed[i]
            for i in range(len(self._config.tags.allowed))
            if self.query_one(f"#tag-idx-{i}", Checkbox).value
        ]
        # Preserve tags outside the allowed set, merge with new selection
        full_tags = self._other_tags + selected_allowed
        if not full_tags:
            self.query_one("#edit-error", Static).update("Select at least one tag")
            return
        self.dismiss((title, desc, full_tags))
