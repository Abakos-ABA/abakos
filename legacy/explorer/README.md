# Explorer: Testnet dashboard (wireframe)

T1 public host: `explorer.testnet.abakos.ai` (planned).

## Local dev

1. Start seed with API:
   ```bash
   cd node
   go run ./cmd/abkd --simnet --datadir ./data/seed --listen :18555 --mine --http :13080 --params=false
   ```
2. Open `explorer/index.html` in a browser (file:// or static server).
3. Dashboard polls `http://127.0.0.1:13080/api/v1/stats` and `/api/v1/blocks`.

## API (T0)

| Endpoint | Response |
|---|---|
| `GET /api/v1/stats` | `height`, `useful_pct_24h`, `block_count`, `verifier` |
| `GET /api/v1/blocks` | `{ "blocks": [ … ] }` |
| `GET /healthz` | `ok` |

## T1 additions

- Indexer (Postgres) decoupled from node
- Miner addresses, open jobs, Pearl comparison chart
- Deploy beside abakos.ai on VPS (Caddy)

See `docs/17-testnet-plan.md` §9.
