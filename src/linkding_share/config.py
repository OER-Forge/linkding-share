import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_CONFIG_BASE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
CONFIG_DIR = _CONFIG_BASE / "linkding-share"
CONFIG_PATH = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG_TEXT = """\
# linkding-share configuration. Restart the app after editing.

# Display timezone for the "When" column. Storage stays UTC.
# Examples: "America/New_York", "America/Los_Angeles", "UTC", "Europe/London".
timezone = "America/New_York"

# Color theme. Built-in Textual themes plus bundled ones in themes.toml.
#   "textual-dark", "textual-light", "gruvbox", "nord", "dracula",
#   "tokyo-night", "monokai", "catppuccin-mocha", "solarized-dark",
#   "newsprint" (light), "broadsheet", "wire-service", "teletype".
# Add your own to ~/.config/linkding-share/themes.toml.
theme = "textual-dark"

# Linkding instance credentials.
# Override with LINKDING_URL and LINKDING_TOKEN environment variables.
[linkding]
url = ""       # e.g. "https://linkding.example.com"
api_key = ""   # REST API token from Settings > Integrations

# Tags this tool can read and write.
# Must already exist in your linkding instance — this tool cannot create tags.
# Override with LINKDING_TAGS env var (comma-separated: "cobuild,research").
[tags]
allowed = []

[sort]
column = "time"   # "title", "tags", "time"
direction = "desc"

# Reader behavior.
# mark_read_seconds: seconds before auto-marking read. 0 = immediate. -1 = off.
# read_retention_days: drop read history after N days. 0 = keep forever.
[reader]
mark_read_seconds = 5
read_retention_days = 90

# auto_refresh_minutes: 0 disables; minimum 1 when enabled.
[fetch]
auto_refresh_minutes = 0

[ui]
nerd_font = "auto"      # "auto", "on", "off"
default_view = "all"    # "all", "unread", "read"
"""


@dataclass
class LinkdingConfig:
    url: str = ""
    api_key: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.api_key)


@dataclass
class TagsConfig:
    allowed: list[str] = field(default_factory=list)


@dataclass
class SortConfig:
    column: str = "time"
    direction: str = "desc"


@dataclass
class ReaderConfig:
    mark_read_seconds: float = 5.0
    read_retention_days: int = 90


@dataclass
class FetchConfig:
    auto_refresh_minutes: int = 0


@dataclass
class UIConfig:
    nerd_font: str = "auto"
    default_view: str = "all"


@dataclass
class Config:
    linkding: LinkdingConfig = field(default_factory=LinkdingConfig)
    tags: TagsConfig = field(default_factory=TagsConfig)
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("UTC"))
    sort: SortConfig = field(default_factory=SortConfig)
    reader: ReaderConfig = field(default_factory=ReaderConfig)
    fetch: FetchConfig = field(default_factory=FetchConfig)
    theme: str = "textual-dark"
    ui: UIConfig = field(default_factory=UIConfig)
    load_errors: list[str] = field(default_factory=list)
    just_created: bool = False


def _ensure_config_file() -> bool:
    if CONFIG_PATH.exists():
        return False
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(DEFAULT_CONFIG_TEXT)
        return True
    except OSError:
        return False


def load_config() -> Config:
    created = _ensure_config_file()
    cfg = Config(just_created=created)

    data: dict = {}
    if CONFIG_PATH.exists():
        try:
            data = tomllib.loads(CONFIG_PATH.read_text())
        except (OSError, tomllib.TOMLDecodeError) as e:
            cfg.load_errors.append(f"config parse error: {e}")

    tz_name = data.get("timezone", "America/New_York")
    try:
        cfg.timezone = ZoneInfo(str(tz_name))
    except ZoneInfoNotFoundError:
        cfg.load_errors.append(f"unknown timezone {tz_name!r}, falling back to UTC")
        cfg.timezone = ZoneInfo("UTC")

    # [linkding] — env vars take priority
    ld = data.get("linkding", {})
    if not isinstance(ld, dict):
        cfg.load_errors.append("[linkding] must be a table; using defaults")
        ld = {}
    ld_url = str(ld.get("url", "") or "").rstrip("/")
    ld_key = str(ld.get("api_key", "") or "")
    ld_url = os.environ.get("LINKDING_URL", ld_url).rstrip("/")
    ld_key = os.environ.get("LINKDING_TOKEN", ld_key)
    if ld_url and not (ld_url.startswith("http://") or ld_url.startswith("https://")):
        cfg.load_errors.append(f"linkding.url {ld_url!r} must start with http:// or https://")
    cfg.linkding = LinkdingConfig(url=ld_url, api_key=ld_key)

    # [tags] — LINKDING_TAGS env var takes priority
    tags_tbl = data.get("tags", {})
    if not isinstance(tags_tbl, dict):
        cfg.load_errors.append("[tags] must be a table; using defaults")
        tags_tbl = {}
    env_tags = os.environ.get("LINKDING_TAGS")
    if env_tags:
        allowed = [t.strip() for t in env_tags.split(",") if t.strip()]
    else:
        raw = tags_tbl.get("allowed", [])
        if not isinstance(raw, list):
            cfg.load_errors.append("[tags].allowed must be a list; using []")
            raw = []
        allowed = [str(t) for t in raw if isinstance(t, str) and t.strip()]
    if not allowed and not created:
        cfg.load_errors.append(
            "No allowed tags configured. Set [tags].allowed in config or LINKDING_TAGS env var."
        )
    cfg.tags = TagsConfig(allowed=allowed)

    sort_tbl = data.get("sort", {})
    if not isinstance(sort_tbl, dict):
        sort_tbl = {}
    col = sort_tbl.get("column", "time")
    direction = sort_tbl.get("direction", "desc")
    if col not in ("title", "tags", "time"):
        cfg.load_errors.append(f"invalid sort.column {col!r}; using 'time'")
        col = "time"
    if direction not in ("asc", "desc"):
        cfg.load_errors.append(f"invalid sort.direction {direction!r}; using 'desc'")
        direction = "desc"
    cfg.sort = SortConfig(column=str(col), direction=str(direction))

    reader_tbl = data.get("reader", {})
    if not isinstance(reader_tbl, dict):
        reader_tbl = {}
    try:
        mrs = float(reader_tbl.get("mark_read_seconds", 5))
    except (TypeError, ValueError):
        cfg.load_errors.append("invalid reader.mark_read_seconds; auto-mark disabled")
        mrs = -1.0
    try:
        retention = max(0, int(reader_tbl.get("read_retention_days", 90)))
    except (TypeError, ValueError):
        cfg.load_errors.append("invalid reader.read_retention_days; pruning disabled")
        retention = 0
    cfg.reader = ReaderConfig(mark_read_seconds=mrs, read_retention_days=retention)

    fetch_tbl = data.get("fetch", {})
    if not isinstance(fetch_tbl, dict):
        fetch_tbl = {}
    try:
        auto_min = max(0, int(fetch_tbl.get("auto_refresh_minutes", 0)))
    except (TypeError, ValueError):
        auto_min = 0
    cfg.fetch = FetchConfig(auto_refresh_minutes=auto_min)

    theme_val = data.get("theme")
    if isinstance(theme_val, str) and theme_val:
        cfg.theme = theme_val

    ui_tbl = data.get("ui", {})
    if not isinstance(ui_tbl, dict):
        ui_tbl = {}
    nerd = ui_tbl.get("nerd_font", "auto")
    if nerd not in ("auto", "on", "off"):
        cfg.load_errors.append(f"invalid ui.nerd_font {nerd!r}; using 'auto'")
        nerd = "auto"
    view = ui_tbl.get("default_view", "all")
    if view not in ("all", "unread", "read"):
        cfg.load_errors.append(f"invalid ui.default_view {view!r}; using 'all'")
        view = "all"
    cfg.ui = UIConfig(nerd_font=str(nerd), default_view=str(view))

    return cfg


def _toml_str(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_str_list(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(_toml_str(x) for x in items) + "]"


def render_config(cfg: Config) -> str:
    tz_name = str(getattr(cfg.timezone, "key", cfg.timezone))
    mrs = cfg.reader.mark_read_seconds
    mrs_str = str(int(mrs)) if float(mrs).is_integer() else repr(mrs)
    return f"""# linkding-share configuration. Restart the app after editing.

timezone = {_toml_str(tz_name)}
theme = {_toml_str(cfg.theme)}

[linkding]
url = {_toml_str(cfg.linkding.url)}
api_key = {_toml_str(cfg.linkding.api_key)}

[tags]
allowed = {_toml_str_list(cfg.tags.allowed)}

[sort]
column = {_toml_str(cfg.sort.column)}
direction = {_toml_str(cfg.sort.direction)}

[reader]
mark_read_seconds = {mrs_str}
read_retention_days = {cfg.reader.read_retention_days}

[fetch]
auto_refresh_minutes = {cfg.fetch.auto_refresh_minutes}

[ui]
nerd_font = {_toml_str(cfg.ui.nerd_font)}
default_view = {_toml_str(cfg.ui.default_view)}
"""


def save_config(cfg: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    text = render_config(cfg)
    tmp = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(CONFIG_PATH)
