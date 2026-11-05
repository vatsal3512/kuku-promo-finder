from collections import Counter
from pathlib import Path

from .parse import SCRIPT_SUFFIXES, load_show, parse_file


def check_input(input_path: str) -> dict:
    root = Path(input_path)
    if not root.exists():
        return {"ok": False, "warnings": [f"{input_path} does not exist"]}
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.suffix.lower() in SCRIPT_SUFFIXES)
    warnings = []
    if not files:
        warnings.append(f"No script files ({', '.join(sorted(SCRIPT_SUFFIXES))}) found")
    empty = []
    for path in files:
        if not parse_file(path).beats:
            empty.append(path.name)
    if empty:
        warnings.append(f"{len(empty)} file(s) produced no timed beats and will be skipped: {', '.join(empty[:5])}")
    show = load_show(input_path)
    rows = []
    for e in show.episodes:
        kinds = Counter(b.kind for b in e.beats)
        rows.append({
            "episode": e.ep, "file": Path(e.source).name, "duration": e.duration, "scenes": len(e.scenes),
            "beats": len(e.beats), "dialogue": kinds["DIALOGUE"], "action": kinds["ACTION"],
            "camera": kinds["CAMERA"], "sound": kinds["SFX"],
        })
        if not kinds["DIALOGUE"]:
            warnings.append(f"Episode {e.ep} has no dialogue lines")
        if e.duration < 20:
            warnings.append(f"Episode {e.ep} is {e.duration:.0f}s long, too short for a 20 s promo on its own")
        if e.duration > 900:
            warnings.append(f"Episode {e.ep} is {e.duration:.0f}s long; check the time format")
    if rows and not any(r["camera"] for r in rows):
        warnings.append("No CAMERA lines found; cuts will snap to line boundaries instead of shot changes")
    numbers = [r["episode"] for r in rows]
    if numbers and numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        warnings.append(f"Episode numbers are not consecutive: {numbers[:12]}{'...' if len(numbers) > 12 else ''}")
    if getattr(show, "renumbered", False):
        warnings.append("Episode numbers were missing or repeated, so episodes were numbered by file order")
    return {
        "ok": bool(rows),
        "show": show.name,
        "files": len(files),
        "episodes": len(rows),
        "beats": sum(r["beats"] for r in rows),
        "total_minutes": round(sum(r["duration"] for r in rows) / 60, 1),
        "warnings": warnings,
        "per_episode": rows,
    }
