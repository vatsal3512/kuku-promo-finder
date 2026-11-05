import re
from collections import Counter, defaultdict

from rapidfuzz import fuzz

from .models import Show

TITLES = {
    "THE", "LADY", "LORD", "SIR", "MR", "MRS", "MISS", "MS", "DR", "MADAM", "MASTER",
    "DUKE", "DUCHESS", "KING", "QUEEN", "PRINCE", "PRINCESS", "YOUNG", "OLD",
}
ROLE_WORDS = {
    "LORD", "LADY", "MAID", "JUDGE", "GUARD", "CONSTABLE", "INFORMANT", "NOBLEWOMAN", "NOBLEMAN",
    "TOWNSMAN", "LOYALIST", "HOUSEKEEPER", "MATRIARCH", "PRIEST", "BUTLER", "FOOTMAN", "DRIVER",
    "SOLDIER", "NURSE", "DOCTOR", "OFFICER", "NARRATOR", "VOICE", "WOMAN", "MAN", "GIRL", "BOY",
    "STRANGER", "CROWD", "ALL", "CONSPIRATOR", "SENTRY", "SCOUT", "THUG", "SERVANT", "MOTHER",
    "FATHER", "SISTER", "BROTHER", "SON", "DAUGHTER", "WIFE", "HUSBAND", "GROOM", "BRIDE", "VILLAGER",
    "PHYSICIAN", "OFFICIAL", "CAPTAIN", "KNIGHT", "HOST", "WAITER", "SECRETARY", "ASSISTANT", "BOSS",
}
PROPER_WORD_RE = re.compile(r"\b[A-Z][a-z]{3,}\b")


def display(label: str) -> str:
    return " ".join(w.capitalize() for w in label.split())


def proper_names(show: Show) -> set[str]:
    counts = Counter(b.label for e in show.episodes for b in e.lines)
    return {label for label, n in counts.items() if n >= 2 and " " not in label and label not in ROLE_WORDS}


def resolve_label(label: str, delivery: list[str], proper: set[str]) -> str:
    for part in delivery:
        if part.upper() in proper:
            return part.upper()
    tokens = label.split()
    named = [t for t in tokens if t in proper]
    if len(named) == 1 and all(t in TITLES or t in proper for t in tokens):
        return named[0]
    return label


def apply_names(show: Show, overrides: list[dict] | None = None) -> dict:
    proper = proper_names(show)
    rules = []
    for item in overrides or []:
        lo, hi = (item.get("episodes") or [0, 10**6])[:2]
        rules.append((item["label"].upper(), int(lo), int(hi), item["name"]))
    mapping: dict[str, dict] = defaultdict(lambda: defaultdict(set))
    for episode in show.episodes:
        for beat in episode.lines:
            name = None
            for label, lo, hi, target in rules:
                if beat.label == label and lo <= episode.ep <= hi:
                    name = target
                    break
            canonical = name.upper() if name else resolve_label(beat.label, beat.delivery, proper)
            beat.speaker = display(canonical)
            mapping[beat.speaker][beat.label].add(episode.ep)
    return {
        speaker: {label: sorted(eps) for label, eps in labels.items()}
        for speaker, labels in mapping.items()
    }


def place_drift(show: Show, min_variants: int = 2) -> list[dict]:
    lowercase_vocab = set()
    occurrences: dict[str, Counter] = defaultdict(Counter)
    for episode in show.episodes:
        texts = [episode.logline, episode.continuity, *[b.text for b in episode.beats]]
        for text in texts:
            lowercase_vocab.update(w for w in re.findall(r"\b[a-z]{4,}\b", text))
            for word in PROPER_WORD_RE.findall(text):
                occurrences[word][episode.ep] += 1
    tokens = [w for w in occurrences if w.lower() not in lowercase_vocab]
    tokens.sort(key=lambda w: -sum(occurrences[w].values()))
    clusters: list[list[str]] = []
    for word in tokens:
        for cluster in clusters:
            head = cluster[0]
            if head[:3] == word[:3] and fuzz.ratio(head, word) >= 72:
                cluster.append(word)
                break
        else:
            clusters.append([word])
    report = []
    for cluster in clusters:
        if len(cluster) < min_variants:
            continue
        report.append({
            "variants": {
                w: {"count": sum(occurrences[w].values()), "episodes": sorted(occurrences[w])}
                for w in cluster
            }
        })
    report.sort(key=lambda r: -len(r["variants"]))
    return report


def label_drift(mapping: dict) -> dict:
    many = [
        {"character": speaker, "labels": labels}
        for speaker, labels in mapping.items()
        if len(labels) > 1
    ]
    by_label: dict[str, list] = defaultdict(list)
    for speaker, labels in mapping.items():
        for label, eps in labels.items():
            by_label[label].append({"character": speaker, "episodes": eps})
    shared = [{"label": label, "used_for": users} for label, users in by_label.items() if len(users) > 1]
    return {"characters_with_several_labels": many, "labels_used_for_several_characters": shared}
