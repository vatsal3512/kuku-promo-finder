import numpy as np

from .features import beats_in
from .models import Candidate, Show

NUMERIC = [
    "hook_prior", "opening_peak", "hook_offset", "cliff_prior", "tail_after_cliff", "intensity", "peak",
    "escalation", "stakes", "dead_air", "lines", "context_risk", "series_position",
]
NAMES = NUMERIC + ["duration", "action_share", "segments", "cross", "montage", "sound_off", "speakers", "rule_score"]


def vector(c: Candidate, show: Show) -> list[float]:
    f = c.features
    if "action_share" not in f:
        beats = [b for _, b in beats_in(c, show)]
        f["action_share"] = round(sum(b.kind == "ACTION" for b in beats) / max(1, len(beats)), 4)
    rule = c.judge.get("rule_score", c.score) if c.judge else c.score
    return [float(f[k]) for k in NUMERIC] + [
        c.duration, f["action_share"], len(c.segments), float(c.kind == "cross"), float(c.kind == "montage"),
        float(f["sound_off_hook"]), len(f["speakers"]), rule,
    ]


def fit(X: np.ndarray, y: np.ndarray, lam: float):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    A = np.c_[np.ones(len(X)), (X - mu) / sd]
    reg = np.eye(A.shape[1]) * lam
    reg[0, 0] = 0
    w = np.linalg.solve(A.T @ A + reg, A.T @ y)
    return lambda Q: np.c_[np.ones(len(Q)), (Q - mu) / sd] @ w, w


def spearman(a, b) -> float:
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def moment_groups(cands: list[Candidate]) -> np.ndarray:
    from .rank import overlap
    parent = list(range(len(cands)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            if overlap(cands[i], cands[j]) >= 0.5:
                parent[root(i)] = root(j)
    return np.array([root(i) for i in range(len(cands))])


def cross_validate(X: np.ndarray, y: np.ndarray, lam: float, groups: np.ndarray | None = None, folds: int = 10) -> float:
    rng = np.random.default_rng(0)
    preds = np.zeros(len(y))
    if groups is None:
        groups = np.arange(len(y))
    unique = rng.permutation(np.unique(groups))
    for chunk in np.array_split(unique, folds):
        fold = np.where(np.isin(groups, chunk))[0]
        if not len(fold):
            continue
        train = np.setdiff1d(np.arange(len(y)), fold)
        predict, _ = fit(X[train], y[train], lam)
        preds[fold] = predict(X[fold])
    return spearman(preds, y)


def learn_from_judge(judged: list[Candidate], others: list[Candidate], show: Show, lam: float = 20.0) -> dict:
    labelled = [c for c in judged if "judge_score" in c.judge]
    if len(labelled) < 20 or not others:
        return {"trained": False}
    X = np.array([vector(c, show) for c in labelled])
    y = np.array([c.judge["judge_score"] for c in labelled])
    rules = np.array([c.judge.get("rule_score", 0.0) for c in labelled])
    cv = cross_validate(X, y, lam, moment_groups(labelled))
    predict, w = fit(X, y, lam)
    preds = predict(np.array([vector(c, show) for c in others]))
    for c, p in zip(others, preds):
        c.features["predicted_judge"] = round(float(p), 4)
    weights = sorted(zip(NAMES, w[1:]), key=lambda t: -abs(t[1]))[:8]
    return {
        "trained": True,
        "labels": len(labelled),
        "cv_spearman": round(cv, 3),
        "rule_score_spearman": round(spearman(rules, y), 3),
        "ranker": "learned" if cv > spearman(rules, y) else "rule",
        "top_weights": [[n, round(float(x), 4)] for n, x in weights],
    }
