import json
import re
import threading
from pathlib import Path

from .models import Candidate
from .verdicts import ClipVerdict


def clip_key(c: Candidate) -> str:
    return "|".join(f"{s.ep}:{s.start:.2f}-{s.end:.2f}" for s in c.segments)


class VerdictStore:
    def __init__(self, cache_dir: str, spec: str):
        name = re.sub(r"[^a-z0-9]+", "-", spec.lower()).strip("-")
        self.path = Path(cache_dir).parent / "verdicts" / f"{name}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.data: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.data[row["key"]] = row["verdict"]

    def get(self, c: Candidate) -> ClipVerdict | None:
        found = self.data.get(clip_key(c))
        return ClipVerdict.model_validate({"clip": "A", **found}) if found else None

    def put(self, c: Candidate, v: ClipVerdict):
        key = clip_key(c)
        row = v.model_dump(exclude={"clip"})
        with self.lock:
            self.data[key] = row
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": key, "verdict": row}, ensure_ascii=False) + "\n")
