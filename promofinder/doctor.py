from collections import Counter
from pathlib import Path

from .parse import RANGE_RE, SCRIPT_SUFFIXES, load_show, parse_file, parse_time, read_script, split_episodes


def parse_path_beats(episode) -> list[tuple[float, float]]:
    source = episode.source.split("#episode-")[0]
    text = read_script(Path(source))
    chunks = split_episodes(text)
    if chunks:
        text = next((body for n, body in chunks if n == episode.ep), text)
    out = []
    for line in text.splitlines():
        m = RANGE_RE.search(line)
        if m:
            start, end = parse_time(m.group(1)), parse_time(m.group(2))
            if start is not None and end is not None:
                out.append((start, end))
    return out


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
        raw = parse_path_beats(e)
        backwards = sum(1 for x in raw if x[1] < x[0])
        if backwards:
            warnings.append(f"Episode {e.ep}: {backwards} line(s) end before they start; check the time format")
        jumps = sum(1 for a, b2 in zip(raw, raw[1:]) if b2[0] < a[0] - 5)
        if jumps:
            warnings.append(f"Episode {e.ep}: times jump backwards {jumps} time(s) in file order; do the times restart in every scene?")
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


def probe_model(spec: str, llm_cfg: dict) -> dict:
    import time

    from pydantic import BaseModel

    from .llm import LLM
    from .providers import PROVIDERS, LLMError, key_pool, load_env_file

    class Probe(BaseModel):
        ok: bool
        word: str = ""

    load_env_file()
    out = {"model": spec, "ok": False}
    provider = spec.split("/", 1)[0]
    if provider in PROVIDERS:
        out["keys_found"] = len(key_pool(PROVIDERS[provider][1])) if PROVIDERS[provider][1] else 0
    started = time.time()
    try:
        llm = LLM(spec, {**llm_cfg, "max_tokens": 400, "max_timeouts": 1, "timeout": 60})
        nonce = str(time.time())
        answer = llm.json("Reply in JSON only.", f'Probe {nonce}. Return {{"ok": true, "word": "ready"}}.', Probe)
        out.update(ok=bool(answer.ok), seconds=round(time.time() - started, 1), json_ok=True)
        if out["seconds"] > 30:
            out["warning"] = "slow: a full run may take much longer than usual; try --profile fast"
    except LLMError as exc:
        out.update(seconds=round(time.time() - started, 1), error_type=type(exc).__name__, error=str(exc)[:300])
    return out
