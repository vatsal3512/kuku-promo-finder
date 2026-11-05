from itertools import count

from rapidfuzz import fuzz

from .models import Beat, Candidate, Episode, Segment, Show
from .rules import Prior, is_continuous


class Snapper:
    def __init__(self, episode: Episode):
        self.episode = episode
        self.lines = episode.lines
        self.shots = episode.shots

    def inside_line(self, t: float) -> bool:
        return any(b.start + 0.05 < t < b.end - 0.05 for b in self.lines)

    def start_for(self, beat: Beat, max_lead: float):
        h = beat.start
        near = [t for t in self.shots if h - 1.0 <= t <= h and not self.inside_line(t)]
        if near:
            return round(max(near), 3)
        if not self.inside_line(h):
            return round(h, 3)
        far = [t for t in self.shots if h - max_lead <= t < h - 1.0 and not self.inside_line(t)]
        return round(max(far), 3) if far else None

    def end_for(self, beat: Beat, max_tail: float):
        c = beat.end
        near = [t for t in self.shots if c <= t <= c + max_tail and not self.inside_line(t)]
        if near:
            return round(min(near), 3)
        t = min(c + 0.3, self.episode.duration)
        return None if self.inside_line(t) else round(t, 3)


def top_beats(episode: Episode, priors: dict[str, Prior], attr: str, k: int) -> list[Beat]:
    ranked = sorted(episode.content, key=lambda b: getattr(priors[b.uid], attr), reverse=True)
    return ranked[:k]


def recap_end(prev: Episode, nxt: Episode) -> float:
    tail_lines = [b.text for b in prev.lines[-8:]]
    start = 0.0
    for beat in nxt.content:
        if beat.start > 15:
            break
        if beat.kind == "DIALOGUE" and any(fuzz.ratio(beat.text, t) >= 80 for t in tail_lines):
            start = beat.end
    return start


def generate(show: Show, priors: dict[str, Prior], cfg: dict) -> list[Candidate]:
    gates, gen = cfg["gates"], cfg["generation"]
    lo, hi = gates["min_duration"], gates["max_duration"]
    lead, tail, min_seg = gates["max_hook_offset"], gates["max_tail"], gates["min_segment"]
    ids = count(1)
    snappers = {e.ep: Snapper(e) for e in show.episodes}
    hooks = {e.ep: top_beats(e, priors, "hook", gen["hooks_per_episode"]) for e in show.episodes}
    cliffs = {e.ep: top_beats(e, priors, "cliff", gen["cliffs_per_episode"]) for e in show.episodes}
    for e in show.episodes:
        content = e.content
        if content:
            for extra in (content[0],):
                if extra not in hooks[e.ep]:
                    hooks[e.ep].append(extra)
            last_line = next((b for b in reversed(content) if b.kind in ("DIALOGUE", "ACTION")), None)
            if last_line and last_line not in cliffs[e.ep]:
                cliffs[e.ep].append(last_line)

    found: dict[tuple, Candidate] = {}

    def add(kind: str, segments: list[Segment], hook: Beat, cliff: Beat):
        if any(s.duration < min_seg for s in segments) and len(segments) > 1:
            return
        total = sum(s.duration for s in segments)
        if not lo <= total <= hi:
            return
        candidate = Candidate(f"C{next(ids):05d}", kind, segments, hook.uid, cliff.uid)
        found.setdefault(candidate.key, candidate)

    for e in show.episodes:
        snap = snappers[e.ep]
        for h in hooks[e.ep]:
            s = snap.start_for(h, lead)
            if s is None:
                continue
            for c in cliffs[e.ep]:
                if c.end <= h.start:
                    continue
                end = snap.end_for(c, tail)
                if end is not None:
                    add("single", [Segment(e.ep, s, end)], h, c)

    if gen.get("cross_episode", True):
        for prev, nxt in zip(show.episodes, show.episodes[1:]):
            if nxt.ep != prev.ep + 1 or not is_continuous(nxt):
                continue
            skip = recap_end(prev, nxt)
            opener = next((b for b in nxt.content if b.start >= skip), None)
            if opener is None:
                continue
            s2 = snappers[nxt.ep].start_for(opener, lead)
            if s2 is None:
                continue
            for h in hooks[prev.ep]:
                if prev.duration - h.start > hi:
                    continue
                s1 = snappers[prev.ep].start_for(h, lead)
                if s1 is None:
                    continue
                first = Segment(prev.ep, s1, prev.duration)
                for c in cliffs[nxt.ep]:
                    if c.start < s2:
                        continue
                    end = snappers[nxt.ep].end_for(c, tail)
                    if end is not None:
                        add("cross", [first, Segment(nxt.ep, s2, end)], h, c)

    if gen.get("montage", True):
        openers = []
        for e in show.episodes:
            snap = snappers[e.ep]
            for h in top_beats(e, priors, "hook", gen["montage_hooks_per_episode"]):
                s = snap.start_for(h, lead)
                if s is None:
                    continue
                options = [b for b in e.content if s + 6 <= b.end <= s + 25]
                if not options:
                    continue
                beat = max(options, key=lambda b: priors[b.uid].cliff + priors[b.uid].intensity)
                end = snap.end_for(beat, tail)
                if end is not None and end - s >= min_seg:
                    openers.append((e.ep, h, Segment(e.ep, s, end)))
        closers = []
        for e in show.episodes:
            snap = snappers[e.ep]
            for c in top_beats(e, priors, "cliff", gen["montage_cliffs_per_episode"]):
                end = snap.end_for(c, tail)
                if end is None:
                    continue
                options = [b for b in e.content if end - 35 <= b.start <= end - 8]
                if not options:
                    continue
                beat = max(options, key=lambda b: priors[b.uid].hook)
                s = snap.start_for(beat, lead)
                if s is not None and end - s >= min_seg:
                    closers.append((e.ep, c, Segment(e.ep, s, end)))
        speakers = {e.ep: {b.speaker for b in e.lines} for e in show.episodes}
        for ep_a, h, seg_a in openers:
            for ep_b, c, seg_b in closers:
                gap = ep_b - ep_a
                if not 1 <= gap <= gen["montage_max_gap"]:
                    continue
                if not (speakers[ep_a] & speakers[ep_b]):
                    continue
                add("montage", [seg_a, seg_b], h, c)

    return list(found.values())
