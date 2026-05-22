import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass
class Bookmark:
    id: int
    url: str
    title: str
    description: str
    tag_names: list[str] = field(default_factory=list)
    date_added: datetime | None = None
    website_title: str | None = None
    website_description: str | None = None

    @property
    def local_id(self) -> str:
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]

    @property
    def display_title(self) -> str:
        return self.title or self.website_title or self.url

    def date_added_str(self, tz: ZoneInfo) -> str:
        if self.date_added is None:
            return "—"
        return self.date_added.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")

    def date_added_short(self, tz: ZoneInfo) -> str:
        if self.date_added is None:
            return "—"
        return self.date_added.astimezone(tz).strftime("%m-%d %H:%M")
