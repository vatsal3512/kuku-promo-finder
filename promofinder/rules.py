import re
from dataclasses import dataclass

from .models import Beat, Episode, Show

IMPACT_RE = re.compile(
    r"\b(slap\w*|punch\w*|strik\w*|struck|crash\w*|explo\w*|detonat\w*|shatter\w*|gasp\w*|scream\w*|"
    r"slam\w*|whip\w*|blood\w*|bleed\w*|fire|flames?|blaze|inferno|collaps\w*|kneel\w*|knees?|drag\w*|"
    r"grab\w*|shove\w*|tackl\w*|throw\w*|threw|fling\w*|flung|snatch\w*|seiz\w*|chain\w*|shackl\w*|"
    r"burn\w*|sizzl\w*|thud|clang\w*|shriek\w*|lung\w*|yank\w*|smash\w*|bang\w*|glar\w*|freez\w*|"
    r"recoil\w*|tear\w*|tore|rip\w*|clench\w*|fist)\b",
    re.I,
)
STAKES_RE = re.compile(
    r"\b(marry|married|marrying|marriage|wedding|bride|groom|husband|wife|dead|die|dies|dying|death|"
    r"kill\w*|poison\w*|arrest\w*|hang\w*|gallows|noose|execut\w*|witch\w*|duke|duchess|disown\w*|"
    r"betray\w*|pregnan\w*|divorce\w*|prison\w*|condemn\w*|traitor|treason|stole|steal\w*|thief|"
    r"murder\w*|alive|grace|inherit\w*|dowry|son|mother|father|sister|blood|fortune|title|crown|"
    r"secret|lie|lied|liar|never|everything|nothing|ring|vow\w*)\b",
    re.I,
)
INTENSE = {
    "scream": 1.0, "shriek": 1.0, "roar": 1.0, "hysteri": 1.0, "enraged": 1.0, "furious": 0.95,
    "shout": 0.9, "bellow": 0.9, "venom": 0.9, "cruel": 0.85, "vicious": 0.85, "sadistic": 0.9,
    "desperate": 0.85, "horrif": 0.85, "terrif": 0.85, "panic": 0.85, "agon": 0.85, "anguish": 0.85,
    "outrag": 0.8, "livid": 0.9, "menac": 0.8, "threat": 0.8, "deadly": 0.8, "lethal": 0.8,
    "sob": 0.75, "weep": 0.7, "crying": 0.7, "heartbr": 0.7, "devastat": 0.75, "betray": 0.75,
    "mock": 0.7, "gloat": 0.7, "taunt": 0.7, "scorn": 0.65, "smug": 0.6, "spite": 0.7, "defian": 0.65,
    "shock": 0.75, "stunned": 0.7, "accus": 0.7, "fierce": 0.65, "harsh": 0.6, "cold": 0.5,
    "trembl": 0.55, "pleading": 0.65, "begging": 0.7, "sinister": 0.7, "malic": 0.75, "dangerous": 0.75,
    "imperious": 0.6, "commanding": 0.5, "resolute": 0.4, "steely": 0.45, "gentle": 0.15, "soft": 0.15,
    "tender": 0.2, "warm": 0.15, "calm": 0.2, "playful": 0.15, "amused": 0.2, "whisper": 0.35,
}
QUESTION_RE = re.compile(r"\?\s*$")
OPEN_END_RE = re.compile(r"(\?|\.\.\.|…|—|-)\s*$")
CLIFF_CUE_RE = re.compile(
    r"(cliffhanger|cut(s|ting)? (sharply |abruptly )?to black|sting|freez\w*|holds? on|abrupt\w*|"
    r"eyes (snap |go )?wide|widen\w*|realiz\w*|stares?|turns? (sharply|slowly)|silence|unresolved)",
    re.I,
)
THREAT_RE = re.compile(
    r"\b(you will|you'll|i will|i'll|before|unless|or else|if you|you cannot|no one|never|"
    r"going to|let them|take her|take him|arrest|hang|burn|kill|die)\b",
    re.I,
)
CONTEXT_START_RE = re.compile(r"^(\.\.\.|…|and\b|but\b|so\b|then\b|because\b|or\b|which\b|that\b|too\b)", re.I)
CONTINUES_RE = re.compile(r"(picks? up|directly|immediately|continu|follows? (directly|immediately|right))", re.I)

HOOK_TYPES = [
    ("betrayal", re.compile(r"\b(betray\w*|marrying me|holding her hand|changed my mind|never going to marry|you knew|affair|cheat\w*|abandon\w*|chose her|instead of you)\b", re.I)),
    ("reveal", re.compile(r"\b(duke|your grace|alive|who are you|always me|lost son|crest|it's you|my son|recogni\w*|identity|imposter|impostor|truth)\b", re.I)),
    ("injustice", re.compile(r"\b(arrest\w*|planted|accus\w*|witch\w*|trial|guilty|condemn\w*|gallows|hang\w*|frame\w*|poison\w*|magistrate|sentence\w*|execut\w*)\b", re.I)),
    ("ultimatum", re.compile(r"\b(or your|or else|unless|name your price|do it|bare hands|choose|withdraw the charges|if you want)\b", re.I)),
    ("rescue", re.compile(r"\b(take your hands off|let her go|let go of|stay behind me|i've got you|are you hurt|protect\w*|rescue\w*|don't touch her|step away)\b", re.I)),
    ("humiliation", re.compile(r"\b(beggar|worthless|plain|servant|kneel\w*|crawl\w*|mock\w*|disgrace\w*|embarrass\w*|beneath|your place|gutter|nobody|rat|filth|ashamed|laugh\w*)\b", re.I)),
    ("defiance", re.compile(r"\b(i will not|i won't|i chose|burn it|you cannot|dignity|i accept|how dare|enough|never again|i am not)\b", re.I)),
    ("romance", re.compile(r"\b(love\w*|kiss\w*|heart|your touch|hold me|beautiful|my wife|my husband)\b", re.I)),
]
HOOK_PHRASE = {
    "betrayal": "a public betrayal",
    "reveal": "a reveal",
    "injustice": "an injustice",
    "ultimatum": "an ultimatum",
    "rescue": "a rescue",
    "humiliation": "a humiliation",
    "defiance": "a defiant stand",
    "romance": "a charged romantic beat",
    "confrontation": "a confrontation",
}
POLICY = {
    "sexual": (re.compile(r"\b(naked|nude|bare skin|bare chest|shirtless|carnal|seduc\w*|undress\w*|entangle\w*|lust\w*|passionate embrace|sex\w*|aroused|moan\w*|in this bed|in your bed)\b", re.I), "high"),
    "gore": (re.compile(r"\b(blood\w*|bleed\w*|lacerat\w*|gash\w*|flesh|wound\w*|bone|shredded)\b", re.I), "medium"),
    "violence": (re.compile(r"\b(punch\w*|strik\w*|struck|whip\w*|tackl\w*|chok\w*|throat|beat\w*|shove\w*|slap\w*|stab\w*)\b", re.I), "low"),
    "weapon": (re.compile(r"\b(rifles?|swords?|knife|knives|dagger|guns?|halberds?|club|iron pipe|branding|red-hot|searing|explosion|detonat\w*|fireball|pistol)\b", re.I), "low"),
    "minor": (re.compile(r"\b(child|boy|little brother|seven|kid|schoolgirl|underage)\b", re.I), "low"),
    "self_harm": (re.compile(r"\b(suicide|kill myself|self-harm|end my life)\b", re.I), "high"),
    "coercion": (re.compile(r"\b(or your (husband|brother|son|daughter)|unless you|blackmail\w*|forced? (to|into)|or else)\b", re.I), "medium"),
}


@dataclass
class Prior:
    hook: float
    cliff: float
    intensity: float
    impact: float
    stakes: float


def intensity_of(beat: Beat) -> float:
    if beat.kind == "DIALOGUE":
        tags = " ".join(beat.delivery).lower()
        level = max([w for key, w in INTENSE.items() if key in tags] or [0.3])
        if beat.text.endswith("!"):
            level = min(1.0, level + 0.15)
        return level
    hits = len(IMPACT_RE.findall(beat.text))
    return min(1.0, 0.25 + 0.25 * hits)


def beat_prior(beat: Beat, episode: Episode) -> Prior:
    text = beat.text
    intensity = intensity_of(beat)
    impact = min(1.0, len(IMPACT_RE.findall(text)) / 2)
    stakes = min(1.0, len(STAKES_RE.findall(text)) / 2)
    short = 1.0 if beat.kind == "DIALOGUE" and beat.words <= 8 else 0.0
    punct = 1.0 if beat.kind == "DIALOGUE" and (text.endswith("!") or text.endswith("?")) else 0.0
    opening = 1.0 if beat.start <= 12 else 0.0
    hook = 0.34 * intensity + 0.22 * impact + 0.2 * stakes + 0.1 * short + 0.08 * punct + 0.06 * opening
    if beat.kind == "SFX":
        hook *= 0.6
    tail_gap = max(0.0, episode.duration - beat.end)
    tail = 1.0 if tail_gap <= 6 else max(0.0, 1 - (tail_gap - 6) / 30)
    open_end = 1.0 if OPEN_END_RE.search(text) else 0.0
    threat = 1.0 if THREAT_RE.search(text) else 0.0
    cue = 1.0 if CLIFF_CUE_RE.search(text) else 0.0
    cliff = 0.24 * tail + 0.18 * open_end + 0.16 * threat + 0.16 * stakes + 0.16 * intensity + 0.1 * cue
    if beat.kind == "SFX":
        cliff *= 0.5
    return Prior(round(min(hook, 1.0), 4), round(min(cliff, 1.0), 4), round(intensity, 4), round(impact, 4), round(stakes, 4))


def score_beats(show: Show) -> dict[str, Prior]:
    return {b.uid: beat_prior(b, e) for e in show.episodes for b in e.content}


def hook_type_of(text: str) -> str:
    best, best_hits = "confrontation", 0
    for name, pattern in HOOK_TYPES:
        hits = len(pattern.findall(text))
        if hits > best_hits:
            best, best_hits = name, hits
    return best


def policy_flags(text: str) -> list[str]:
    flags = []
    hits = {name: len(pattern.findall(text)) for name, (pattern, _) in POLICY.items()}
    for name, (_, severity) in POLICY.items():
        n = hits[name]
        if not n:
            continue
        level = severity
        if name == "sexual" and n == 1:
            level = "medium"
        if name == "gore" and n >= 3:
            level = "high"
        if name == "minor" and (hits["violence"] or hits["sexual"] or hits["weapon"]):
            level = "high" if hits["sexual"] else "medium"
        if name == "weapon" and re.search(r"\b(eye|face|skin)\b", text, re.I) and re.search(r"branding|red-hot|searing", text, re.I):
            level = "medium"
        flags.append(f"{name}:{level}")
    return flags


def is_continuous(episode: Episode) -> bool:
    return bool(CONTINUES_RE.search(episode.continuity or ""))
