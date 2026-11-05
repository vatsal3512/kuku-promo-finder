import json
import re
from pathlib import Path

import pytest

from promofinder.config import load_config
from promofinder.llm import extract_json
from promofinder.parse import load_show, parse_time, split_tag
from promofinder.pipeline import run

FIXTURE = Path(__file__).parent / "fixtures" / "sample_show"


def test_parse_time_variants():
    assert parse_time("00:04.80") == 4.8
    assert parse_time("01:02.5") == 62.5
    assert parse_time("3:07") == 187
    assert parse_time("nope") is None


def test_split_tag_voice_and_delivery():
    name, voice, delivery = split_tag("THE BEARDED STRANGER (O.S.) (Deep, Resonant)")
    assert name == "THE BEARDED STRANGER"
    assert voice == "O.S."
    assert delivery == ["Deep", "Resonant"]
    name, voice, delivery = split_tag("LORD ASHCROFT (O.S. / Continues)")
    assert name == "LORD ASHCROFT" and voice == "O.S." and delivery == []


def test_show_parses_in_order():
    show = load_show(str(FIXTURE))
    assert [e.ep for e in show.episodes] == [1, 2]
    for episode in show.episodes:
        starts = [b.start for b in episode.beats]
        assert starts == sorted(starts)
        assert episode.duration >= max(b.end for b in episode.beats)
        assert episode.shots[0] == 0.0
        assert len({b.uid for b in episode.beats}) == len(episode.beats)
    assert show.episodes[0].lines[0].text == "Who burned the sauce?!"


def test_extract_json_handles_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure: {"b": [1, 2]} done') == {"b": [1, 2]}


@pytest.fixture()
def offline_result(tmp_path):
    return run(str(FIXTURE), out_root=str(tmp_path), mode="offline", config_path=None, top=5, log=lambda *_: None)


def test_offline_outputs_obey_gates(offline_result):
    show = load_show(str(FIXTURE))
    cfg = load_config(None)
    assert offline_result["records"]
    for record in offline_result["records"]:
        assert cfg["gates"]["min_duration"] <= record["duration"] <= cfg["gates"]["max_duration"]
        first = record["segments"][0]
        assert record["hook"]["episode"] == first["episode"]
        hook_beat = show.beats[record["hook"]["beat_id"]]
        assert 0 <= hook_beat.start - first["start_seconds"] <= cfg["gates"]["max_hook_offset"]
        for seg in record["segments"]:
            episode = show.by_ep[seg["episode"]]
            assert 0 <= seg["start_seconds"] < seg["end_seconds"] <= episode.duration
            for line in episode.lines:
                for cut in (seg["start_seconds"], seg["end_seconds"]):
                    assert not (line.start + 0.05 < cut < line.end - 0.05)


def test_offline_writes_all_files(offline_result):
    out = Path(offline_result["out_dir"])
    for name in ["promos.json", "promos.md", "promos.csv", "edl.csv", "ffmpeg_cuts.sh", "candidates_scored.jsonl", "run_meta.json", "name_drift.json"]:
        assert (out / name).exists(), name
    payload = json.loads((out / "promos.json").read_text(encoding="utf-8"))
    assert payload["promos"][0]["role"] == "control"


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def usage(self):
        return {"model": "fake/fake", "calls": self.calls}

    def json(self, system, user, schema):
        self.calls += 1
        name = schema.__name__
        if name == "Bible":
            return schema(premise="A fired dishwasher is secretly an heir.", protagonist="Maya", characters=[], aliases=[])
        if name == "EpisodeTags":
            ids = [int(x) for x in re.findall(r"\[b(\d+)\]", user)]
            return schema(hooks=[{"beat": ids[1], "hook_type": "humiliation", "strength": 5}, {"beat": 999, "strength": 3}],
                          cliffhangers=[{"beat": ids[-2], "strength": 4}], turning_points=[ids[1]])
        if name == "Verdicts":
            letters = [line.split()[1] for line in user.splitlines() if line.startswith("CLIP ")]
            return schema(clips=[{"clip": l, "hook": 4, "cliffhanger": 4, "standalone": 4, "escalation": 3, "premise": 4,
                                  "why_it_works": "Fast humiliation then reveal."} for l in letters])
        if name == "PairChoice":
            return schema(winner="A")
        raise AssertionError(name)


def test_llm_mode_with_fake_model(tmp_path, monkeypatch):
    import promofinder.llm as llm_module
    fake = FakeLLM()
    monkeypatch.setattr(llm_module, "LLM", lambda *a, **k: fake)
    result = run(str(FIXTURE), out_root=str(tmp_path), mode="llm", config_path=None, top=3, log=lambda *_: None)
    assert result["records"]
    assert fake.calls >= 3
    assert all(r["judge"].get("judge_score") is not None for r in result["records"])
    tags = json.loads((Path(result["out_dir"]) / "episode_tags.json").read_text(encoding="utf-8"))
    assert tags["1"]["invalid_ids"] == 1


def test_merge_flags_keeps_highest_severity():
    from promofinder.export import merge_flags
    merged = merge_flags(["violence:low", "sexual:high"], ["violence", "minor_in_danger", ""])
    assert merged == ["sexual:high", "minor:medium", "violence:medium"]


def test_baseline_check_catches_bad_timestamps():
    from promofinder.baseline import RawPromo, check
    show = load_show(str(FIXTURE))
    from promofinder.names import apply_names
    apply_names(show)
    gates = load_config(None)["gates"]
    episode = show.by_ep[1]
    good = RawPromo(start="00:03.00", end="00:31.00", hook="Who burned the sauce?!", cliffhanger="He swore he would never see me again.")
    assert check(good, episode, gates) == []
    bad = RawPromo(start="00:10.00", end="01:30.00", hook="Who burned the sauce?!", cliffhanger="nothing like this")
    issues = check(bad, episode, gates)
    assert any("duration" in i for i in issues)
    assert any("ends after" in i for i in issues)
    assert any("splits a line" in i for i in issues)


def test_pick_control_prefers_early_safe_clip():
    from promofinder.models import Candidate, Segment
    from promofinder.rank import pick_control
    cfg = {"selection": {"control_max_position": 0.2}}
    late = Candidate(cid="late", kind="single", segments=[Segment(24, 0, 30)], hook_uid="", cliff_uid="", features={"series_position": 0.47})
    risky = Candidate(cid="risky", kind="single", segments=[Segment(3, 0, 30)], hook_uid="", cliff_uid="", features={"series_position": 0.04}, policy=["gore:medium"])
    safe = Candidate(cid="safe", kind="single", segments=[Segment(1, 0, 30)], hook_uid="", cliff_uid="", features={"series_position": 0.0})
    ordered = pick_control([late, risky, safe], cfg)
    assert [c.cid for c in ordered] == ["safe", "late", "risky"]


def test_merge_verdicts_is_conservative():
    from promofinder.judge import ClipVerdict, merge_verdicts
    a = ClipVerdict(clip="A", hook=5, cliffhanger=4, standalone=4, escalation=5, premise=5, spoiler_level="minor", unexplained_refs=["the ring", "Gerald"], policy_flags=["violence"])
    b = ClipVerdict(clip="A", hook=3, cliffhanger=4, standalone=2, escalation=5, premise=5, spoiler_level="major", unexplained_refs=["Gerald"], policy_flags=["weapon"])
    m = merge_verdicts([a, b])
    assert m.hook == 4 and m.standalone == 3
    assert m.spoiler_level == "major"
    assert m.unexplained_refs == ["Gerald"]
    assert m.policy_flags == ["violence", "weapon"]
    assert m.judge_spread == 2
    assert m.standalone_min == 2


def test_one_per_scene_blocks_back_to_back_clips():
    from promofinder.models import Candidate, Segment
    from promofinder.rank import select
    cfg = {"selection": {"top": 5, "pool": 10, "mmr_lambda": 0.75, "max_overlap": 0.35, "max_per_episode": 3, "one_per_scene": True}}
    def make(cid, start, end, scenes, score):
        c = Candidate(cid=cid, kind="single", segments=[Segment(1, start, end)], hook_uid=cid, cliff_uid=cid, features={"first_episode": 1, "scenes": scenes}, score=score)
        return c
    a = make("a", 39.0, 90.8, ["1-2"], 0.9)
    b = make("b", 89.5, 133.8, ["1-2"], 0.8)
    c = make("c", 140.0, 170.0, ["1-3"], 0.7)
    assert [x.cid for x in select([a, b, c], cfg)] == ["a", "c"]


def test_verdict_store_round_trip(tmp_path):
    from promofinder.judge import ClipVerdict, VerdictStore
    from promofinder.models import Candidate, Segment
    c = Candidate(cid="x", kind="single", segments=[Segment(3, 84.0, 135.5)], hook_uid="", cliff_uid="")
    store = VerdictStore(str(tmp_path / "llm"), "nvidia/some/model")
    store.put(c, ClipVerdict(clip="B", hook=5, cliffhanger=4, standalone=4, escalation=5, premise=5))
    again = VerdictStore(str(tmp_path / "llm"), "nvidia/some/model")
    assert again.get(c).standalone == 4


def _variants():
    import re
    base = (FIXTURE / "episode-001.txt").read_text(encoding="utf-8")

    def hms(text):
        return re.sub(r"\((\d{2}):(\d{2})\.(\d{2})\)", r"(00:\1:\2.\3)", text)

    def no_bold(text):
        return re.sub(r"^\*\*(.+?):\*\*\s*$", r"\1:", text, flags=re.M)

    def bare_range(text):
        return re.sub(r"Start: \((.+?)\) \| End: \((.+?)\)", r"[\1 - \2]", text)

    def srt(text):
        return re.sub(r"Start: \((\d{2}):(\d{2})\.(\d{2})\) \| End: \((\d{2}):(\d{2})\.(\d{2})\)", r"00:\1:\2,\g<3>0 --> 00:\4:\5,\g<6>0", text)

    def inline(text):
        return re.sub(r"^(\*\*.+?:\*\*)\s*\n(Start: .+?)\n(.+)$", r"\1 \2 \3", text, flags=re.M)

    return base, {
        "crlf": base.replace("\n", "\r\n"),
        "hh_mm_ss": hms(base),
        "no_bold": no_bold(base),
        "bare_range": bare_range(base),
        "srt_arrows": srt(base),
        "all_on_one_line": inline(base),
        "no_bold_bare_range": bare_range(no_bold(base)),
    }


def test_parser_tolerates_format_variants():
    from promofinder.parse import parse_text
    base, variants = _variants()
    ref = parse_text(base, "episode-001.txt")
    expected = [(b.kind, round(b.start, 2), round(b.end, 2), b.text) for b in ref.beats]
    assert len(expected) > 10
    for name, text in variants.items():
        got = parse_text(text, "episode-001.txt")
        assert [(b.kind, round(b.start, 2), round(b.end, 2), b.text) for b in got.beats] == expected, name


def test_parse_time_formats():
    from promofinder.parse import parse_time
    assert parse_time("01:23.45") == 83.45
    assert parse_time("00:01:23.45") == 83.45
    assert parse_time("00:01:23,450") == 83.45
    assert parse_time("1:05:00") == 3900.0
    assert parse_time("no time") is None


def test_offline_run_without_camera_lines(tmp_path):
    src = tmp_path / "show"
    src.mkdir()
    for path in FIXTURE.glob("*.txt"):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"\*\*CAMERA:\*\*\nStart: .+\n.+\n", "", text)
        assert "CAMERA" not in text
        (src / path.name).write_text(text, encoding="utf-8")
    result = run(str(src), out_root=str(tmp_path / "out"), mode="offline", log=lambda *a: None)
    assert result["records"]
    for r in result["records"]:
        assert 20 <= r["duration"] <= 60


def test_episodes_without_numbers_are_numbered_by_file_order(tmp_path):
    from promofinder.doctor import check_input
    for i, path in enumerate(sorted(FIXTURE.glob("*.txt")), 1):
        text = re.sub(r"^EPISODE NUMBER:.*\n", "", path.read_text(encoding="utf-8"), flags=re.M)
        (tmp_path / f"part_{'ab'[i - 1]}.txt").write_text(text, encoding="utf-8")
    show = load_show(str(tmp_path))
    assert [e.ep for e in show.episodes] == [1, 2]
    assert len(show.beats) == sum(len(e.beats) for e in show.episodes)
    report = check_input(str(tmp_path))
    assert report["ok"] and any("file order" in w for w in report["warnings"])


def test_episode_cap_scales_for_small_shows():
    from promofinder.models import Candidate, Segment
    from promofinder.rank import select
    cfg = {"selection": {"top": 6, "pool": 50, "mmr_lambda": 0.75, "max_overlap": 0.35, "max_per_episode": 2}}
    cands = [Candidate(cid=str(i), kind="single", segments=[Segment(1, i * 30.0, i * 30.0 + 25)], hook_uid=str(i), cliff_uid=str(i), features={"first_episode": 1}, score=1 - i / 100) for i in range(8)]
    assert len(select(cands, cfg)) == 6


def test_craft_check_flags_weak_openings_and_tails():
    from promofinder.models import Candidate, Segment
    from promofinder.rank import craft_check
    def clip(length, **f):
        return Candidate(cid="x", kind="single", segments=[Segment(1, 0, length)], hook_uid="", cliff_uid="", features=f)
    good = clip(40, first_line_at=0.2, opening_words=9, hook_kind="DIALOGUE", talk_tail=1.0)
    late = clip(30, first_line_at=9.0, opening_words=0, hook_kind="ACTION", talk_tail=1.0)
    thin = clip(30, first_line_at=0.1, opening_words=1, hook_kind="DIALOGUE", talk_tail=1.0)
    visual = clip(30, first_line_at=1.5, opening_words=2, hook_kind="ACTION", talk_tail=1.0)
    tail = clip(58, first_line_at=0.1, opening_words=9, hook_kind="DIALOGUE", talk_tail=12.0)
    assert craft_check(good, {}) == {}
    assert "no line in first 3s" in craft_check(late, {})
    assert "thin opening line" in craft_check(thin, {})
    assert craft_check(visual, {}) == {}
    assert set(craft_check(tail, {})) == {"silent tail after last line", "long for a promo"}


class DeadLLM(FakeLLM):
    def __init__(self):
        super().__init__()
        self.dead = None

    def json(self, system, user, schema):
        from promofinder.llm import LLMAuthError
        self.dead = LLMAuthError("nvidia rejected the API key (HTTP 401).")
        raise self.dead


def test_dead_model_still_returns_valid_promos(tmp_path, monkeypatch):
    from promofinder import llm as llm_module
    from promofinder.evaluate import load_run, validity
    monkeypatch.setattr(llm_module, "LLM", lambda *a, **k: DeadLLM())
    result = run(str(FIXTURE), out_root=str(tmp_path), mode="llm", top=3, log=lambda *_: None)
    assert result["records"]
    assert result["meta"]["degraded"]
    report = validity(load_run(result["out_dir"]), str(FIXTURE), None)
    assert report["all_valid"], report["issues"]


def test_missing_key_falls_back_to_rules(tmp_path, monkeypatch):
    from promofinder import llm as llm_module

    def broken(*a, **k):
        raise llm_module.LLMError("Missing API key: set NVIDIA_API_KEY")

    monkeypatch.setattr(llm_module, "LLM", broken)
    result = run(str(FIXTURE), out_root=str(tmp_path), mode="llm", top=3, log=lambda *_: None)
    assert result["meta"]["mode"] == "offline"
    assert result["meta"]["degraded"][0]["stage"] == "model"
    assert result["records"]


def test_profiles_change_the_budget():
    from promofinder.profiles import apply_profile
    cfg = apply_profile(load_config(None), "fast")
    assert cfg["llm"]["judge_repeats"] == 1 and cfg["llm"]["jury_model"] == "" and cfg["skip_bible"]
    assert apply_profile(load_config(None), None)["llm"]["judge_repeats"] == load_config(None)["llm"]["judge_repeats"]


def test_stored_verdicts_do_not_depend_on_batch_mates(tmp_path):
    from promofinder.candidates import generate
    from promofinder.features import featurize, gates_pass
    from promofinder.judge import judge_repeated
    from promofinder.rules import score_beats

    show = load_show(str(FIXTURE))
    priors = score_beats(show)
    clips = []
    for c in generate(show, priors, load_config(None)):
        featurize(c, show, priors)
        if gates_pass(c, load_config(None)):
            clips.append(c)
    clips = clips[:8]
    assert len(clips) >= 6

    class CountingJudge(FakeLLM):
        spec = "fake/judge"

        def json(self, system, user, schema, **kwargs):
            out = super().json(system, user, schema)
            for v in out.clips:
                v.hook = 1 + (self.calls % 5)
            return out

    judge = CountingJudge()
    cfg = load_config(None)
    cfg["llm"]["cache_dir"] = str(tmp_path / "llm")
    cfg["llm"]["judge_repeats"] = 1
    first = judge_repeated(show, clips[:5], judge, cfg, seed=1)
    calls = judge.calls
    second = judge_repeated(show, clips[2:8], judge, cfg, seed=99)
    assert judge.calls > calls
    for c in clips[2:5]:
        assert first[c.cid].hook == second[c.cid].hook
