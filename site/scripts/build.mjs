import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { home, pages, release } from "../src/content.mjs";
import {
  canonicalFor,
  renderAppPage,
  renderDocumentPage,
  renderHome,
  renderPage,
} from "../src/template.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const siteDir = path.resolve(here, "..");
const repoDir = path.resolve(siteDir, "..");
const outDir = path.join(siteDir, "dist");

// Cache-busting version derived from asset contents, not a manually-edited
// date string. Every edit to CSS/JS automatically invalidates client caches
// without anyone needing to remember to bump a "?v=" number.
const assetSources = await Promise.all(
  ["site.css", "site.js", "tokens.css"].map((file) =>
    readFile(path.join(siteDir, "public", "assets", file), "utf8"),
  ),
);
const ASSET_V = createHash("sha1")
  .update(assetSources.join("\n"))
  .digest("hex")
  .slice(0, 10);
const withAssetVersion = (html) => html.replaceAll("20260715", ASSET_V);

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");

const inline = (value) => {
  let text = escapeHtml(value);
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  text = text.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)]+|[^)]+)\)/g,
    '<a href="$2">$1</a>',
  );
  return text;
};

function markdownToHtml(source) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let paragraph = [];
  let list = null;
  let inCode = false;
  let code = [];
  let codeLang = "";

  const flushParagraph = () => {
    if (paragraph.length) {
      out.push(`<p>${inline(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      out.push(`</${list}>`);
      list = null;
    }
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (line.startsWith("```")) {
      flushParagraph();
      flushList();
      if (!inCode) {
        inCode = true;
        codeLang = line.slice(3).trim();
      } else {
        out.push(
          `<pre class="codeblock"><code data-lang="${escapeHtml(codeLang)}">${escapeHtml(code.join("\n"))}</code></pre>`,
        );
        inCode = false;
        code = [];
        codeLang = "";
      }
      continue;
    }
    if (inCode) {
      code.push(line);
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    if (/^\|.*\|$/.test(line) && /^\|?[\s:|-]+\|/.test(lines[i + 1] || "")) {
      flushParagraph();
      flushList();
      const header = line
        .split("|")
        .slice(1, -1)
        .map((cell) => `<th>${inline(cell.trim())}</th>`)
        .join("");
      i += 2;
      const rows = [];
      while (i < lines.length && /^\|.*\|$/.test(lines[i])) {
        rows.push(
          `<tr>${lines[i]
            .split("|")
            .slice(1, -1)
            .map((cell) => `<td>${inline(cell.trim())}</td>`)
            .join("")}</tr>`,
        );
        i += 1;
      }
      i -= 1;
      out.push(
        `<div class="tablewrap"><table><thead><tr>${header}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`,
      );
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = Math.min(4, heading[1].length + 1);
      const id = heading[2]
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      out.push(`<h${level} id="${id}">${inline(heading[2])}</h${level}>`);
      continue;
    }
    if (/^---+$/.test(line.trim())) {
      flushParagraph();
      flushList();
      out.push("<hr>");
      continue;
    }
    if (line.startsWith("> ")) {
      flushParagraph();
      flushList();
      out.push(`<blockquote>${inline(line.slice(2))}</blockquote>`);
      continue;
    }
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const type = unordered ? "ul" : "ol";
      if (list !== type) {
        flushList();
        list = type;
        out.push(`<${type}>`);
      }
      out.push(`<li>${inline((unordered || ordered)[1])}</li>`);
      continue;
    }
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  if (inCode) {
    out.push(`<pre class="codeblock"><code>${escapeHtml(code.join("\n"))}</code></pre>`);
  }
  return out.join("\n");
}

async function writeRoute(route, html, legacy = true) {
  const versioned = withAssetVersion(html);
  const routeDir = route ? path.join(outDir, route) : outDir;
  await mkdir(routeDir, { recursive: true });
  await writeFile(path.join(routeDir, "index.html"), versioned, "utf8");
  if (route && legacy) {
    await writeFile(path.join(outDir, `${route}.html`), versioned, "utf8");
  }
}

async function copyIfPresent(source, target) {
  if (existsSync(source)) {
    await cp(source, target, { recursive: true });
  }
}

await rm(outDir, { recursive: true, force: true });
await mkdir(path.join(outDir, "assets"), { recursive: true });

await copyIfPresent(path.join(siteDir, "public"), outDir);

await writeRoute("", renderHome(home), false);
for (const [slug, page] of Object.entries(pages)) {
  await writeRoute(slug, renderPage(slug, page));
}

for (const [slug, filename, title, description, status] of [
  [
    "litepaper",
    "litepaper.md",
    "Abakos Litepaper",
    "A concise overview of Abakos: PoS compute, full hardware utilization, ABA wallet settlement.",
    "CURRENT",
  ],
  [
    "whitepaper",
    "whitepaper.md",
    "Abakos Whitepaper",
    "Architecture, marketplace add-ons, Provider Agent, tokenomics, roadmap and risks.",
    "DRAFT v0.2",
  ],
]) {
  const markdown = await readFile(path.join(repoDir, "docs", filename), "utf8");
  await writeRoute(
    slug,
    renderDocumentPage(
      slug,
      { title, description, status },
      markdownToHtml(markdown),
    ),
  );
}

for (const [slug, meta, bodyFile] of [
  [
    "wallet",
    { title: "Abakos Wallet", description: "Connect Keplr, Leap, Cosmostation or MetaMask to the Abakos sandbox: balance, send, delegate, faucet.", eyebrow: "Sandbox tool", status: ["SANDBOX", "development"], h1: "Wallet", lede: "Connect Keplr, Leap or Cosmostation (native Cosmos wallets), or MetaMask via the Cosmos Extension snap, to the Abakos sandbox. Get test ABA, send and delegate. ABA here has no value." },
    "wallet.body.html",
  ],
  [
    "explorer",
    { title: "Abakos Explorer", description: "Live blocks, validators and supply on the Abakos sandbox chain.", eyebrow: "Sandbox network", status: ["LIVE", "live"], h1: "Explorer", lede: "Live height, validators, supply and latest blocks on abakos-sandbox-1." },
    "explorer.body.html",
  ],
  [
    "dashboard",
    { title: "Provider Dashboard", description: "Live Abakos Provider Agent: idle-mining the most profitable coin, buyback into ABA, 88/4/4/4 split, on-chain payouts.", eyebrow: "Sandbox tool", status: ["SANDBOX", "development"], h1: "Provider Dashboard", lede: "The Provider Agent serves rentals first, mines the most profitable coin on idle GPU/CPU, buys back ABA and pays the host on-chain (88% host / 4% stakers / 4% treasury / 4% burn). Mining is simulated on the sandbox; the payouts are real." },
    "dashboard.body.html",
  ],
  [
    "dex",
    { title: "Abakos DEX", description: "Swap ABA and test USDT on the Abakos EVM (chain 9721) - a real on-chain constant-product AMM.", eyebrow: "Sandbox EVM", status: ["LIVE", "live"], h1: "DEX", lede: "Real on-chain ABA/USDT swaps on the Abakos EVM via MetaMask. Constant-product AMM, 0.30% fee. Sandbox only - no value." },
    "dex.body.html",
  ],
]) {
  const bodyHtml = await readFile(path.join(siteDir, "src", bodyFile), "utf8");
  await writeRoute(slug, renderAppPage(slug, meta, bodyHtml));
}

const manifest = {
  project: "Abakos",
  phase: release.phase,
  label: release.label,
  updated: release.updated,
  summary: release.summary,
  surfaces: {
    website: { mode: "live", url: "https://abakos.ai" },
    explorer: { mode: "live", publicUrl: "https://abakos.ai/explorer/" },
    console: { mode: "planned", publicUrl: null },
    api: { mode: "in_development", publicUrl: null },
    chat: { mode: "planned", publicUrl: null },
    provider: { mode: "in_development", publicUrl: "https://abakos.ai/dashboard/" },
  },
};
await mkdir(path.join(outDir, "status"), { recursive: true });
await writeFile(
  path.join(outDir, "status", "manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);

const routes = [
  "",
  ...Object.keys(pages),
  "litepaper",
  "whitepaper",
  "wallet",
  "explorer",
  "dashboard",
  "dex",
];
await writeFile(
  path.join(outDir, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${routes
    .map(
      (route) =>
        `  <url><loc>${route ? canonicalFor(route) : "https://abakos.ai/"}</loc><lastmod>${release.updated}</lastmod></url>`,
    )
    .join("\n")}\n</urlset>\n`,
  "utf8",
);
await writeFile(
  path.join(outDir, "robots.txt"),
  "User-agent: *\nAllow: /\nSitemap: https://abakos.ai/sitemap.xml\n",
  "utf8",
);
await writeFile(
  path.join(outDir, "404.html"),
  withAssetVersion(
    renderPage("not-found", {
      title: "Page not found",
      description: "The requested Abakos page does not exist.",
      eyebrow: "404",
      h1: "This route has no block.",
      lede: "Return to the product hub or inspect the current delivery status.",
      status: ["NOT FOUND", "planned"],
      primary: ["Back to Abakos", "https://abakos.ai/"],
      secondary: ["View status", "https://status.abakos.ai/"],
      body: "",
    }),
  ),
  "utf8",
);

console.log(`Built ${routes.length} routes into ${outDir}`);
