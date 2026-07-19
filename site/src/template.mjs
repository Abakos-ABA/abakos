import { navGroups, phases, release } from "./content.mjs";

const esc = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

const roadmap = () => `
  <div class="roadmap">
    ${phases
      .map(
        ([phase, title, text, status], index) => `
          <article class="roadmap-item ${status === "live" ? "current" : ""}">
            <div class="roadmap-top">
              <span>${esc(phase)}</span>
              <span class="status-badge status-${status}">${status === "live" ? "LIVE" : status === "done" ? "DONE" : status === "development" ? "IN DEVELOPMENT" : "PLANNED"}</span>
            </div>
            <h3>${esc(title)}</h3>
            <p>${esc(text)}</p>
            ${index < phases.length - 1 ? '<i aria-hidden="true"></i>' : ""}
          </article>`,
      )
      .join("")}
  </div>`;

// A nav link is "active" if it points at the page we're on -- either as an
// absolute abakos.ai path, a bare relative path, or the subdomain we're
// currently rendering for (marketplace/chat/status live on their own
// hostname, not under abakos.ai/<slug>/).
const isActiveLink = (href, active) =>
  Boolean(active) &&
  (href === `/${active}/` ||
    href === `https://abakos.ai/${active}/` ||
    href.startsWith(`https://${active}.`));

const navigation = (active = "") => `
  <nav id="nav" aria-label="Primary">
    <div class="wrap nav-wrap">
      <a class="brand" href="https://abakos.ai/" aria-label="Abakos home">
        <img class="brand-logo" src="/assets/logo-horizontal.png?v=4" alt="Abakos">
      </a>
      <button type="button" class="burger" id="hbtn" aria-label="Open menu" aria-expanded="false" aria-controls="navlinks"><span></span></button>
      <div class="navlinks" id="navlinks">
        ${navGroups
          .map(
            (group) => `
              <div class="nav-group">
                <button class="nav-group-trigger" type="button" aria-expanded="false">${esc(group.label)} <span aria-hidden="true">⌄</span></button>
                <div class="nav-menu">
                  ${group.links
                    .map(
                      ([label, href]) =>
                        `<a href="${href}"${isActiveLink(href, active) ? ' class="on"' : ""}>${esc(label)}</a>`,
                    )
                    .join("")}
                </div>
              </div>`,
          )
          .join("")}
        <a class="nav-direct" href="https://discord.gg/zBxNvdMjtM" target="_blank" rel="noopener">Discord</a>
        <a class="btn btn-fill nav-cta" href="https://console.abakos.ai/">Rent compute</a>
      </div>
    </div>
  </nav>`;

const statusStrip = () => `
  <div class="global-status" role="status">
    <div class="wrap">
      <span class="status-badge status-live">${esc(release.phase)} · ${esc(release.label)}</span>
      <span class="global-status-text">${esc(release.summary)}</span>
      <a href="https://status.abakos.ai/"><span class="status-link-full">View delivery status</span><span class="status-link-short">Status</span> →</a>
    </div>
  </div>`;

// One list, everywhere -- this form appears on several pages, but it is
// always the same underlying list. The copy and button text must stay
// identical on every page so it reads as one list, not six different
// newsletters. "segment" only tags internally which page someone signed up
// from (useful for us later); it is never shown to the visitor.
const waitlist = (segment = "general") => `
  <section id="waitlist" class="waitlist-section">
    <div class="wrap split">
      <div>
        <div class="section-label">One list, every update</div>
        <h2>Join the Abakos list.</h2>
        <p class="lede">Updates on all progress and products &mdash; sandbox, Console, API and Chat. For the fastest small updates and quick answers, hop into our <a href="https://discord.gg/zBxNvdMjtM" target="_blank" rel="noopener">Discord</a>. Never token-price hype.</p>
      </div>
      <div>
        <form class="wl" data-waitlist="${esc(segment)}">
          <label class="sr-only" for="waitlist-email-${esc(segment)}">Email address</label>
          <input id="waitlist-email-${esc(segment)}" type="email" name="email" autocomplete="email" placeholder="you@company.com" required>
          <button class="btn btn-fill" type="submit">Join the list</button>
        </form>
        <p class="msg" aria-live="polite"></p>
        <p class="fineprint">You'll get a short confirmation email. One list, unsubscribe any time. See the <a href="https://abakos.ai/privacy/">privacy notice</a>.</p>
      </div>
    </div>
  </section>`;

const footer = () => `
  <footer>
    <div class="wrap">
      <div class="footer-grid">
        <div class="footer-brand">
          <a class="brand brand-footer" href="https://abakos.ai/"><img class="brand-logo" src="/assets/logo-horizontal.png?v=4" alt="Abakos"></a>
          <p>Hardware that stays fully used.</p>
          <span class="status-badge status-live">PUBLIC SANDBOX LIVE</span>
        </div>
        <div class="footer-column"><h4>Products</h4><a href="https://console.abakos.ai/">Console</a><a href="https://chat.abakos.ai/">Chat</a><a href="https://abakos.ai/developers/">API</a><a href="https://abakos.ai/wallet/">Wallet</a><a href="https://abakos.ai/providers/">Providers</a></div>
        <div class="footer-column"><h4>Network</h4><a href="https://abakos.ai/network/">Protocol</a><a href="https://status.abakos.ai/">Status</a><a href="https://abakos.ai/explorer/">Explorer</a><a href="https://abakos.ai/dex/">DEX</a><a href="https://pool.abakos.ai/">Mining Pool</a><a href="https://abakos.ai/investors/">Investors</a></div>
        <div class="footer-column"><h4>Resources</h4><a href="https://abakos.ai/docs/">Docs</a><a href="https://abakos.ai/litepaper/">Litepaper</a><a href="https://abakos.ai/whitepaper/">Whitepaper</a><a href="https://github.com/Abakos-ABA/abakos" target="_blank" rel="noopener">GitHub</a><a href="https://discord.gg/zBxNvdMjtM" target="_blank" rel="noopener">Discord</a></div>
      </div>
      <div class="footer-bottom">
        <span>© <span id="yr">2026</span> Abakos</span>
        <div><a href="https://abakos.ai/about/">About</a><a href="https://abakos.ai/privacy/">Privacy</a><a href="https://abakos.ai/terms/">Terms</a><a href="https://abakos.ai/contact/">Contact</a></div>
      </div>
      <p class="disc">Abakos is pre-mainnet infrastructure; the public sandbox is live for testing (ABA has no value there). Timelines and protocol parameters are drafts. Nothing on this site is financial advice or a guarantee of compute price, token value, provider revenue, or launch date.</p>
    </div>
  </footer>`;

const document = ({
  title,
  description,
  canonical,
  active,
  body,
  bodyClass = "",
  includeStatus = true,
  schema = "",
}) => `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${esc(title)}</title>
  <meta name="description" content="${esc(description)}">
  <meta name="theme-color" content="#070709">
  <meta name="color-scheme" content="dark">
  <link rel="canonical" href="${esc(canonical)}">
  <link rel="icon" href="/favicon.png" type="image/png" sizes="32x32">
  <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Abakos">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(description)}">
  <meta property="og:url" content="${esc(canonical)}">
  <meta property="og:image" content="https://abakos.ai/og.png">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="preconnect" href="https://api.fontshare.com" crossorigin>
  <link href="https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@700,800&f[]=satoshi@400,500,700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/tokens.css?v=20260715">
  <link rel="stylesheet" href="/assets/site.css?v=20260715">
  ${schema}
</head>
<body class="${esc(bodyClass)}">
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="topline"></div>
  ${navigation(active)}
  ${includeStatus ? statusStrip() : ""}
  <main id="main">${body.replaceAll('<div data-roadmap></div>', roadmap())}</main>
  ${footer()}
  <script src="/assets/site.js?v=20260715" defer></script>
</body>
</html>`;

export const renderHome = (page) =>
  document({
    title: page.title,
    description: page.description,
    canonical: "https://abakos.ai/",
    active: "",
    body: `${page.body}${waitlist("general")}`,
    bodyClass: "home-page",
    schema: `<script type="application/ld+json">${JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "Abakos",
      url: "https://abakos.ai",
      description: page.description,
    })}</script>`,
  });

// These three pages are canonically served from their own subdomain now --
// abakos.ai/<slug>/ still gets built (so the subdomain has a file to serve)
// but redirects at the Caddy level, so the <link rel="canonical"> must point
// at the real, single, reachable URL instead of the abakos.ai path.
const subdomainSlugs = new Set(["console", "chat", "status", "pool"]);
export const canonicalFor = (slug) =>
  subdomainSlugs.has(slug) ? `https://${slug}.abakos.ai/` : `https://abakos.ai/${slug}/`;

export const renderPage = (slug, page) => {
  const status = page.status
    ? `<span class="status-badge status-${esc(page.status[1])}">${esc(page.status[0])}</span>`
    : "";
  const primary = page.primary
    ? `<a class="btn btn-fill" href="${esc(page.primary[1])}">${esc(page.primary[0])}</a>`
    : "";
  const secondary = page.secondary
    ? `<a class="btn btn-line" href="${esc(page.secondary[1])}">${esc(page.secondary[0])}</a>`
    : "";
  const hero = `
    <header class="page-hero">
      <div class="wrap">
        <div class="page-eyebrow">${esc(page.eyebrow || "")}</div>
        ${status}
        <h1>${esc(page.h1)}</h1>
        <p class="lede">${esc(page.lede)}</p>
        ${primary || secondary ? `<div class="actions">${primary}${secondary}</div>` : ""}
      </div>
    </header>`;
  return document({
    title: `${page.title} · Abakos`,
    description: page.description,
    canonical: canonicalFor(slug),
    active: slug,
    body: `${hero}${page.body}${page.segment ? waitlist(page.segment) : ""}`,
    bodyClass: `page-${slug}`,
  });
};

// App pages (wallet, explorer): full site chrome (nav/footer/CSS) + a standard
// hero, then an injected interactive body (its own markup + <script>). The body
// lives in a separate .html file so its backticks/${} don't clash with our
// template literals.
export const renderAppPage = (slug, meta, bodyHtml) =>
  document({
    title: `${meta.title} · Abakos`,
    description: meta.description,
    canonical: canonicalFor(slug),
    active: slug,
    body: `
      <header class="page-hero">
        <div class="wrap">
          <div class="page-eyebrow">${esc(meta.eyebrow || "")}</div>
          ${meta.status ? `<span class="status-badge status-${esc(meta.status[1])}">${esc(meta.status[0])}</span>` : ""}
          <h1>${esc(meta.h1)}</h1>
          <p class="lede">${esc(meta.lede || "")}</p>
        </div>
      </header>
      ${bodyHtml}
    `,
    bodyClass: `page-${slug} app-page`,
  });

export const renderDocumentPage = (slug, metadata, contentHtml) =>
  document({
    title: `${metadata.title} · Abakos`,
    description: metadata.description,
    canonical: `https://abakos.ai/${slug}/`,
    active: "docs",
    body: `
      <header class="page-hero doc-hero">
        <div class="wrap">
          <div class="page-eyebrow">Documentation · ${esc(metadata.status)}</div>
          <span class="status-badge status-development">${esc(metadata.status)}</span>
          <h1>${esc(metadata.title)}</h1>
          <p class="lede">${esc(metadata.description)}</p>
          <div class="actions"><a class="btn btn-line" href="/docs/">All documentation</a></div>
        </div>
      </header>
      <section><div class="wrap"><article class="prose">${contentHtml}</article></div></section>
    `,
    bodyClass: "doc-page",
  });
