# api/: Abakos Developer API (OpenAI-compatible)

Managed gateway at `https://api.abakos.ai/v1`, drop-in replacement for OpenAI
in Cursor, VS Code (Continue, Cline), CLI, LangChain, LiteLLM, and custom apps.

## Status

Plan only. See [`docs/16-developer-api-and-ide.md`](../docs/16-developer-api-and-ide.md).

## Planned layout

```
api/
  gateway/     # Auth, billing, rate-limit, OpenAI /v1 proxy, job routing
  README.md
```

## MVP endpoints

- `GET /v1/models`
- `POST /v1/chat/completions` (streaming SSE)
- `POST /v1/embeddings` (phase 2)

## Quick start (once live)

```bash
export ABAKOS_API_KEY=abk_live_…
curl https://api.abakos.ai/v1/chat/completions \
  -H "Authorization: Bearer $ABAKOS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"abakos/qwen2.5-coder-32b-instruct","messages":[{"role":"user","content":"Hello"}],"stream":true}'
```

Cursor: set OpenAI Base URL to `https://api.abakos.ai/v1` and use your Abakos API key.
