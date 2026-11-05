import os
import re
from pathlib import Path


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


def key_pool(names: list[str]) -> list[str]:
    found = []
    for name in names:
        for env in [name] + [f"{name}{i}" for i in range(2, 10)]:
            value = os.environ.get(env)
            if value and value not in found:
                found.append(value)
    return found
