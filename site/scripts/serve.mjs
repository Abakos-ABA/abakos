import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "dist");
const port = Number(process.env.PORT || 4173);

const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
};

const safePath = (url) => {
  const pathname = decodeURIComponent(new URL(url, "http://localhost").pathname);
  const normalized = path.normalize(pathname).replace(/^([/\\])+/, "");
  if (normalized.startsWith("..")) return null;
  return normalized;
};

createServer((req, res) => {
  const requested = safePath(req.url || "/");
  if (requested === null) {
    res.writeHead(400);
    res.end("Bad request");
    return;
  }

  const candidates = [
    path.join(root, requested),
    path.join(root, requested, "index.html"),
    path.join(root, `${requested}.html`),
  ];
  let file = candidates.find(
    (candidate) => existsSync(candidate) && statSync(candidate).isFile(),
  );
  if (!file) {
    file = path.join(root, "404.html");
    res.statusCode = 404;
  }
  res.setHeader("Content-Type", types[path.extname(file)] || "application/octet-stream");
  res.setHeader(
    "Cache-Control",
    file.endsWith(".html") ? "no-cache" : "public, max-age=3600",
  );
  createReadStream(file).pipe(res);
}).listen(port, "127.0.0.1", () => {
  console.log(`Abakos site: http://127.0.0.1:${port}`);
});
