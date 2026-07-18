# 15 · Branding Policy

Binding rules for a consistent, serious appearance. Guiding principle: **honesty as brand**, no hype, no miracle promises. We are infrastructure, not a casino.

## Name & spelling
- **Always "Abakos"**: capital A, with **"k"**. Never "Abacus" (avoid confusion with abacus.ai).
- Ticker: **`ABA`** (always uppercase). Note: `ABA` is already used by several small/meme tokens on BSC and Ethereum. This is a deliberate, informed choice, not an oversight. If confusion ever becomes a real problem, revisit.
- Network: "Abakos" / "Abakos Network". Node binary: `abkd` (unchanged; it's the daemon name, not the ticker). Consumer app: "Abakos Chat".
- Never "the Abakos coin" in serious context. Use "the ABA token" / "the Abakos protocol."

## Tagline & core messages
- **Primary:** "Compute that pays for itself."
- **One-liner:** The AI compute blockchain where every *paid* GPU job simultaneously secures the chain, so compute becomes cheaper than anywhere else.
- **3 pillars (always in this order):** 1) enforced usefulness · 2) on-chain marketplace + escrow · 3) Abakos Chat.

## Logo
- Abacus mark + wordmark (PNG): `site/public/assets/logo-horizontal.png` (navbar/footer), `site/public/assets/apple-touch-icon.png` (app icon / apple-touch).
- Favicon: `site/public/favicon.png` (from app icon).
- Social preview: `site/public/og.png` (1200×630).

## Design language (v5: "premium single-source", semantic status)
Deep black, one brand hue (electric blue) used at three lightness stops for gradients/glow instead of a flat single value. Buttons, hero headline accent, and hover states all shade from the same hue family, plus **one** semantic accent (green) reserved strictly for "this is real today" claims (live status badges, the hero status dot, the proven-facts numbers in "What exists today"). Blue never means "live"; green never means "click here." A consistent 3-step radius scale (sm/md/lg) replaces the previous ad-hoc 3–6px values per component. Motion carries over from v3: animated **canvas hero**, hover micro-interactions, a shared easing curve (`--abk-ease`). Numbered sections (01, 02 …) + mono labels + hairlines remain. (All animations respect `prefers-reduced-motion`.)

**Hard rule (learned the hard way):** no color may be hardcoded a second time outside `tokens.css`. A previous redesign hardcoded a lighter blue directly into the hero canvas animation's JS instead of reading the brand token. It drifted from the real brand color and was visibly a different blue than the buttons/logo, especially on mobile where the animation fills the whole hero next to the CTA buttons. `site.js` now reads `--abk-brand-light-rgb` via `getComputedStyle` at runtime specifically so this class of bug cannot recur.

## Color palette (corporate tokens)

See `site/public/assets/tokens.css` for canonical names:

| Token | Hex | Meaning |
|---|---|---|
| `--abk-brand` | `#0b5cfd` (logo blue, verified by sampling the PNG) | Brand, links, buttons, interactive accents |
| `--abk-brand-light` | `#5b8dff` | Gradient/glow highlight stop only, never used alone as a second brand color |
| `--abk-brand-dark` | `#0846c4` | Gradient/pressed-state shade only |
| `--abk-green` | `#4ade80` | Reserved for genuinely live/proven status only |
| `--abk-red` | `#ff5d6c` | Errors only |
| `--abk-bg` | `#070709` | |
| `--abk-surface` | `#101118` | |
| `--abk-card` | `#0d0e14` | |
| `--abk-text` | `#f6f7fb` | |
| `--abk-text-muted` | `#8a8fa0` | |
| `--abk-text-soft` | `#b8bfcc` | |
| `--abk-line` | `#202433` | |

Shape scale: `--abk-radius-sm` (4px, badges/inputs/small chips) · `--abk-radius-md` (8px, buttons/cards/grids) · `--abk-radius-lg` (16px, the hero console, the one flagship element that gets a bigger radius on purpose).

`:root{color-scheme:dark}` plus `<meta name="color-scheme" content="dark">` are set explicitly so mobile browsers don't apply their own auto-dark-mode adjustments to native form controls.

CSS files: `site/public/assets/tokens.css` (tokens only) → `site/public/assets/site.css` (components, all colors via `var(--abk-...)`, zero hex literals except `#fff`/transparent). One brand hue total, used at three lightness stops, no unrelated second color.

## Typography (v3)
- **Display:** "Cabinet Grotesk" (800/700), bolder and more distinctive than the very common "Clash Display" used across much of crypto branding; large, tight headlines (`letter-spacing:-.02em`).
- **Body/UI:** "Satoshi" (400/500/700), unchanged.
- **Labels/data:** mono (`ui-monospace`), uppercase, wide tracking.
- Fallbacks: display→Space Grotesk; body→Inter/system. Loaded via Fontshare.

## Subdomain policy (one canonical URL per page, ever)
- `abakos.ai` (+ `www`) hosts the marketing/informational surfaces that don't have their own subdomain: home, Developer API, Providers, Protocol/Network, Docs, Investors, About, Contact, legal, Litepaper/Whitepaper.
- `marketplace.abakos.ai`, `chat.abakos.ai` and `status.abakos.ai` are the **real, sole, canonical** home of those three pages, not a mirror, not a redirect-back-to-main. Clicking "Marketplace" anywhere on the site takes you to `marketplace.abakos.ai` directly; it does not land on `abakos.ai/marketplace/` first. `abakos.ai/marketplace/`, `/chat/`, `/status/` and the retired `/testnet/` all 301-redirect *to* the subdomain, never the other way around.
- `/testnet/` no longer exists as a separate page. It was a near-duplicate of `/status/` (both showed the same roadmap; users found "two status pages" confusing). Its "T1 acceptance gate" checklist was merged into `/status/`, which is the single, comprehensive delivery-status page.
- No `providers.abakos.ai`: the supply side is a page/section of the same product, not a separate top-level surface (matches how Vast.ai, Akash and Render treat hosts/providers inside one app rather than a separate domain).
- **Isolation, not sharing:** all four hostnames serve out of the same build directory on disk, but each Caddy site block only serves *its own* page plus `/assets/*` via explicit `handle` blocks (mutually exclusive, first match wins), never a generic `try_files` fallback across the whole shared directory. That fallback was the literal cause of a real bug: any subdomain could accidentally serve any other page's real file, because the file genuinely exists at that path in the shared directory. Anything not explicitly handled 301s to the matching page on `abakos.ai`.
- **Every nav/footer link is a full absolute URL**, including links back to `abakos.ai` itself. Nav and footer render identically regardless of which hostname served the page, so a relative `/docs/` link rendered on `marketplace.abakos.ai` would otherwise point at `marketplace.abakos.ai/docs/`, which doesn't exist.

## Voice
- **Honest & fact-based:** name weaknesses openly (e.g. "node is still scaffold," "figures illustrative").
- **Technical but accessible:** explain terms, no buzzword soup.
- **No financial hype:** no price predictions, no "guaranteed" returns. Always disclaimer "not financial advice."
- **Anti-scam stance:** actively emphasize transparency (open source for testnet, honest "% useful" metric).

## Do / Don't
- ✅ "enforced usefulness," "paid, verified work," "cheaper than anywhere."
- ✅ comparison with Pearl/Gonka factual (table), not derogatory.
- ❌ "to the moon," "guaranteed," "risk-free," "the next Bitcoin."
- ❌ present closed models (Opus/GPT) as "available on Abakos": we host open weights only.

## Assets & consistency
- Secure domains/handles: see `docs/14-public-disclosure-and-assets.md`.
- Consistent email sender: `info@abakos.ai`.
- Social bio template: "Compute that pays for itself. PoUW AI-compute L1: enforced usefulness, on-chain marketplace, consumer AI app. abakos.ai".
- Discord: https://discord.gg/zBxNvdMjtM (official community server, link in footer, litepaper, deck, outreach).
