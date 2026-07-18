# Abakos website (v4)

Product-led static website, canonical status surface, generated
documentation, and segmented waitlists.

## Source structure

```text
site/
  src/content.mjs       page content, status taxonomy, roadmap
  src/template.mjs      shared layout, navigation, footer, waitlist
  scripts/build.mjs     static build + Markdown docs + manifest + sitemap
  scripts/serve.mjs     local preview server
  public/assets/        CSS, JS, logo, icons
  tests/site.spec.mjs   Playwright desktop/mobile coverage
  dist/                 generated output (do not edit)
```

The source of truth is the shared build, not the legacy top-level HTML files.
Compatibility `.html` aliases are generated for existing external links.

## Commands

```bash
npm install
npm run build
npm run dev
npm test
```

Preview: `http://127.0.0.1:4173`

## Product routes

Every page still builds under `abakos.ai/<slug>/` in `dist/` (one shared
build), but three of them are canonically served from their own subdomain.
Caddy redirects the `abakos.ai` path to the subdomain, never the reverse:

- `/` (abakos.ai): product-first landing page
- **`console.abakos.ai`**: the Console (deploy bundles + add-ons + funded batch jobs)
- **`chat.abakos.ai`**: Abakos Chat
- **`status.abakos.ai`**: the one delivery-status page, including the
  public-testnet acceptance gate (there is no separate `/testnet/` page;
  it was a near-duplicate of Status and got merged in)
- `/developers/`, `/providers/`, `/network/`, `/docs/` (abakos.ai)
- `/litepaper/`, `/whitepaper/`, `/investors/`, `/about/`, `/contact/`,
  `/privacy/`, `/terms/` (abakos.ai)
- `status.abakos.ai/manifest.json`: machine-readable availability

There is intentionally no `providers.abakos.ai` or `api.abakos.ai` (marketing
page, not the future API host). Those stay pages on the main site, matching
how Vast.ai/Akash/Render treat hosts vs. renters inside one app.

**All nav/footer links are full absolute URLs**, including links back to
`abakos.ai` itself. The shared nav/footer render identically no matter which
hostname serves the page, so a relative link would resolve against the wrong
host on the three subdomains.

Caddy gives each subdomain **only its own page** via explicit `handle`
blocks (mutually exclusive, first match wins) instead of a generic
`try_files` fallback shared across one directory. That fallback was the
actual bug behind "every subdomain shows every page": the file for any other
page genuinely exists in the shared build dir, so an unscoped fallback would
happily serve it under the wrong hostname. Anything not the page itself or
`/assets/*` 301s back to the matching path on `abakos.ai`.

## Deployment

Build first, then deploy the generated directory:

```powershell
cd site
npm run build
scp -r dist/* root@217.160.46.61:/opt/sites/abakos.ai/public/
scp waitlist_service.py root@217.160.46.61:/opt/sites/abakos.ai/
ssh root@217.160.46.61 "chown -R caddy:caddy /opt/sites/abakos.ai/public && systemctl restart abakos-waitlist"
```

Host routing lives in
`MarlonMoralesServer/sites/abakos.ai/Caddyfile.snippet`.

Required DNS records before the new hostnames work:

- `status.abakos.ai` → `217.160.46.61`
- `console.abakos.ai` → `217.160.46.61`
- `chat.abakos.ai` → `217.160.46.61`

There is no `marketplace.abakos.ai` anymore. The product is the Console; the
old marketplace host and its redirects were removed, not re-pointed.
