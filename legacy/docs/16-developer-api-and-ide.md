# 16 · Developer API & IDE Integration (Cursor, VS Code, …)

The **developer API** is the fifth demand pillar alongside chat: developers should use Abakos compute **without crypto knowledge**, via API key in tools they already use (Cursor, VS Code, CLI, own apps).

> **Core principle:** 100% **OpenAI-compatible** (`/v1/*`). No proprietary SDK needed; any app that supports OpenAI, OpenRouter, or Together works with Abakos after a base URL change.

---

## Why this matters strategically

| Effect | Explanation |
|---|---|
| **Immediate demand** | every API call = paid inference job → `useful_ratio` rises on-chain |
| **Virality** | devs share config snippets ("cheaper than OpenRouter") on Reddit, Discord, GitHub |
| **Anti-Pearl story** | Pearl has **one** gated Together endpoint. Abakos = **open API for everyone** |
| **IDE = high-intent users** | Cursor/VS Code users already pay for AI, price undercut hits directly |

---

## Architecture

```
IDE / CLI / App (OpenAI client)
        │
        ▼
api.abakos.ai/v1          ← managed gateway (auth, billing, rate-limit, routing)
        │
        ├── real-time path (chat, IDE, streaming)     → latency-optimized, session escrow
        └── batch path (embeddings, fine-tuning)     → cheaper, async OK
        │
        ▼
Compute marketplace (job + escrow) → miner (vLLM/SGLang)
```

- **One gateway**, two internal queues (real-time vs. batch), same OpenAI surface externally.
- **No accept step on the provider side.** Every request is auto-matched to the cheapest active, sufficiently-reputed provider serving the requested model (spec-marketplace.md §6a); providers register a standing listing and stay active, they don't browse and claim individual API calls, that would be far too slow for a synchronous request.
- Initially **hybrid**: gateway routes to partner GPUs, parallel marketplace hookup (like Abakos Chat, Doc 05).
- Later: fully over decentralized network, with fallback to "premium" partners at latency spikes.
- **Multi-turn requests (IDE agents, chat completions with history):** the API is OpenAI-compatible, so the caller already resends the `messages` array each request, exactly like any other OpenAI-compatible provider. Underneath, each call can be matched to a different provider without losing context, because the marketplace job commits to the actual context used, not to a specific provider remembering it. Full design: [`docs/spec-session-continuity.md`](spec-session-continuity.md).

---

## OpenAI-compatible endpoints (MVP → v1)

| Endpoint | Priority | Use |
|---|---|---|
| `GET /v1/models` | MVP | model list for IDE dropdowns |
| `POST /v1/chat/completions` | **MVP (P0)** | Cursor, Continue, Cline, own apps |
| `POST /v1/completions` | v1 | legacy clients, some plugins |
| `POST /v1/embeddings` | v2 | RAG in Continue, codebase index |
| `POST /v1/audio/transcriptions` | later | optional |
| `GET /v1/usage` | v1 | dashboard, cost control |

### Streaming (required for IDEs)

- `stream: true` → server-sent events (SSE), format identical to OpenAI.
- First-token latency target: **< 800 ms** (real-time path); above that coding assist feels broken.

### Model names (convention)

```
abakos/qwen2.5-coder-32b-instruct   # coding (IDE-first)
abakos/deepseek-coder-v2-lite       # coding, faster
abakos/llama-3.3-70b-instruct       # general / chat
abakos/qwen2.5-72b-instruct         # general, stronger
abakos/nomic-embed-text             # embeddings (phase 2)
```

Prefix `abakos/` makes origin clear and does not collide with OpenAI model IDs.

---

## IDE integration (concrete)

### Cursor

Cursor supports **custom OpenAI-compatible providers** (Settings → Models).

1. Create API key on [abakos.ai](https://abakos.ai) (dashboard, later).
2. In Cursor:
   - **Override OpenAI Base URL:** `https://api.abakos.ai/v1`
   - **API Key:** `abk_live_…`
   - **Model:** `abakos/qwen2.5-coder-32b-instruct`

Alternatively via `cursor-settings` (JSON), if available:

```json
{
  "openai.baseUrl": "https://api.abakos.ai/v1",
  "openai.apiKey": "abk_live_…"
}
```

**Cursor Agent / Composer:** need reliable streaming + sufficient context (32k+). Launch models: Coder-32B with 32k context; 128k+ as premium tier.

### VS Code: Continue

[Continue](https://continue.dev) is the most common open-source AI assistant with custom API support.

`~/.continue/config.json` (or `.continue/config.json` in project):

```json
{
  "models": [
    {
      "title": "Abakos Coder",
      "provider": "openai",
      "model": "abakos/qwen2.5-coder-32b-instruct",
      "apiBase": "https://api.abakos.ai/v1",
      "apiKey": "abk_live_…"
    }
  ],
  "tabAutocompleteModel": {
    "title": "Abakos Autocomplete",
    "provider": "openai",
    "model": "abakos/deepseek-coder-v2-lite",
    "apiBase": "https://api.abakos.ai/v1",
    "apiKey": "abk_live_…"
  }
}
```

### VS Code: Cline / Roo Code / CodeGPT

All support **OpenAI-compatible base URL + API key**. Setup analogous: base `https://api.abakos.ai/v1`, model from `/v1/models`.

### CLI & SDKs (drop-in)

Every OpenAI client works without an Abakos SDK:

**Python:**
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.abakos.ai/v1",
    api_key="abk_live_…",
)

stream = client.chat.completions.create(
    model="abakos/qwen2.5-coder-32b-instruct",
    messages=[{"role": "user", "content": "Refactor this function…"}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

**Node / curl / LangChain / LiteLLM:** same pattern, set `base_url` / `api_base`.

**LiteLLM** (one proxy for many tools):
```yaml
model_list:
  - model_name: abakos-coder
    litellm_params:
      model: openai/abakos/qwen2.5-coder-32b-instruct
      api_base: https://api.abakos.ai/v1
      api_key: os.environ/ABAKOS_API_KEY
```

---

## Auth, billing, limits

| Topic | Design |
|---|---|
| **API key** | `abk_live_…` / `abk_test_…`; rotatable in dashboard |
| **Auth header** | `Authorization: Bearer abk_live_…` (OpenAI standard) |
| **Billing** | prepaid balance (card/USDC) or ABA (~10–20% discount, real token demand since ABA has to be acquired to fund the balance; the underlying marketplace job then settles to the provider in ABA instead of stablecoin, see Doc 04) |
| **Free tier** | small free quota from ecosystem pool (Doc 03), dev onboarding |
| **Rate limits** | per key: RPM/TPM; higher limits against deposit |
| **Org / team keys** | v1: separate keys per team, shared balance |

Crypto stays **optional**: devs pay like OpenRouter, ABA only for discount.

---

## Coding-specific requirements

IDE usage is **latency-critical** and needs **code models**:

| Requirement | Solution |
|---|---|
| Tab autocomplete | small, fast model (7B–16B coder); low latency |
| Chat / agent | 32B coder or 70B general; streaming |
| FIM (fill-in-the-middle) | v1: DeepSeek-Coder FIM format via `/v1/completions` or dedicated parameter; verify against Continue autocomplete |
| Long context | 32k MVP, 128k premium (neocloud multi-GPU) |
| @codebase / RAG | `/v1/embeddings` + local index in Continue (phase 2) |

**Launch model priority (IDE):**
1. Qwen2.5-Coder-32B-Instruct
2. DeepSeek-Coder-V2-Lite (autocomplete)
3. Llama-3.3-70B (general fallback)

---

## Abakos vs. Pearl vs. OpenRouter (API)

| | Pearl | OpenRouter | Abakos |
|---|---|---|---|
| Public OpenAI API | no (1 Together endpoint) | yes | **yes** |
| Cursor/VS Code ready | no | yes | **yes** |
| Subsidy via mining | yes (but 0% useful) | no | **yes (enforced useful)** |
| Price vs. OpenAI | N/A (gated) | aggregator margin | **below market** (PoUW subsidy) |
| Decentralized | chain yes, inference no | no | **yes** (goal) |

---

## Roadmap (API-specific)

| Phase | Deliverable |
|---|---|
| **Thin (pre-mainnet)** | `api.abakos.ai` on rented GPUs; OpenAI-compatible; docs + Cursor/Continue setup guide; first paying devs |
| **Phase 3 (testnet)** | gateway → marketplace, batch mode only (embeddings, non-streaming completions); no real-time path needed yet |
| **Phase 4 (testnet beta)** | streaming (`stream: true`) on the same hybrid real-time infra Abakos Chat needs, shipped together with Chat, not held back for Launch |
| **Launch (mainnet)** | real-time path for chat + IDE moves off hybrid partner GPUs onto the fully decentralized network; ABA discount live |
| **Post-launch** | FIM autocomplete, team keys, usage dashboard, LiteLLM plugin |

**Marketing hook:** "Paste this config: 30% cheaper coding AI in Cursor."

---

## Repo layout (planned)

```
abakos/
  api/
    gateway/          # FastAPI/Go, OpenAI-compatible proxy
    README.md
  sdk-python/         # optional: thin wrapper (openai + helpers), not required
  docs/integrations/  # Cursor, Continue, Cline setup guides (later)
```

---

## Risks

- **Latency** decentralized vs. Cursor-native OpenAI → hybrid until network stable.
- **Quality** open coder models vs. Claude/GPT-4 → honest positioning ("cheap + good enough for 80% of tasks").
- **Abuse** (API key leaks, scraping) → rate limits, anomaly detection, key scopes.
- **Support load** → good docs + copy-paste configs more important than custom extension.

## Open decisions

- [ ] own VS Code extension vs. docs only for Continue/Cursor? → **start: docs only** (less maintenance, same reach).
- [ ] `api.abakos.ai` subdomain vs. `abakos.ai/api/v1` → **subdomain** (Caddy, standard for API keys).
- [ ] free-tier size for devs (e.g. $5/month equivalent).

---

## Next steps

1. Thin gateway on partner GPU (RunPod/Vast), proof before mainnet (Doc 13).
2. Landing page section "For Developers" + link to setup guide.
3. Implement `GET/POST /v1/chat/completions` + `GET /v1/models` first.
4. Publish copy-paste configs for Cursor + Continue.
5. r/LocalLLaMA + Hacker News launch when price is benchmarked.
