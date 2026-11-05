from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from promofinder.llm import LLM, LLMAuthError, LLMNotFound, LLMQuotaError, LLMRefusal


class Answer(BaseModel):
    ok: bool


class ApiError(Exception):
    def __init__(self, status, message="error"):
        super().__init__(message)
        self.status_code = status


def reply(content, finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)], usage=None)


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_llm(monkeypatch, tmp_path, *clients):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    llm = LLM("nvidia/some-model", {"cache_dir": str(tmp_path)})
    llm.clients = list(clients)
    return llm


def test_bad_key_fails_fast_and_stays_dead(monkeypatch, tmp_path):
    client = FakeClient([ApiError(401)])
    llm = make_llm(monkeypatch, tmp_path, client)
    with pytest.raises(LLMAuthError):
        llm.json("s", "u1", Answer)
    with pytest.raises(LLMAuthError):
        llm.json("s", "u2", Answer)
    assert len(client.calls) == 1


def test_one_bad_key_falls_through_to_a_good_one(monkeypatch, tmp_path):
    bad = FakeClient([ApiError(401)])
    good = FakeClient([reply('{"ok": true}')])
    llm = make_llm(monkeypatch, tmp_path, bad, good)
    assert llm.json("s", "u", Answer).ok
    assert not llm.dead


def test_missing_model_and_no_credit_are_named(monkeypatch, tmp_path):
    llm = make_llm(monkeypatch, tmp_path, FakeClient([ApiError(404)]))
    with pytest.raises(LLMNotFound):
        llm.json("s", "u", Answer)
    llm = make_llm(monkeypatch, tmp_path, FakeClient([ApiError(429, "You exceeded your current quota")]))
    with pytest.raises(LLMQuotaError):
        llm.json("s", "u", Answer)


def test_refusals_are_not_scores(monkeypatch, tmp_path):
    llm = make_llm(monkeypatch, tmp_path, FakeClient([reply("I'm sorry, I can't help with violent content.")]))
    with pytest.raises(LLMRefusal):
        llm.json("s", "u", Answer)
    llm = make_llm(monkeypatch, tmp_path, FakeClient([reply("", finish="content_filter")]))
    with pytest.raises(LLMRefusal):
        llm.json("s", "u2", Answer)


def test_unsupported_parameters_are_dropped(monkeypatch, tmp_path):
    client = FakeClient([ApiError(400, "Unsupported parameter: temperature"), reply('{"ok": true}')])
    llm = make_llm(monkeypatch, tmp_path, client)
    assert llm.json("s", "u", Answer).ok
    assert "temperature" not in client.calls[-1]


def test_extra_options_get_their_own_cache_and_fall_back(monkeypatch, tmp_path):
    client = FakeClient([ApiError(400, "Unknown field chat_template_kwargs"), reply('{"ok": true}')])
    llm = make_llm(monkeypatch, tmp_path, client)
    extra = {"chat_template_kwargs": {"enable_thinking": False}}
    assert llm._key("s", "u", extra) != llm._key("s", "u")
    assert llm.json("s", "u", Answer, extra=extra).ok
    assert "extra_body" in client.calls[0] and "extra_body" not in client.calls[-1]


def test_model_replies_in_odd_shapes_are_accepted():
    from promofinder.judge import ClipVerdict
    from promofinder.tag import EpisodeTags
    tags = EpisodeTags.model_validate({"hooks": [{"beat": "b16", "strength": "4"}, {"beat": 12, "strength": 7}],
                                       "cliffhangers": [{"beat": "[b40]"}], "turning_points": ["b3", 5]})
    assert [h.beat for h in tags.hooks] == [16, 12] and tags.hooks[1].strength == 5
    assert tags.cliffhangers[0].beat == 40 and tags.turning_points == [3, 5]
    v = ClipVerdict.model_validate({"clip": "A", "hook": "4/5", "cliffhanger": "five", "standalone": "8/10", "unexplained_refs": "Gerald; the ring"})
    assert (v.hook, v.cliffhanger, v.standalone) == (4.0, 5.0, 4.0)
    assert v.unexplained_refs == ["Gerald", "the ring"]
