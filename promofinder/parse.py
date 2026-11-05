import re
from pathlib import Path

from .models import Beat, Episode, Scene, Show

TIME_RE = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?(?![\d:])")
CLOCK = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?"
RANGE_RE = re.compile(
    r"(?:Start\s*:?\s*)?[\(\[]?\s*(" + CLOCK + r")\s*[\)\]]?\s*(?:\||-->|->|–|—|-|to)\s*(?:End\s*:?\s*)?[\(\[]?\s*(" + CLOCK + r")\s*[\)\]]?",
    re.I,
)
TAG_RE = re.compile(r"^\*\*(.+?)\*\*\s*(.*)$")
PLAIN_TAG_RE = re.compile(r"^([A-Z][A-Z0-9 .'&/\-]{1,40}(?:\s*\([^)]*\))*)\s*:\s*(.*)$")
HEADER_RE = re.compile(r"^(EPISODE NUMBER|EPISODE LOGLINE|EPISODE TITLE|CONTINUITY NOTES)\s*:\s*(.*)$", re.I)
SCENE_RE = re.compile(r"^SCENE\s+(\d+)\s*$", re.I)
SCENE_FIELD_RE = re.compile(r"^SCENE\s+(HEADING|START|END)\s*:\s*(.*)$", re.I)
VOICE_RE = re.compile(r"(O\.S\.|V\.O\.|O\.C\.|OFF-SCREEN|OFF SCREEN|CONT'D|CONTINUES|CONTINUING)", re.I)
NUM_RE = re.compile(r"(\d+)")
STOP_RE = re.compile(r"^(---|SCENE\s+\d+|ACTIONS AND DIALOGUE)", re.I)
NON_DIALOGUE = {
    "CAMERA": "CAMERA",
    "SHOT": "CAMERA",
    "ACTION": "ACTION",
    "ACTIONS": "ACTION",
    "SOUND FX": "SFX",
    "SOUND": "SFX",
    "SFX": "SFX",
    "MUSIC": "SFX",
    "TEXT": "TEXT",
    "SUPER": "TEXT",
    "TITLE": "TEXT",
    "ON-SCREEN TEXT": "TEXT",
}


SCRIPT_SUFFIXES = {".txt", ".md", ".fountain", ".text"}


def parse_time(value: str):
    match = TIME_RE.search(value or "")
    if not match:
        return None
    hours, minutes, seconds, frac = match.groups()
    total = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
    if frac:
        total += int(frac) / (10 ** len(frac))
    return round(total, 3)


def split_tag(tag: str):
    name = tag.split("(", 1)[0].strip().rstrip(":").strip()
    voice = ""
    delivery = []
    for group in re.findall(r"\(([^)]*)\)", tag):
        found = VOICE_RE.findall(group)
        if found:
            voice = found[0].upper()
        for part in re.split(r"[,/;]", VOICE_RE.sub("", group)):
            part = part.strip(" .-")
            if part:
                delivery.append(part)
    return name, voice, delivery


def read_block(lines: list[str], i: int) -> tuple[str, int]:
    collected = []
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or TAG_RE.match(raw) or STOP_RE.match(raw) or RANGE_RE.match(raw):
            break
        if PLAIN_TAG_RE.match(raw) and i + 1 < len(lines) and RANGE_RE.search(lines[i + 1]):
            break
        collected.append(raw)
        i += 1
    return " ".join(collected), i


def parse_text(text: str, source: str = "") -> Episode:
    lines = text.splitlines()
    header: dict[str, str] = {}
    scenes: list[Scene] = []
    raw_beats = []
    scene = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        header_match = HEADER_RE.match(line)
        if header_match:
            header[header_match.group(1).upper()] = header_match.group(2).strip()
            i += 1
            continue
        scene_match = SCENE_RE.match(line)
        if scene_match:
            scene = Scene(int(scene_match.group(1)))
            scenes.append(scene)
            i += 1
            continue
        field_match = SCENE_FIELD_RE.match(line)
        if field_match and scene is not None:
            key, value = field_match.group(1).upper(), field_match.group(2).strip()
            if key == "HEADING":
                scene.heading = value
            elif parse_time(value) is not None:
                setattr(scene, "start" if key == "START" else "end", parse_time(value))
            i += 1
            continue
        tag_match = TAG_RE.match(line) or PLAIN_TAG_RE.match(line)
        if tag_match:
            tag, inline = tag_match.group(1).strip(), tag_match.group(2).strip()
            range_match = RANGE_RE.search(inline) if inline else None
            if range_match:
                around = f"{inline[:range_match.start()]} {inline[range_match.end():]}".strip(" :-|")
                if around:
                    body, k = around, i + 1
                else:
                    body, k = read_block(lines, i + 1)
            else:
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                range_match = RANGE_RE.search(lines[j]) if j < len(lines) else None
                if not range_match:
                    i += 1
                    continue
                rest = lines[j][range_match.end():].strip(" :-|")
                if rest:
                    body, k = rest, j + 1
                else:
                    body, k = read_block(lines, j + 1)
                if inline and not body:
                    body = inline
            raw_beats.append((tag, range_match, body, scene.num if scene else 0))
            i = k
            continue
        i += 1

    number_source = header.get("EPISODE NUMBER", "") or Path(source).stem
    number_match = NUM_RE.search(number_source) or NUM_RE.search(Path(source).stem)
    ep = int(number_match.group(1)) if number_match else 0

    beats = []
    for order, (tag, range_match, body, scene_num) in enumerate(raw_beats):
        start = parse_time(range_match.group(1)) or 0.0
        end = parse_time(range_match.group(2)) or start
        name, voice, delivery = split_tag(tag)
        kind = NON_DIALOGUE.get(name.upper(), "DIALOGUE")
        text_value = body.strip()
        if kind == "DIALOGUE":
            text_value = text_value.strip('"“” ')
        beats.append((start, order, Beat(
            uid="",
            ep=ep,
            idx=0,
            scene=scene_num,
            kind=kind,
            start=start,
            end=max(end, start),
            text=text_value,
            label=name.upper() if kind == "DIALOGUE" else "",
            voice=voice,
            delivery=delivery if kind == "DIALOGUE" else [],
        )))
    beats.sort(key=lambda item: (item[0], item[1]))
    ordered = []
    for idx, (_, _, beat) in enumerate(beats):
        beat.idx = idx
        beat.uid = f"E{ep:03d}-{idx:03d}"
        ordered.append(beat)

    duration = max([s.end for s in scenes] + [b.end for b in ordered] + [0.0])
    shots = sorted({0.0, round(duration, 3)} | {b.start for b in ordered if b.kind == "CAMERA"} | {b.end for b in ordered if b.kind == "CAMERA"})
    return Episode(
        ep=ep,
        title=header.get("EPISODE NUMBER", f"Episode {ep}"),
        logline=header.get("EPISODE LOGLINE", ""),
        continuity=header.get("CONTINUITY NOTES", ""),
        source=source,
        scenes=scenes,
        beats=ordered,
        shots=shots,
        duration=round(duration, 3),
    )


def parse_file(path: Path) -> Episode:
    return parse_text(Path(path).read_text(encoding="utf-8", errors="replace"), str(path))


def load_show(input_path: str, name: str | None = None) -> Show:
    root = Path(input_path)
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.suffix.lower() in SCRIPT_SUFFIXES)
    episodes = [e for e in (parse_file(p) for p in files) if e.beats]
    numbers = [e.ep for e in episodes]
    renumbered = len(set(numbers)) < len(numbers) or 0 in numbers
    if renumbered:
        episodes.sort(key=lambda e: natural_key(Path(e.source).name))
        for n, episode in enumerate(episodes, 1):
            renumber(episode, n)
    episodes.sort(key=lambda e: e.ep)
    show_name = name or (root.stem if root.is_file() else root.name)
    show = Show(show_name, episodes)
    show.renumbered = renumbered
    return show


def natural_key(name: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def renumber(episode: Episode, n: int):
    episode.ep = n
    for beat in episode.beats:
        beat.ep = n
        beat.uid = f"E{n:03d}-{beat.idx:03d}"
