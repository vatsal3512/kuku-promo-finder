import copy
from pathlib import Path

import yaml

DEFAULTS = {
    "gates": {
        "min_duration": 20.0,
        "max_duration": 60.0,
        "max_hook_offset": 3.0,
        "max_tail": 1.5,
        "max_segments": 3,
        "min_segment": 4.0,
    },
    "generation": {
        "hooks_per_episode": 12,
        "cliffs_per_episode": 6,
        "cross_episode": True,
        "montage": True,
        "montage_max_gap": 6,
        "montage_hooks_per_episode": 4,
        "montage_cliffs_per_episode": 3,
    },
    "weights": {
        "hook": 0.30,
        "cliff": 0.30,
        "intensity": 0.12,
        "stakes": 0.10,
        "escalation": 0.05,
        "sound_off": 0.05,
        "funnel": 0.12,
    },
    "penalties": {
        "dead_air_per_second": 0.03,
        "context": 0.10,
        "single": 0.0,
        "cross": 0.02,
        "montage": 0.08,
        "policy_high": 0.5,
        "policy_medium": 0.05,
    },
    "selection": {
        "top": 15,
        "pool": 400,
        "mmr_lambda": 0.75,
        "max_overlap": 0.35,
        "max_per_episode": 2,
        "control_max_position": 0.2,
        "one_per_scene": True,
    },
    "llm": {
        "model": "nvidia/nvidia/nemotron-3-ultra-550b-a55b",
        "judge_model": "",
        "judge_pool": 80,
        "refine_seeds": 20,
        "refine_variants": 3,
        "judge_repeats": 2,
        "premise_zone": 0.1,
        "learned_wave": 0,
        "learn_lambda": 20.0,
        "jury_model": "",
        "jury_top": 25,
        "judge_batch": 5,
        "pairwise_top": 12,
        "temperature": 0.2,
        "max_tokens": 8000,
        "concurrency": 6,
        "timeout": 240,
        "cache_dir": ".cache/llm",
        "blend": 0.65,
        "funnel_bonus": 0.10,
        "spoiler_major_penalty": 0.08,
        "min_standalone": 3,
        "min_cliffhanger": 3,
    },
    "names": [],
}


def merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | None = None) -> dict:
    if path and not Path(path).exists() and Path(path).name == "config.yaml":
        bundled = Path(__file__).resolve().parent.parent / "config.yaml"
        path = str(bundled) if bundled.exists() else path
    if path and Path(path).exists():
        return merge(DEFAULTS, yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    return copy.deepcopy(DEFAULTS)
