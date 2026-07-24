// In-app auto-update: checks the signed GitHub release feed, and on confirmation
// downloads + installs the update and relaunches -- all inside the app. Signature
// is verified against the embedded public key by the Tauri updater plugin, so a
// tampered download is rejected.
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

let checking = false;
let stylesInjected = false;

function injectStyles(): void {
  if (stylesInjected) return;
  stylesInjected = true;
  const s = document.createElement("style");
  s.textContent = `
  .upd-back{position:fixed;inset:0;background:rgba(4,5,8,.66);backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;z-index:9999}
  .upd-card{width:min(520px,92vw);background:#12151c;border:1px solid #232838;border-radius:14px;padding:22px;box-shadow:0 24px 60px -12px rgba(0,0,0,.6)}
  .upd-card h3{margin:0 0 4px;font-size:19px;color:#e8eaf0}
  .upd-ver{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#8a8fa0;margin-bottom:14px}
  .upd-ver b{color:#39d98a}
  .upd-notes{max-height:180px;overflow:auto;background:#0b0d12;border:1px solid #232838;border-radius:8px;padding:12px;font-size:13px;color:#c7ccda;white-space:pre-wrap;line-height:1.5}
  .upd-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:16px}
  .upd-btn{padding:10px 16px;border-radius:8px;border:1px solid #232838;background:#1a1e28;color:#e8eaf0;font-size:14px;cursor:pointer}
  .upd-btn.fill{background:#39d98a;border-color:#39d98a;color:#06231a;font-weight:600}
  .upd-btn:disabled{opacity:.55;cursor:default}
  .upd-prog{height:8px;border-radius:6px;background:#232838;overflow:hidden;margin-top:16px;display:none}
  .upd-prog>i{display:block;height:100%;width:0;background:linear-gradient(90deg,#5a8cff,#39d98a);transition:width .2s}
  .upd-msg{font-size:12px;color:#8a8fa0;margin-top:10px;min-height:16px}
  .upd-toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:#12151c;border:1px solid #232838;color:#e8eaf0;padding:10px 16px;border-radius:10px;font-size:13px;z-index:9999;box-shadow:0 12px 30px -10px rgba(0,0,0,.6)}
  `;
  document.head.appendChild(s);
}

function toast(msg: string): void {
  injectStyles();
  const t = document.createElement("div");
  t.className = "upd-toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

function showModal(update: Update): void {
  injectStyles();
  const back = document.createElement("div");
  back.className = "upd-back";
  const notes = (update.body || "A new version is available.").trim();
  back.innerHTML = `
    <div class="upd-card">
      <h3>Update available</h3>
      <div class="upd-ver">${update.currentVersion} &rarr; <b>${update.version}</b></div>
      <div class="upd-notes">${escapeHtml(notes)}</div>
      <div class="upd-prog" id="upd-prog"><i id="upd-bar"></i></div>
      <div class="upd-msg" id="upd-msg"></div>
      <div class="upd-actions">
        <button class="upd-btn" id="upd-later">Later</button>
        <button class="upd-btn fill" id="upd-now">Update now</button>
      </div>
    </div>`;
  document.body.appendChild(back);

  const later = back.querySelector("#upd-later") as HTMLButtonElement;
  const now = back.querySelector("#upd-now") as HTMLButtonElement;
  const prog = back.querySelector("#upd-prog") as HTMLElement;
  const bar = back.querySelector("#upd-bar") as HTMLElement;
  const msg = back.querySelector("#upd-msg") as HTMLElement;

  later.onclick = () => back.remove();
  now.onclick = async () => {
    later.disabled = now.disabled = true;
    prog.style.display = "block";
    msg.textContent = "Downloading\u2026";
    let downloaded = 0;
    let total = 0;
    try {
      await update.downloadAndInstall((e) => {
        switch (e.event) {
          case "Started":
            total = e.data.contentLength || 0;
            break;
          case "Progress":
            downloaded += e.data.chunkLength;
            if (total > 0) bar.style.width = Math.min(100, (downloaded / total) * 100).toFixed(1) + "%";
            msg.textContent = `Downloading\u2026 ${(downloaded / 1e6).toFixed(1)} MB${total ? " / " + (total / 1e6).toFixed(1) + " MB" : ""}`;
            break;
          case "Finished":
            bar.style.width = "100%";
            msg.textContent = "Installing\u2026 the app will restart.";
            break;
        }
      });
      await relaunch();
    } catch (err) {
      msg.textContent = "Update failed: " + ((err as Error).message || String(err));
      later.disabled = now.disabled = false;
      later.textContent = "Close";
    }
  };
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
}

/**
 * Check for a newer signed release. On startup pass { silent: true } so nothing
 * pops up when up to date; the Settings button passes silent:false for feedback.
 */
export async function checkForUpdate(opts: { silent?: boolean } = {}): Promise<void> {
  if (checking) return;
  checking = true;
  try {
    // GitHub's releases/latest redirect intermittently 504s; retry before
    // surfacing an error to the user.
    let update: Update | null = null;
    let lastErr: unknown;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        update = await check();
        lastErr = undefined;
        break;
      } catch (e) {
        lastErr = e;
        await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)));
      }
    }
    if (lastErr) throw lastErr;
    if (update) showModal(update);
    else if (!opts.silent) toast("You're on the latest version.");
  } catch (e) {
    if (!opts.silent) toast("Update check failed: " + ((e as Error).message || String(e)));
  } finally {
    checking = false;
  }
}
