from __future__ import annotations

import json
import stat
from pathlib import Path

from logicchart.llm_config import (
    LOGICCHART_ENV_FILENAME,
    PROVIDERS,
    config_to_json,
    get_provider,
    logicchart_env_path,
    parse_env_file,
    read_logicchart_env,
    render_current_config,
    write_logicchart_env,
)


def test_deepseek_v4_is_the_preferred_default() -> None:
    provider = get_provider("deepseek")

    assert provider.preferred is True
    assert provider.default_model == "deepseek-v4-pro"
    assert "deepseek-v4-flash" in provider.models


def test_qwen_provider_includes_documented_coder_preset() -> None:
    provider = get_provider("qwen")

    assert provider.default_model == "qwen3-max"
    assert "qwen3-coder-plus" in provider.models


def test_logicchart_env_writer_preserves_unrelated_values_and_masks_key(tmp_path: Path) -> None:
    env_path = logicchart_env_path(tmp_path)
    env_path.write_text(
        "EXISTING=value\nLOGICCHART_LLM_PROVIDER=old\n",
        encoding="utf-8",
    )

    values = write_logicchart_env(
        env_path,
        provider=get_provider("deepseek"),
        model="deepseek-v4-flash",
        api_key="sk-test key",
    )

    parsed = parse_env_file(env_path)
    assert env_path.name == LOGICCHART_ENV_FILENAME
    assert parsed["EXISTING"] == "value"
    assert parsed["LOGICCHART_LLM_PROVIDER"] == "deepseek"
    assert parsed["LOGICCHART_LLM_MODEL"] == "deepseek-v4-flash"
    assert parsed["LOGICCHART_LLM_BASE_URL"] == "https://api.deepseek.com"
    assert parsed["LOGICCHART_LLM_API_KEY"] == "sk-test key"
    assert values["LOGICCHART_LLM_API_KEY"] == "sk-test key"

    if hasattr(stat, "S_IMODE"):
        assert stat.S_IMODE(env_path.stat().st_mode) & 0o077 == 0


def test_provider_config_helpers_do_not_print_secrets(tmp_path: Path) -> None:
    providers_payload = {
        "preferred_provider": "deepseek",
        "providers": [provider.to_dict() for provider in PROVIDERS],
    }
    assert providers_payload["preferred_provider"] == "deepseek"
    provider_ids = {provider["id"] for provider in providers_payload["providers"]}
    assert {"deepseek", "openai", "anthropic", "google", "qwen", "zai", "kimi"} <= provider_ids

    env_path = tmp_path / LOGICCHART_ENV_FILENAME
    values = write_logicchart_env(
        env_path,
        provider=get_provider("deepseek"),
        model=get_provider("deepseek").default_model,
        api_key="sk-secret-value",
    )
    setup_payload = {
        "provider": values["LOGICCHART_LLM_PROVIDER"],
        "model": values["LOGICCHART_LLM_MODEL"],
        "api_key": "<set>",
    }
    assert setup_payload["provider"] == "deepseek"
    assert setup_payload["model"] == "deepseek-v4-pro"
    assert setup_payload["api_key"] == "<set>"
    assert "sk-secret-value" not in json.dumps(setup_payload)

    stored = read_logicchart_env(env_path)
    assert stored["LOGICCHART_LLM_API_KEY"] == "sk-secret-value"

    shown = render_current_config(env_path)
    assert "LOGICCHART_LLM_API_KEY=<set>" in shown
    assert "sk-secret-value" not in shown
    assert config_to_json(env_path)["values"]["LOGICCHART_LLM_API_KEY"] == "<set>"


def test_provider_config_accepts_custom_model_and_region_endpoint(tmp_path: Path) -> None:
    values = write_logicchart_env(
        tmp_path / LOGICCHART_ENV_FILENAME,
        provider=get_provider("qwen"),
        model="qwen3-coder-plus",
        base_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
        api_key="dashscope-key",
    )
    assert values["LOGICCHART_LLM_MODEL"] == "qwen3-coder-plus"
    assert values["LOGICCHART_LLM_API_KEY"] == "dashscope-key"

    values = read_logicchart_env(tmp_path / LOGICCHART_ENV_FILENAME)
    assert values["LOGICCHART_LLM_PROVIDER"] == "qwen"
    assert values["LOGICCHART_LLM_MODEL"] == "qwen3-coder-plus"
    assert (
        values["LOGICCHART_LLM_BASE_URL"] == "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
    )
