# linkding-share

A terminal TUI for browsing, adding, editing, and deleting bookmarks on a shared [Linkding](https://linkding.link/) instance. Built with [Textual](https://textual.textualize.io/).

Two-pane layout: a sortable bookmark list on the left, the full article body on the right. Fetches bookmarks from a Linkding instance filtered by a configurable set of tags, scrapes and renders article bodies in-terminal via [trafilatura](https://trafilatura.readthedocs.io/), and tracks read/unread state locally. Designed for two people sharing a Linkding account with a shared API token and a shared tag convention — a lightweight way to co-curate a set of links without any extra infrastructure.

## Features

- **Tag-scoped view** — configure one or more allowed tags (via config or `LINKDING_TAGS` env var); the tool only shows bookmarks that carry at least one of them. Tags must already exist in Linkding; the tool validates them on startup and will not create new ones.
- **Two-pane TUI** with click-to-sort columns (Title / Tags / Time), a View filter (All / Unread / Read), a tag filter dropdown, and a live search bar.
- **Readable article body** fetched and extracted in-terminal via [trafilatura](https://trafilatura.readthedocs.io/). Falls back to the stored description on publisher blocks.
- **Add bookmarks** (`a`) — paste a URL, the tool scrapes the title and description automatically; pick tags from the allowed set and save.
- **Edit bookmarks** (`e`) — update title, description, and tags on any bookmark. Tags outside the allowed set are preserved; only the allowed-tag subset is editable.
- **Delete bookmarks** (`d`) — with a confirmation modal before the API call.
- **Read & unread tracking** persisted locally across sessions. The View dropdown and `u` shortcut toggle between All / Unread / Read. The Unread view is safe: nothing auto-removes a bookmark from it — only an explicit `x` marks it read there.
- **Auto mark-as-read** after a configurable delay once the article body finishes loading. Configurable delay; set to `-1` to disable.
- **In-app settings menu** (`,`) — edit every config field live, including which tags are accessible, without a restart.
- **Color themes**: 21 Textual built-ins (`gruvbox`, `nord`, `dracula`, `tokyo-night`, `catppuccin-mocha`, `solarized-dark`, …) plus 4 bundled palettes (`newsprint`, `broadsheet`, `wire-service`, `teletype`). Drop your own into `~/.config/linkding-share/themes.toml`.
- **Nerd Font glyphs**: auto-detected; falls back to ASCII. Force on/off in settings.
- **Alacritty font integration**: if you use Alacritty, the settings menu can set your terminal font and live-reload it without a restart.
- **Copy & open shortcuts**: `c` copies the URL to the clipboard (OSC 52, works over SSH); `o` opens in the browser.

## Install

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

### Install as a binary (recommended)

```sh
git clone <this repo> linkding-share
cd linkding-share
uv tool install .
```

This drops a `linkding-share` binary on your `PATH` via `~/.local/bin`. Run `uv tool update-shell` if that directory isn't on your `PATH` yet.

```sh
linkding-share
```

To upgrade after pulling new commits:

```sh
git pull
uv tool install --reinstall .
```

To uninstall: `uv tool uninstall linkding-share`.

### Run from a clone (dev workflow)

```sh
git clone <this repo> linkding-share
cd linkding-share
uv sync
uv run linkding-share
```

### First launch

On first launch the app creates `~/.config/linkding-share/config.toml` with defaults. You need to configure your Linkding URL, API token, and at least one allowed tag before the tool will load anything.

```sh
linkding-share --show-config          # print config path and exit
linkding-share --print-default-config # dump the default TOML
```

## Configuration

The fastest way to get started is with environment variables:

```sh
export LINKDING_URL=https://linkding.example.com
export LINKDING_TOKEN=your_api_token_here
export LINKDING_TAGS=cobuild,research
linkding-share
```

Or edit `~/.config/linkding-share/config.toml` directly and press `r` in the app to reload:

```toml
# Display timezone for the "When" column. Storage stays UTC.
timezone = "America/New_York"

# Color theme. Built-in Textual themes plus bundled custom ones.
# Add your own to ~/.config/linkding-share/themes.toml.
theme = "textual-dark"

# Linkding instance credentials.
# Override with LINKDING_URL and LINKDING_TOKEN environment variables.
[linkding]
url = ""       # e.g. "https://linkding.example.com"
api_key = ""   # REST API token from Settings > Integrations

# Tags this tool can read and write.
# Must already exist in your Linkding instance — this tool cannot create tags.
# Override with LINKDING_TAGS env var (comma-separated: "cobuild,research").
[tags]
allowed = ["cobuild", "research"]

[sort]
column = "time"    # "title" | "tags" | "time"
direction = "desc"

# mark_read_seconds: delay after body loads before auto-marking read.
#   0 = immediate, negative = disabled. The Unread view always requires
#   an explicit `x` — nothing auto-removes a bookmark from it.
# read_retention_days: prune read history after this many days. 0 = keep forever.
[reader]
mark_read_seconds = 5
read_retention_days = 90

# auto_refresh_minutes: 0 disables background refresh.
[fetch]
auto_refresh_minutes = 0

[ui]
nerd_font = "auto"      # "auto" | "on" | "off"
default_view = "all"    # "all" | "unread" | "read"
```

### Environment variable priority

`LINKDING_URL`, `LINKDING_TOKEN`, and `LINKDING_TAGS` always take priority over the values in `config.toml`. Useful for running two instances against different Linkding accounts without touching the config file.

### Tag rules

- Tags in `[tags].allowed` (or `LINKDING_TAGS`) must exist in your Linkding instance before the tool starts. The tool validates them on startup and warns about any that are missing.
- **The tool cannot create tags.** Create them in the Linkding web UI first.
- When editing a bookmark, only the allowed tags are shown as checkboxes. Any tags the bookmark already has that fall outside the allowed set are preserved as-is and shown as read-only.
- Bookmarks are visible in this tool if they carry **at least one** allowed tag, even if they also have other tags.

## Keys

| Key | Action |
|---|---|
| `↑` / `↓` / `j` / `k` | Move cursor |
| `Enter` | Mark read & focus reader (no-op for marking in the Unread view) |
| `Tab` / `Shift+Tab` | Switch focus: list ↔ reader pane |
| `Space` / `b` | Page down / up in reader |
| `PgDn` / `PgUp` | Same |
| `Ctrl+D` / `Ctrl+U` | Half-page scroll |
| `g` / `G` | Jump to top / bottom |
| `1` / `2` / `3` | Sort by Title / Tags / Time |
| `a` | Add a new bookmark (scrapes title from URL) |
| `e` | Edit current bookmark (title, description, tags) |
| `d` | Delete current bookmark (with confirmation) |
| `x` | Toggle read / unread |
| `z` | Undo last read toggle |
| `o` | Open URL in browser (also marks read, except in Unread view) |
| `c` | Copy URL to clipboard |
| `u` | Cycle View: All → Unread → Read → All |
| `/` | Search by title or tag |
| `Escape` | Close search |
| `,` | Open settings |
| `r` | Refresh from Linkding & reload config |
| `?` | Show help |
| `q` | Quit |

Click any column header to sort by that column; click again to flip direction.

### Add bookmark (`a`)

1. Press `a` — an **Add Bookmark** modal opens.
2. Type or paste a URL and press `Enter` — the tool fetches the page and auto-fills the title and description via trafilatura (a status line shows progress).
3. Optionally edit the title and description.
4. Check one or more tags from the allowed set.
5. `Ctrl+S` or the **Save** button POSTs to Linkding and adds the bookmark to the list.

### Edit bookmark (`e`)

Opens the selected bookmark pre-filled with its current title, description, and tags. Only allowed tags are shown as checkboxes. Tags outside the allowed set are listed as read-only and will be preserved in the PATCH request. `Ctrl+S` saves.

### Settings menu (`,`)

A full-screen modal. **Ctrl+S** saves and applies live; **Esc** cancels.

| Section | Fields |
|---|---|
| **Appearance** | Theme, Nerd Font glyphs, Default view |
| **Alacritty font** *(shown only if `~/.config/alacritty/alacritty.toml` exists)* | Font family (dropdown of installed Nerd Fonts) and size; live-reloads on save |
| **Linkding** | URL and API key |
| **Tags** | Checkboxes for every tag that exists in your Linkding instance; ON = accessible in this tool |
| **Default sort** | Column and direction |
| **Fetch** | Auto-refresh interval |
| **Reader** | Mark-read delay, read-history retention |
| **Timezone** | Preset dropdown + custom IANA text field |

## Sharing model

Both users point their local `config.toml` (or env vars) at the same Linkding instance with the same API token. Neither token nor config is shared as a file — each person keeps their credentials locally.

The shared tag (e.g. `cobuild`) is the only coordination mechanism. Any bookmark either person adds with that tag becomes visible to the other on next refresh (`r` or auto-refresh).

```
Person A                          Person B
~/.config/linkding-share/         ~/.config/linkding-share/
  config.toml                       config.toml
    LINKDING_URL = same ──────────────── LINKDING_URL = same
    LINKDING_TOKEN = same ───────────── LINKDING_TOKEN = same
    [tags].allowed = ["cobuild"]        [tags].allowed = ["cobuild"]
```

Read/unread tracking is **local to each person** — it lives in a `state.json` on each machine and is never synced.

## Storage

- **Config**: `~/.config/linkding-share/config.toml`
- **Read state**: `~/Library/Application Support/linkding-share/state.json` on macOS, `~/.local/share/linkding-share/state.json` on Linux.

The state file only stores which bookmark URLs have been read (as SHA-1 hashes) and when. It never leaves your machine.

## Custom themes

Create `~/.config/linkding-share/themes.toml`:

```toml
[[theme]]
name = "my-theme"
dark = true
primary = "#7aa2f7"
accent = "#f7768e"
background = "#1a1b26"
surface = "#24283b"
foreground = "#c0caf5"
# Optional: secondary, warning, error, success, panel
```

The theme appears in the settings picker immediately. The bundled palettes are in `src/linkding_share/themes.toml`.

## Caveats

- Some publishers block programmatic fetches (401/403). When that happens the reader pane shows the stored Linkding description with a "press `o` to open in browser" hint.
- Tag validation runs on every startup. If a tag in `[tags].allowed` doesn't exist in Linkding yet, the app warns but still starts — it just won't find any bookmarks with that tag until you create it.
- Deleting a bookmark in this tool calls the Linkding API and removes it from the instance for both users. There is no undo.
- Read/unread state is local to each machine. The other person's read state is not visible and not synced.
