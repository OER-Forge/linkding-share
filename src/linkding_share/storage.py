import json
import time
from pathlib import Path

from platformdirs import user_data_dir


def _data_dir() -> Path:
    p = Path(user_data_dir("linkding-share", appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


class State:
    """Tracks per-bookmark read status locally across runs.

    On-disk: {"read": {local_id: unix_ts, ...}}
    """

    def __init__(self, read_retention_days: int = 0) -> None:
        self.path = _data_dir() / "state.json"
        self.read: dict[str, float] = {}
        self._undo_stack: list[tuple[str, float | None]] = []
        self._load()
        if read_retention_days > 0:
            self._prune_read(read_retention_days)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        raw_read = data.get("read", {})
        if isinstance(raw_read, dict):
            self.read = {
                str(k): float(v)
                for k, v in raw_read.items()
                if isinstance(v, (int, float))
            }

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps({"read": dict(sorted(self.read.items()))}))
        except OSError:
            pass

    def _prune_read(self, retention_days: int) -> None:
        cutoff = time.time() - retention_days * 86400
        before = len(self.read)
        self.read = {k: v for k, v in self.read.items() if v >= cutoff}
        if len(self.read) != before:
            self._save()

    def mark_read(self, local_id: str) -> None:
        if local_id not in self.read:
            self._undo_stack.append((local_id, None))
            if len(self._undo_stack) > 20:
                self._undo_stack.pop(0)
            self.read[local_id] = time.time()
            self._save()

    def toggle_read(self, local_id: str) -> bool:
        prev_ts = self.read.get(local_id)
        self._undo_stack.append((local_id, prev_ts))
        if len(self._undo_stack) > 20:
            self._undo_stack.pop(0)
        if local_id in self.read:
            del self.read[local_id]
        else:
            self.read[local_id] = time.time()
        self._save()
        return local_id in self.read

    def is_read(self, local_id: str) -> bool:
        return local_id in self.read

    def undo_last_read(self) -> tuple[str, bool] | None:
        if not self._undo_stack:
            return None
        local_id, prev_ts = self._undo_stack.pop()
        if prev_ts is None:
            self.read.pop(local_id, None)
        else:
            self.read[local_id] = prev_ts
        self._save()
        return local_id, local_id in self.read
