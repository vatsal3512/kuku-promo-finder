from pathlib import Path

import pytest

from promofinder.doctor import check_input
from promofinder.evaluate import load_run, validity
from promofinder.names import apply_names
from promofinder.parse import load_show, parse_time
from promofinder.pipeline import run

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample_show" / "episode-001.txt"


def quiet(*_):
    return None


@pytest.mark.parametrize("name,episodes,beats", [("office_combined", 3, 59), ("family_hinglish", 2, 37), ("sample_show", 2, 50)])
def test_other_shows_parse_and_give_valid_promos(tmp_path, name, episodes, beats):
    show = load_show(str(FIXTURES / name))
    assert len(show.episodes) == episodes
    assert len(show.beats) == beats
    result = run(str(FIXTURES / name), out_root=str(tmp_path), mode="offline", log=quiet)
    assert result["records"]
    report = validity(load_run(result["out_dir"]), str(FIXTURES / name))
    assert report["all_valid"], report["issues"]


def test_one_file_with_many_episodes_is_split():
    show = load_show(str(FIXTURES / "office_combined"))
    assert [e.ep for e in show.episodes] == [1, 2, 3]
    assert all(e.duration > 50 for e in show.episodes)


def test_non_latin_speakers_are_kept():
    show = load_show(str(FIXTURES / "family_hinglish"))
    apply_names(show, None)
    labels = {b.label for e in show.episodes for b in e.beats if b.kind == "DIALOGUE"}
    assert "PRIYA" in labels
    assert any(not label.isascii() for label in labels)


def test_seconds_and_srt_times():
    assert parse_time("12.5s") == 12.5
    assert parse_time("7 sec") == 7.0
    assert parse_time("00:01:02,500") == 62.5


def test_utf16_file_reads_the_same(tmp_path):
    (tmp_path / "episode-001.txt").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-16")
    plain = load_show(str(SAMPLE))
    wide = load_show(str(tmp_path))
    assert [(b.kind, b.start, b.text) for b in wide.beats.values()] == [(b.kind, b.start, b.text) for b in plain.beats.values()]


def test_broken_inputs_never_crash(tmp_path):
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("Just some notes with no timestamps at all.\nNothing to parse here.", encoding="utf-8")
    (tmp_path / "short.txt").write_text("EPISODE NUMBER: Episode 9\n\n**ANA:**\nStart: (00:00.00) | End: (00:04.00)\n\"Hi.\"\n", encoding="utf-8")
    (tmp_path / "shuffled.txt").write_text(
        "EPISODE NUMBER: Episode 10\n\n**BEN:**\nStart: (00:20.00) | End: (00:18.00)\n\"Backwards.\"\n\n"
        "**ANA:**\nStart: (00:02.00) | End: (00:04.00)\n\"First.\"\n",
        encoding="utf-8",
    )
    report = check_input(str(tmp_path))
    assert report["ok"]
    assert any("no timed beats" in w for w in report["warnings"])
    assert any("too short" in w for w in report["warnings"])
    result = run(str(tmp_path), out_root=str(tmp_path / "out"), mode="offline", log=quiet)
    assert result["records"] == []


def test_folder_with_nothing_usable_explains_itself(tmp_path):
    (tmp_path / "readme.txt").write_text("no script here", encoding="utf-8")
    report = check_input(str(tmp_path))
    assert not report["ok"]
    with pytest.raises(SystemExit):
        run(str(tmp_path), out_root=str(tmp_path / "out"), mode="offline", log=quiet)
