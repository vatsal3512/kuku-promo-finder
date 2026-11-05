from dataclasses import dataclass, field


@dataclass
class Beat:
    uid: str
    ep: int
    idx: int
    scene: int
    kind: str
    start: float
    end: float
    text: str
    label: str = ""
    voice: str = ""
    delivery: list[str] = field(default_factory=list)
    speaker: str = ""

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Scene:
    num: int
    heading: str = ""
    start: float = 0.0
    end: float = 0.0


@dataclass
class Episode:
    ep: int
    title: str
    logline: str
    continuity: str
    source: str
    scenes: list[Scene]
    beats: list[Beat]
    shots: list[float]
    duration: float

    @property
    def content(self) -> list[Beat]:
        return [b for b in self.beats if b.kind != "CAMERA"]

    @property
    def lines(self) -> list[Beat]:
        return [b for b in self.beats if b.kind == "DIALOGUE"]


@dataclass
class Show:
    name: str
    episodes: list[Episode]

    def __post_init__(self):
        self.by_ep = {e.ep: e for e in self.episodes}
        self.beats = {b.uid: b for e in self.episodes for b in e.beats}


@dataclass
class Segment:
    ep: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


@dataclass
class Candidate:
    cid: str
    kind: str
    segments: list[Segment]
    hook_uid: str
    cliff_uid: str
    features: dict = field(default_factory=dict)
    parts: dict = field(default_factory=dict)
    score: float = 0.0
    hook_type: str = ""
    policy: list[str] = field(default_factory=list)
    arc: str = ""
    why: str = ""
    judge: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return round(sum(s.duration for s in self.segments), 3)

    @property
    def key(self) -> tuple:
        return tuple((s.ep, round(s.start, 1), round(s.end, 1)) for s in self.segments)
