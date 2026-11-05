import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from pydantic import BaseModel, ValidationError

PROVIDERS = {
    "nvidia": ("https://integrate.api.nvidia.com/v1", ["NVIDIA_API_KEY"]),
    "groq": ("https://api.groq.com/openai/v1", ["GROQ_API_KEY"]),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", ["GEMINI_API_KEY", "GOOGLE_API_KEY"]),
    "openrouter": ("https://openrouter.ai/api/v1", ["OPENROUTER_API_KEY"]),
    "openai": ("https://api.openai.com/v1", ["OPENAI_API_KEY"]),
    "anthropic": ("https://api.anthropic.com/v1/", ["ANTHROPIC_API_KEY"]),
    "together": ("https://api.together.xyz/v1", ["TOGETHER_API_KEY"]),
    "mistral": ("https://api.mistral.ai/v1", ["MISTRAL_API_KEY"]),
    "deepseek": ("https://api.deepseek.com/v1", ["DEEPSEEK_API_KEY"]),
    "ollama": ("http://localhost:11434/v1", []),
    "custom": (None, ["PROMO_LLM_API_KEY"]),
}
JSON_MODE = {"groq", "gemini", "openai", "openrouter", "together", "mistral", "deepseek"}


class LLMError(RuntimeError):
    pass


class LLMAuthError(LLMError):
    pass


class LLMQuotaError(LLMError):
    pass


class LLMNotFound(LLMError):
    pass


class LLMRefusal(LLMError):
    pass


class LLMContextError(LLMError):
    pass


REFUSAL_RE = re.compile(r"^\s*(i'?m sorry|i am sorry|i can(no|')t|i am unable|i'm unable|i won'?t|as an ai)", re.I)
QUOTA_RE = re.compile(r"insufficient[_ ]quota|credit|billing|payment required|exceeded your current quota", re.I)
CONTEXT_RE = re.compile(r"context length|context window|maximum context|too many tokens|prompt is too long|reduce the length", re.I)


def load_env_file(path: Path = Path(".env")):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def extract_json(text: str):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"^.*?</think>", "", text, flags=re.S).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    return json.loads(text)


def key_pool(names: list[str]) -> list[str]:
    found = []
    for name in names:
        for env in [name] + [f"{name}{i}" for i in range(2, 10)]:
            value = os.environ.get(env)
            if value and value not in found:
                found.append(value)
    return found


class LLM:
    def __init__(self, spec: str, cfg: dict | None = None):
        cfg = cfg or {}
        load_env_file()
        if "/" not in spec:
            raise LLMError(f"Model must look like provider/model, got {spec!r}")
        self.provider, self.model = spec.split("/", 1)
        if self.provider not in PROVIDERS:
            raise LLMError(f"Unknown provider {self.provider!r}. Known: {', '.join(PROVIDERS)}")
        base_url, keys = PROVIDERS[self.provider]
        if self.provider == "custom":
            base_url = os.environ.get("PROMO_LLM_BASE_URL")
            if not base_url:
                raise LLMError("Set PROMO_LLM_BASE_URL for the custom provider")
        pool = key_pool(keys)
        if keys and not pool:
            raise LLMError(f"Missing API key: set {' or '.join(keys)}")
        from openai import OpenAI
        self.clients = [OpenAI(base_url=base_url, api_key=k, max_retries=0, timeout=cfg.get("timeout", 240)) for k in pool or ["none"]]
        self.client = self.clients[0]
        self.turn = 0
        self.spec = spec
        self.temperature = cfg.get("temperature", 0.2)
        self.max_tokens = cfg.get("max_tokens", 4000)
        self.cache_dir = Path(cfg.get("cache_dir", ".cache/llm"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.max_timeouts = int(cfg.get("max_timeouts", 2))
        self.key_names = keys
        self.bad_keys: set[int] = set()
        self.dead: LLMError | None = None
        self.stats = {"keys": len(self.clients), "rate_limited": 0, "calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0, "failures": 0}

    def usage(self) -> dict:
        return {"model": self.spec, **{k: round(v, 2) if isinstance(v, float) else v for k, v in self.stats.items()}}

    def describe_error_mix(self) -> str:
        errors = self.stats.get("errors", {})
        return ", ".join(f"{k}: {v}" for k, v in sorted(errors.items())) or "none"

    def _key(self, system: str, user: str, extra: dict | None = None) -> Path:
        tail = f"|{json.dumps(extra, sort_keys=True)}" if extra else ""
        digest = hashlib.sha256(f"{self.spec}|{self.temperature}|{system}|{user}{tail}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _call(self, system: str, user: str, extra: dict | None = None) -> str:
        kwargs = dict(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if self.provider in JSON_MODE:
            kwargs["response_format"] = {"type": "json_object"}
        if extra:
            kwargs["extra_body"] = dict(extra)
        if self.dead:
            raise self.dead
        delay = 4.0
        with self.lock:
            index = self.turn % len(self.clients)
            self.turn += 1
            while index in self.bad_keys and len(self.bad_keys) < len(self.clients):
                index = (index + 1) % len(self.clients)
        tries = 6 * len(self.clients)
        timeouts = 0
        for attempt in range(tries):
            started = time.time()
            try:
                response = self.clients[index].chat.completions.create(**kwargs)
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                message = str(exc)
                fatal = self._fatal(status, message)
                if fatal is not None:
                    with self.lock:
                        self.bad_keys.add(index)
                        self.stats.setdefault("errors", {})
                        self.stats["errors"][type(fatal).__name__] = self.stats["errors"].get(type(fatal).__name__, 0) + 1
                        if isinstance(fatal, LLMNotFound) or len(self.bad_keys) >= len(self.clients):
                            self.dead = fatal
                    if self.dead:
                        raise fatal from exc
                    index = next(i for i in range(len(self.clients)) if i not in self.bad_keys)
                    continue
                if status in (400, 413, 422) and CONTEXT_RE.search(message):
                    raise LLMContextError(f"Prompt too long for {self.spec}") from exc
                if status in (400, 422) and "extra_body" in kwargs:
                    kwargs.pop("extra_body")
                    continue
                if status == 400 and "temperature" in message.lower() and "temperature" in kwargs:
                    kwargs.pop("temperature")
                    continue
                if status == 400 and "max_tokens" in message and "max_tokens" in kwargs:
                    kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                    continue
                if status == 400 and "system" in message.lower() and kwargs["messages"][0]["role"] == "system":
                    kwargs["messages"] = [{"role": "user", "content": system + "\n\n" + user}]
                    continue
                transient = status in (429, 500, 502, 503, 504) or status is None
                if "Timeout" in type(exc).__name__:
                    timeouts += 1
                    if timeouts > self.max_timeouts:
                        with self.lock:
                            self.stats.setdefault("errors", {})
                            self.stats["errors"]["timeout_gave_up"] = self.stats["errors"].get("timeout_gave_up", 0) + 1
                        raise LLMError(f"Timed out {timeouts} times") from exc
                if transient or "rate" in str(exc).lower():
                    with self.lock:
                        self.stats["rate_limited"] += 1
                        kind = str(status) if status else type(exc).__name__
                        self.stats.setdefault("errors", {})
                        self.stats["errors"][kind] = self.stats["errors"].get(kind, 0) + 1
                    index = (index + 1) % len(self.clients)
                    if len(self.clients) > 1 and (attempt + 1) % len(self.clients):
                        continue
                    retry_after = None
                    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
                    if headers.get("retry-after"):
                        try:
                            retry_after = float(headers["retry-after"])
                        except ValueError:
                            retry_after = None
                    time.sleep(min(90.0, retry_after or delay))
                    delay *= 2
                    continue
                if status == 400 and "response_format" in kwargs:
                    kwargs.pop("response_format")
                    continue
                raise LLMError(str(exc)) from exc
            usage = getattr(response, "usage", None)
            with self.lock:
                self.stats["seconds"] += time.time() - started
                self.stats["calls"] += 1
                if usage:
                    self.stats["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
                    self.stats["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
            choice = response.choices[0]
            content = choice.message.content or ""
            if getattr(choice, "finish_reason", None) == "content_filter" or (not content.strip() and getattr(choice, "finish_reason", None) != "length"):
                with self.lock:
                    self.stats["refusals"] = self.stats.get("refusals", 0) + 1
                raise LLMRefusal(f"{self.spec} returned no content (finish reason: {getattr(choice, 'finish_reason', None)})")
            if getattr(choice, "finish_reason", None) == "length":
                with self.lock:
                    self.stats["truncated"] = self.stats.get("truncated", 0) + 1
            return content
        raise LLMError("Gave up after repeated rate limits")

    def _fatal(self, status, message: str) -> LLMError | None:
        names = " or ".join(self.key_names) or "the API key"
        if status in (401, 403):
            return LLMAuthError(f"{self.provider} rejected the API key (HTTP {status}). Check {names}.")
        if status == 402 or (status == 429 and QUOTA_RE.search(message)):
            return LLMQuotaError(f"{self.provider} says the account has no credit or quota left (HTTP {status}).")
        if status == 404:
            return LLMNotFound(f"Model {self.model!r} was not found on {self.provider} (HTTP 404). Check the model name.")
        return None

    def json(self, system: str, user: str, schema: type[BaseModel], retries: int = 2, extra: dict | None = None) -> BaseModel:
        path = self._key(system, user, extra)
        if path.exists():
            try:
                with self.lock:
                    self.stats["cache_hits"] += 1
                return schema.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except (ValidationError, json.JSONDecodeError):
                path.unlink(missing_ok=True)
        prompt = user
        last_error = None
        for _ in range(retries + 1):
            raw = self._call(system, prompt, extra)
            if "{" not in raw and "[" not in raw and REFUSAL_RE.search(raw):
                with self.lock:
                    self.stats["refusals"] = self.stats.get("refusals", 0) + 1
                raise LLMRefusal(f"{self.spec} declined: {raw.strip()[:120]}")
            try:
                parsed = schema.model_validate(extract_json(raw))
                path.write_text(parsed.model_dump_json(), encoding="utf-8")
                return parsed
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                prompt = f"{user}\n\nYour previous reply was not valid JSON for the schema ({str(exc)[:300]}). Reply with JSON only."
        with self.lock:
            self.stats["failures"] += 1
        raise LLMError(f"Invalid JSON after retries: {last_error}")
