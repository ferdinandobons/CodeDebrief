# Optional LLM Provider Setup

LogicChart is deterministic and local-first. LLMs are optional enrichment providers for
human-friendly labels, summaries, and explanations; they are never required for analysis
correctness.

## Local Env File

Use the CLI to create a dedicated local env file:

```bash
printf '%s' "$DEEPSEEK_API_KEY" | logicchart llm setup --api-key-stdin
logicchart llm show
```

The default writes `.env.logicchart` in the analyzed project:

```dotenv
LOGICCHART_LLM_PROVIDER=deepseek
LOGICCHART_LLM_MODEL=deepseek-v4-pro
LOGICCHART_LLM_BASE_URL=https://api.deepseek.com
LOGICCHART_LLM_API_FORMAT=openai-compatible
LOGICCHART_LLM_API_KEY=...
```

`.env.logicchart` is ignored by git. `logicchart llm show` masks the key, and `setup`
does not make a provider request.

## Provider Presets

The presets below were checked against official provider docs on 2026-06-19. Catalogs
change often, so users can always pass `--model` and `--base-url` overrides.

| Provider | Region | Default | Other useful presets |
|---|---:|---|---|
| DeepSeek | China | `deepseek-v4-pro` | `deepseek-v4-flash`, legacy `deepseek-chat`, `deepseek-reasoner` |
| OpenAI | United States | `gpt-5.5` | `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano` |
| Anthropic | United States | `claude-sonnet-4-6` | `claude-fable-5`, `claude-opus-4-8`, `claude-haiku-4-5` |
| Google Gemini | United States | `gemini-3.1-pro` | `gemini-3.5-flash`, `gemini-3-flash`, `gemini-2.5-pro` |
| xAI | United States | `grok-4.3` | `grok-build-0.1` |
| Alibaba Qwen | China | `qwen3-max` | `qwen3.5-plus`, `qwen3.5-flash`, `qwen3-coder-plus`, `qwen-plus` |
| Z.AI | China | `glm-5.2` | custom GLM model ids supported through `--model` |
| Kimi / Moonshot | China | `kimi-k2.7-code` | `kimi-k2.6`, `kimi-k2.5`, `moonshot-v1` |
| Mistral AI | Europe | `mistral-medium-3.5` | `mistral-small-4`, `mistral-large-3`, `devstral-2` |

Official references:

- [DeepSeek API models](https://api-docs.deepseek.com/quick_start/pricing)
- [OpenAI model docs](https://platform.openai.com/docs/models)
- [Anthropic Claude model overview](https://docs.anthropic.com/en/docs/about-claude/models/overview)
- [Google Gemini models](https://ai.google.dev/gemini-api/docs/models)
- [xAI models](https://docs.x.ai/developers/models)
- [Alibaba Model Studio model list](https://www.alibabacloud.com/help/en/model-studio/models)
- [Alibaba OpenAI-compatible Qwen API](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)
- [Z.AI API introduction](https://docs.z.ai/api-reference/introduction)
- [Kimi chat completion API](https://platform.kimi.ai/docs/api/chat)
- [Mistral models overview](https://docs.mistral.ai/models/overview)

## Region Overrides

Some providers expose different endpoints by region. For example, Alibaba Model Studio
supports region-specific OpenAI-compatible endpoints:

```bash
printf '%s' "$DASHSCOPE_API_KEY" | logicchart llm setup \
  --provider qwen \
  --model qwen3-coder-plus \
  --base-url https://dashscope-us.aliyuncs.com/compatible-mode/v1 \
  --api-key-stdin
```

## Guardrails

- Do not commit `.env.logicchart`.
- Use `--api-key-stdin` instead of `--api-key` when working in a shared shell history.
- Running `logicchart llm setup` only stores local configuration. It does not enrich,
  upload, or call a provider.
- Future enrichment commands must stay explicit and should summarize what text they will
  send before making provider requests.
