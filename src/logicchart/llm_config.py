from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGICCHART_ENV_FILENAME = ".env.logicchart"
LOGICCHART_LLM_KEYS = (
    "LOGICCHART_LLM_PROVIDER",
    "LOGICCHART_LLM_MODEL",
    "LOGICCHART_LLM_BASE_URL",
    "LOGICCHART_LLM_API_FORMAT",
    "LOGICCHART_LLM_API_KEY",
)


@dataclass(frozen=True)
class LlmProvider:
    id: str
    name: str
    region: str
    api_format: str
    base_url: str
    default_model: str
    models: tuple[str, ...]
    notes: str
    key_hint: str
    preferred: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region,
            "api_format": self.api_format,
            "base_url": self.base_url,
            "default_model": self.default_model,
            "models": list(self.models),
            "notes": self.notes,
            "key_hint": self.key_hint,
            "preferred": self.preferred,
        }


PROVIDERS: tuple[LlmProvider, ...] = (
    LlmProvider(
        id="deepseek",
        name="DeepSeek",
        region="China",
        api_format="openai-compatible",
        base_url="https://api.deepseek.com",
        default_model="deepseek-v4-pro",
        models=("deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"),
        notes=(
            "Preferred LogicChart default. deepseek-chat and deepseek-reasoner are legacy "
            "aliases for DeepSeek v4 flash modes and may be retired by the provider."
        ),
        key_hint="DeepSeek API key",
        preferred=True,
    ),
    LlmProvider(
        id="openai",
        name="OpenAI",
        region="United States",
        api_format="openai",
        base_url="https://api.openai.com/v1",
        default_model="gpt-5.5",
        models=("gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"),
        notes="Use a smaller GPT-5.4 variant when latency or cost is more important.",
        key_hint="OpenAI API key",
    ),
    LlmProvider(
        id="anthropic",
        name="Anthropic",
        region="United States",
        api_format="anthropic",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-6",
        models=(
            "claude-fable-5",
            "claude-opus-4-8",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ),
        notes="Sonnet is the balanced default; Opus and Fable target harder reasoning.",
        key_hint="Anthropic API key",
    ),
    LlmProvider(
        id="google",
        name="Google Gemini",
        region="United States",
        api_format="google",
        base_url="https://generativelanguage.googleapis.com",
        default_model="gemini-3.1-pro",
        models=("gemini-3.1-pro", "gemini-3.5-flash", "gemini-3-flash", "gemini-2.5-pro"),
        notes="Gemini model ids can vary by endpoint; custom model override is supported.",
        key_hint="Google AI API key",
    ),
    LlmProvider(
        id="xai",
        name="xAI",
        region="United States",
        api_format="openai-compatible",
        base_url="https://api.x.ai/v1",
        default_model="grok-4.3",
        models=("grok-4.3", "grok-build-0.1"),
        notes="Grok Build is the coding-focused preset; Grok 4.3 is the general default.",
        key_hint="xAI API key",
    ),
    LlmProvider(
        id="qwen",
        name="Alibaba Qwen",
        region="China",
        api_format="openai-compatible",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3-max",
        models=(
            "qwen3-max",
            "qwen3.5-plus",
            "qwen3.5-flash",
            "qwen3-coder-plus",
            "qwen-plus",
            "qwen-flash",
        ),
        notes="Alibaba Model Studio offers region-specific catalogs and endpoints.",
        key_hint="DashScope API key",
    ),
    LlmProvider(
        id="zai",
        name="Z.AI",
        region="China",
        api_format="openai-compatible",
        base_url="https://api.z.ai/api/paas/v4",
        default_model="glm-5.2",
        models=("glm-5.2",),
        notes="Z.AI exposes OpenAI-compatible chat completion examples for GLM models.",
        key_hint="Z.AI API key",
    ),
    LlmProvider(
        id="kimi",
        name="Kimi / Moonshot",
        region="China",
        api_format="openai-compatible",
        base_url="https://api.moonshot.ai/v1",
        default_model="kimi-k2.7-code",
        models=(
            "kimi-k2.7-code",
            "kimi-k2.6",
            "kimi-k2.5",
            "moonshot-v1",
        ),
        notes="Kimi k2.7 code is the coding-focused default from the chat API docs.",
        key_hint="Moonshot API key",
    ),
    LlmProvider(
        id="mistral",
        name="Mistral AI",
        region="Europe",
        api_format="mistral",
        base_url="https://api.mistral.ai/v1",
        default_model="mistral-medium-3.5",
        models=(
            "mistral-medium-3.5",
            "mistral-small-4",
            "mistral-large-3",
            "devstral-2",
        ),
        notes="Included as a major non-US/non-China preset with coding-oriented options.",
        key_hint="Mistral API key",
    ),
)


def providers_by_id() -> dict[str, LlmProvider]:
    return {provider.id: provider for provider in PROVIDERS}


def get_provider(provider_id: str) -> LlmProvider:
    provider = providers_by_id().get(provider_id)
    if provider is None:
        supported = ", ".join(provider.id for provider in PROVIDERS)
        raise ValueError(f"unknown LLM provider {provider_id!r}; supported providers: {supported}")
    return provider


def logicchart_env_path(root: Path, env_file: str | None = None) -> Path:
    path = Path(env_file) if env_file else Path(LOGICCHART_ENV_FILENAME)
    if path.is_absolute():
        return path
    return root / path


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _unquote_env_value(value.strip())
    return values


def write_logicchart_env(
    path: Path,
    *,
    provider: LlmProvider,
    model: str,
    api_key: str,
    base_url: str | None = None,
) -> dict[str, str]:
    values = {
        "LOGICCHART_LLM_PROVIDER": provider.id,
        "LOGICCHART_LLM_MODEL": model,
        "LOGICCHART_LLM_BASE_URL": base_url or provider.base_url,
        "LOGICCHART_LLM_API_FORMAT": provider.api_format,
        "LOGICCHART_LLM_API_KEY": api_key,
    }
    _write_env_values(path, values)
    return values


def read_logicchart_env(path: Path) -> dict[str, str]:
    values = parse_env_file(path)
    return {key: value for key, value in values.items() if key in LOGICCHART_LLM_KEYS}


def render_providers_text() -> str:
    lines = ["Optional LLM providers (setup only; LogicChart never needs an LLM for correctness):"]
    for provider in PROVIDERS:
        marker = " [preferred]" if provider.preferred else ""
        lines.append(f"- {provider.id}{marker}: {provider.name} ({provider.region})")
        lines.append(f"  default model: {provider.default_model}")
        lines.append(f"  models: {', '.join(provider.models)}")
        lines.append(f"  base URL: {provider.base_url}")
        lines.append(f"  note: {provider.notes}")
    return "\n".join(lines)


def render_setup_text(path: Path, values: dict[str, str]) -> str:
    safe_values = {
        key: ("<set>" if key.endswith("_API_KEY") else value) for key, value in values.items()
    }
    return "\n".join(
        [
            f"Wrote LogicChart LLM config: {path}",
            f"provider: {safe_values['LOGICCHART_LLM_PROVIDER']}",
            f"model: {safe_values['LOGICCHART_LLM_MODEL']}",
            f"base_url: {safe_values['LOGICCHART_LLM_BASE_URL']}",
            "api_key: <set>",
            "No provider call was made. Enrichment remains opt-in.",
        ]
    )


def render_current_config(path: Path) -> str:
    values = read_logicchart_env(path)
    if not values:
        return f"No LogicChart LLM config found at {path}."

    lines = [f"LogicChart LLM config: {path}"]
    for key in LOGICCHART_LLM_KEYS:
        if key not in values:
            continue
        value = "<set>" if key.endswith("_API_KEY") else values[key]
        lines.append(f"- {key}={value}")
    return "\n".join(lines)


def config_to_json(path: Path) -> dict[str, Any]:
    values = read_logicchart_env(path)
    masked = {
        key: ("<set>" if key.endswith("_API_KEY") and value else value)
        for key, value in values.items()
    }
    return {
        "env_file": str(path),
        "configured": bool(values),
        "values": masked,
    }


def _write_env_values(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    if not existing_lines:
        output.extend(
            [
                "# LogicChart optional LLM enrichment config.",
                "# This file is local-only and should not be committed.",
            ]
        )

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in values:
            output.append(f"{key}={_quote_env_value(values[key])}")
            seen.add(key)
        else:
            output.append(line)

    if output and output[-1] != "":
        output.append("")
    for key in LOGICCHART_LLM_KEYS:
        if key in seen:
            continue
        output.append(f"{key}={_quote_env_value(values[key])}")

    path.write_text("\n".join(output) + "\n", encoding="utf-8")
    with suppress(OSError):
        os.chmod(path, 0o600)


def _quote_env_value(value: str) -> str:
    if value == "" or any(char.isspace() or char in "#'\"" for char in value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
        return value.replace('\\"', '"').replace("\\\\", "\\")
    return value
