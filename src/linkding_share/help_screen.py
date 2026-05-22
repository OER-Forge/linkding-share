from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


class HelpScreen(ModalScreen):
    CSS = """
    HelpScreen { layout: vertical; align: center middle; }
    #help-container {
        width: 100;
        height: auto;
        border: solid $accent;
        background: $surface;
    }
    #help-text { padding: 1 2; }
    """

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close"),
        Binding("q", "dismiss_help", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        help_text = """[bold cyan]linkding-share keyboard shortcuts[/]

[bold]Navigation:[/]
  ↑/↓       Move cursor up/down
  j/k       Move cursor (vim-style)
  Tab       Switch focus: list ↔ reader pane
  Shift+Tab Switch focus pane ↔ list (reverse)

[bold]Reading:[/]
  Space     Page down in reader
  b         Page up in reader
  PgDn/PgUp Page down/up (same as Space/b)
  Ctrl+D    Half-page scroll down
  Ctrl+U    Half-page scroll up
  g         Jump to top
  G         Jump to bottom

[bold]Sorting:[/]
  1         Sort by Title
  2         Sort by Tags
  3         Sort by Time
  (Click column headers to sort)

[bold]Filtering:[/]
  u         Cycle View: All → Unread → Read
  /         Search by title/tags
  Escape    Close search

[bold]Bookmarks:[/]
  a         Add new bookmark (scrapes title from URL)
  e         Edit current bookmark (title, description, tags)
  d         Delete current bookmark (with confirmation)
  x         Toggle read/unread
  z         Undo last read toggle
  o         Open URL in browser
  c         Copy URL to clipboard

[bold]App:[/]
  ,         Settings
  r         Refresh from linkding
  ?         Show this help
  q         Quit
"""
        with VerticalScroll(id="help-container"):
            yield Static(help_text, id="help-text", markup=True)

    def action_dismiss_help(self) -> None:
        self.dismiss()
