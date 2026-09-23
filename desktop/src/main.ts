import QRCode from "qrcode";
import * as wallet from "./wallet";
import type { Addresses } from "./wallet";
import * as mining from "./mining";
import * as host from "./host";
import { EXPLORER, DEX, enableMining, kvGet, kvSet, fetchTxs, fetchTxsWithProvider, chainProviders, reportStats, cosmosHashForEvmTx, cosmosBalanceAba, activeLeases, providerResources } from "./net";
import type { TxInfo } from "./net";
import { checkForUpdate } from "./update";
import { getVersion } from "@tauri-apps/api/app";
import { openUrl } from "@tauri-apps/plugin-opener";
import logoRaw from "./assets/abakos-3d-drop.svg?raw";

// The real animated Abakos brand mark (color-shifting fields via SMIL + a CSS
// ball-drop). We INLINE the SVG rather than use <img src>: an <img>-embedded SVG
// freezes its internal CSS animations on Linux/webkit2gtk (the ball stuck up top
// while only the outer float ran). Inline, the keyframes + SMIL run on all OS.
// IDs are namespaced per instance so url(#…)/href="#…" refs don't clash when two
// logos (topbar + onboarding) coexist in the DOM. `size` = "sm" | "xl".
const logoBase = logoRaw.slice(logoRaw.indexOf("<svg")).replace("<svg ", '<svg class="ablogo-mark" ');
let logoSeq = 0;
const brandLogo = (size: "sm" | "xl"): string => {
  const n = ++logoSeq;
  let svg = logoBase;
  for (const id of ["fields", "fBlur", "softShadow", "cp0", "cp1", "cp2"]) {
    svg = svg
      .replace(new RegExp(`id="${id}"`, "g"), `id="${id}_${n}"`)
      .replace(new RegExp(`url\\(#${id}\\)`, "g"), `url(#${id}_${n})`)
      .replace(new RegExp(`href="#${id}"`, "g"), `href="#${id}_${n}"`);
  }
  return `<span class="ablogo ${size}">${svg}</span>`;
};

// Theme: names map to :root[data-theme="…"] blocks in styles.css. Persisted via kv
// so the choice survives restarts; applied before the first render to avoid a flash.
const THEMES = [
  { id: "midnight", label: "Midnight", swatch: "#7C46FF" },
  { id: "onyx", label: "Onyx (Dark)", swatch: "#0A0A0A" },
  { id: "aurora", label: "Aurora", swatch: "#00CFFF" },
  { id: "nebula", label: "Nebula", swatch: "#FF4D9D" },
  { id: "ember", label: "Ember", swatch: "#FF8A3D" },
  { id: "matrix", label: "Matrix", swatch: "#3DFF9A" },
  { id: "daylight", label: "Daylight", swatch: "#5B6CFF" },
];
function applyTheme(id: string): void {
  document.documentElement.dataset.theme = THEMES.some((t) => t.id === id) ? id : "midnight";
}
async function initTheme(): Promise<void> {
  try {
    applyTheme((await kvGet("theme")) || "midnight");
  } catch {
    applyTheme("midnight");
  }
}

const POOL = "https://pool.abakos.ai/";
// Escrowed per compute bid by the provider daemon; mirrors ABA_BID_DEPOSIT in
// provider-compute/config/network.sh.
const BID_DEPOSIT_ABA = 5;

// External links open in the system browser - a plain href would navigate the
// Tauri webview away from the app with no way back.
document.addEventListener("click", (e) => {
  const a = (e.target as HTMLElement).closest?.("a[href]") as HTMLAnchorElement | null;
  if (!a) return;
  const href = a.getAttribute("href") || "";
  if (/^https?:\/\//.test(href)) {
    e.preventDefault();
    openUrl(href).catch(() => {});
  }
});

const app = document.getElementById("app") as HTMLElement;

const HS_UNITS = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s", "EH/s", "ZH/s", "YH/s"];
const fmtHs = (h: number): string => {
  h = Number(h || 0);
  let i = 0;
  while (Math.abs(h) >= 1000 && i < HS_UNITS.length - 1) {
    h /= 1000;
    i++;
  }
  return (i ? h.toFixed(2) : Math.round(h)) + " " + HS_UNITS[i];
};
const fmtAba = (n: number): string =>
  Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 6 });
const short = (s: string, n = 10): string => (s.length > 2 * n ? s.slice(0, n) + "\u2026" + s.slice(-6) : s);

let addresses: Addresses | null = null;
let activeTab = "wallet";
let pendingRecipient = ""; // set by "Send" from the address book, consumed on Send-tab render

// Escape user-provided text (contact names) before putting it in innerHTML.
const esc = (s: string): string =>
  (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);
let receiveShowAba = true;
let balanceTimer: number | undefined;
let liveTimer: number | undefined;

function stopTimers(): void {
  if (balanceTimer) window.clearInterval(balanceTimer);
  if (liveTimer) window.clearInterval(liveTimer);
  balanceTimer = liveTimer = undefined;
}

async function copy(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    /* clipboard may be unavailable */
  }
}

// ---------------------------------------------------------------- onboarding
async function boot(): Promise<void> {
  stopTimers();
  if (await wallet.hasWallet()) renderUnlock();
  else renderOnboarding();
}

function shell(inner: string): void {
  app.innerHTML = `
    <div class="topbar">
      <div class="brand">${brandLogo("sm")}<span class="brandword">Abakos&nbsp;<b>Provider</b></span></div>
      <span class="badge off" id="netbadge"><span class="pulse"></span> sandbox</span>
    </div>
    <div class="wrap">${inner}</div>`;
}

function renderOnboarding(): void {
  shell(`
    <div class="center">
      <div class="hero">${brandLogo("xl")}</div>
      <div class="card">
        <div class="label">Welcome</div>
        <h2>Set up your ABA wallet</h2>
        <p class="soft">One wallet earns your mining payouts and holds your ABA. Sandbox phase &mdash; ABA has real value on the live DEX; only risk what you can afford to lose.</p>
        <div class="tabs">
          <div class="tab on" data-tab="create">Create new</div>
          <div class="tab" data-tab="import">Import</div>
        </div>
        <div id="pane"></div>
      </div>
    </div>`);
  const pane = document.getElementById("pane") as HTMLElement;
  const paint = (tab: string): void => {
    document.querySelectorAll(".tab").forEach((t) =>
      t.classList.toggle("on", (t as HTMLElement).dataset.tab === tab),
    );
    pane.innerHTML =
      tab === "create"
        ? `<label class="field"><span>Choose a password (encrypts your key on this device)</span><input id="pw" type="password" placeholder="password"></label>
           <label class="field"><span>Repeat password</span><input id="pw2" type="password" placeholder="repeat"></label>
           <button class="btn fill big" id="do">Create wallet</button>
           <p class="msg" id="msg"></p>`
        : `<label class="field"><span>Recovery phrase (12/24 words) or 0x private key</span><textarea id="seed" placeholder="word1 word2 ... or 0x..."></textarea></label>
           <label class="field"><span>Password (encrypts your key on this device)</span><input id="pw" type="password" placeholder="password"></label>
           <button class="btn fill big" id="do">Import wallet</button>
           <p class="msg" id="msg"></p>`;
    const msg = document.getElementById("msg") as HTMLElement;
    (document.getElementById("do") as HTMLButtonElement).onclick = async () => {
      const pw = (document.getElementById("pw") as HTMLInputElement).value;
      try {
        if (tab === "create") {
          const pw2 = (document.getElementById("pw2") as HTMLInputElement).value;
          if (pw.length < 6) throw new Error("password must be at least 6 characters");
          if (pw !== pw2) throw new Error("passwords do not match");
          const { mnemonic, addresses: a } = await wallet.createNew(pw);
          revealMnemonic(mnemonic, a);
        } else {
          const seed = (document.getElementById("seed") as HTMLTextAreaElement).value.trim();
          if (pw.length < 6) throw new Error("password must be at least 6 characters");
          const a = /^0x?[0-9a-fA-F]{64}$/.test(seed.replace(/^0x/, "0x"))
            ? await wallet.importPrivateKey(seed, pw)
            : await wallet.importMnemonic(seed, pw);
          addresses = a;
          renderApp();
        }
      } catch (e) {
        msg.className = "msg err";
        msg.textContent = (e as Error).message || String(e);
      }
    };
  };
  document.querySelectorAll(".tab").forEach((t) =>
    ((t as HTMLElement).onclick = () => paint((t as HTMLElement).dataset.tab as string)),
  );
  paint("create");
}

function revealMnemonic(mnemonic: string, a: Addresses): void {
  shell(`
    <div class="center">
      <div class="card">
        <div class="label">Back this up</div>
        <h2>Your recovery phrase</h2>
        <p class="soft">Write these words down and keep them safe. They are the only way to restore this wallet. We never see them.</p>
        <div class="mnemonic" id="mn">${mnemonic}</div>
        <div class="actions"><button class="btn" id="cp">Copy phrase</button></div>
        <label class="field" style="margin-top:14px"><span><input type="checkbox" id="ack"> I have saved my recovery phrase</span></label>
        <button class="btn fill big" id="go" disabled>Continue</button>
      </div>
    </div>`);
  (document.getElementById("cp") as HTMLButtonElement).onclick = () => copy(mnemonic);
  const ack = document.getElementById("ack") as HTMLInputElement;
  const go = document.getElementById("go") as HTMLButtonElement;
  ack.onchange = () => (go.disabled = !ack.checked);
  go.onclick = () => {
    addresses = a;
    renderApp();
  };
}

function renderUnlock(): void {
  shell(`
    <div class="center">
      <div class="hero">${brandLogo("xl")}</div>
      <div class="card">
        <div class="label">Welcome back</div>
        <h2>Unlock your wallet</h2>
        <label class="field"><span>Password</span><input id="pw" type="password" placeholder="password" autofocus></label>
        <button class="btn fill big" id="do">Unlock</button>
        <p class="msg" id="msg"></p>
        <p class="fineprint"><a id="forget" href="#">Forget this wallet &amp; start over</a></p>
      </div>
    </div>`);
  const msg = document.getElementById("msg") as HTMLElement;
  const submit = async (): Promise<void> => {
    try {
      addresses = await wallet.unlock((document.getElementById("pw") as HTMLInputElement).value);
      renderApp();
    } catch {
      msg.className = "msg err";
      msg.textContent = "wrong password";
    }
  };
  (document.getElementById("do") as HTMLButtonElement).onclick = submit;
  (document.getElementById("pw") as HTMLInputElement).addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter") submit();
  });
  (document.getElementById("forget") as HTMLElement).onclick = async (e) => {
    e.preventDefault();
    if (confirm("Forget this wallet? Make sure you have your recovery phrase.")) {
      await wallet.forget();
      boot();
    }
  };
}

// ---------------------------------------------------------------- main app (tabbed)
const TABS: [string, string][] = [
  ["wallet", "Wallet"],
  ["send", "Send"],
  ["receive", "Receive"],
  ["txs", "Transactions"],
  ["mining", "Mining"],
  ["host", "Host"],
  ["settings", "Settings"],
];

function renderApp(): void {
  shell(`
    <div class="apptabs">
      ${TABS.map(([id, label]) => `<button class="apptab${id === activeTab ? " on" : ""}" data-t="${id}">${label}</button>`).join("")}
    </div>
    <div id="tabc"></div>`);
  document.querySelectorAll(".apptab").forEach((b) =>
    ((b as HTMLElement).onclick = () => switchTab((b as HTMLElement).dataset.t as string)),
  );
  renderTab();
  refreshBalance();
  if (!balanceTimer) balanceTimer = window.setInterval(refreshBalance, 15000);
  if (!liveTimer) liveTimer = window.setInterval(refreshLive, 4000);
  refreshLive();
}

// Switch tabs WITHOUT rebuilding the shell/topbar, so the animated logo keeps
// playing instead of restarting. Only the tab strip's active state and the tab
// content (#tabc) change.
function switchTab(id: string): void {
  if (id === activeTab) return;
  activeTab = id;
  document.querySelectorAll(".apptab").forEach((b) =>
    (b as HTMLElement).classList.toggle("on", (b as HTMLElement).dataset.t === id),
  );
  renderTab();
  // renderTab paints placeholders ("…"); populate the new tab's data immediately
  // instead of waiting for the next timer tick (both guard on missing elements).
  refreshBalance();
  refreshLive();
}

function renderTab(): void {
  const a = addresses as Addresses;
  const c = document.getElementById("tabc") as HTMLElement;
  if (activeTab === "wallet") {
    c.innerHTML = `
      <div class="card">
        <div class="label">Balance</div>
        <div class="balance"><span id="bal">\u2026</span> <small>ABA</small></div>
        <p class="fineprint">Cosmos bank: <b id="cosbal">\u2026</b> ABA \u00b7 same account, two encodings.</p>
        <div class="addr" style="margin-top:12px"><span class="atype">Cosmos</span><code>${a.aba}</code><span class="copy" data-copy="${a.aba}">copy</span></div>
        <div class="addr" style="margin-top:8px"><span class="atype evm">EVM</span><code>${a.evm}</code><span class="copy" data-copy="${a.evm}">copy</span></div>
        <div class="actions" style="margin-top:12px"><button class="btn" id="refresh">Refresh</button></div>
        <p class="msg" id="walletmsg"></p>
      </div>
      <div class="card">
        <div class="label">Recent activity</div>
        <div id="activity">loading\u2026</div>
        <p class="fineprint" style="margin-top:8px"><a href="#" id="alltxs">All transactions \u2192</a> \u00b7 <a href="${EXPLORER}#acct/${a.aba}">Explorer \u2197</a></p>
      </div>`;
    wireCopy();
    (document.getElementById("refresh") as HTMLButtonElement).onclick = refreshBalance;
    (document.getElementById("alltxs") as HTMLElement).onclick = (e) => {
      e.preventDefault();
      activeTab = "txs";
      renderApp();
    };
    loadActivity();
  } else if (activeTab === "txs") {
    c.innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
          <div><div class="label">Transactions</div><h2>Account history</h2></div>
          <button class="btn" id="txrefresh">Refresh</button>
        </div>
        <div id="txlist"><p class="fineprint">loading\u2026</p></div>
        <div class="actions" style="margin-top:12px"><button class="btn" id="txmore" style="display:none">Show more</button></div>
        <p class="fineprint">Full history: <a href="${EXPLORER}#acct/${a.aba}">account on Explorer \u2197</a> (opens in your browser)</p>
      </div>`;
    setupTxs();
  } else if (activeTab === "send") {
    c.innerHTML = `
      <div class="card">
        <div class="label">Send ABA</div>
        <label class="field"><span>Recipient</span><input id="to" placeholder="abakos1\u2026 or 0x\u2026" autocomplete="off" spellcheck="false"></label>
        <p class="tohint" id="tohint"></p>
        <div id="contacts" class="contacts"></div>
        <label class="field"><span>Amount (ABA) \u00b7 <span class="soft" id="sendbal">\u2026</span><a class="maxbtn" id="sendmax">Max</a></span><input id="amt" type="number" min="0" step="0.000001" placeholder="0.0"></label>
        <div class="actions"><button class="btn fill" id="send">Send</button><button class="btn" id="savec">Save recipient</button></div>
        <div class="saverow" id="saverow" style="display:none"><input id="savename" placeholder="Name for this address" maxlength="40"><button class="btn fill" id="savego">Save</button><button class="btn" id="savecancel">Cancel</button></div>
        <div id="sendresult"></div>
      </div>`;
    setupSend();
  } else if (activeTab === "receive") {
    c.innerHTML = `
      <div class="card" style="text-align:center">
        <div class="label" style="text-align:left">Receive</div>
        <p class="soft" style="text-align:left">Same account, two encodings - share either. Cosmos wallets use <span class="mono">abakos1\u2026</span>, MetaMask/EVM uses <span class="mono">0x\u2026</span>.</p>
        <div class="rtabs"><button class="btn${receiveShowAba ? " fill" : ""}" id="rc-aba">Cosmos (abakos1)</button><button class="btn${receiveShowAba ? "" : " fill"}" id="rc-evm">EVM (0x)</button></div>
        <div id="qr"></div>
        <div class="addr" style="margin-top:12px;text-align:left"><code id="raddr"></code><span class="copy" id="rcopy">copy</span></div>
      </div>`;
    (document.getElementById("rc-aba") as HTMLButtonElement).onclick = () => { receiveShowAba = true; renderTab(); };
    (document.getElementById("rc-evm") as HTMLButtonElement).onclick = () => { receiveShowAba = false; renderTab(); };
    const addr = receiveShowAba ? a.aba : a.evm;
    (document.getElementById("raddr") as HTMLElement).textContent = addr;
    (document.getElementById("rcopy") as HTMLElement).onclick = () => copy(addr);
    const qr = document.getElementById("qr") as HTMLElement;
    const canvas = document.createElement("canvas");
    qr.appendChild(canvas);
    QRCode.toCanvas(canvas, addr, { margin: 1, width: 180 }).catch(() => { qr.textContent = addr; });
  } else if (activeTab === "mining") {
    c.innerHTML = `
      <div class="card" id="miningcard">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
          <div><div class="label">Mining</div><h2>Earn ABA from idle hardware</h2></div>
          <span class="badge off" id="minerbadge"><span class="pulse"></span> stopped</span>
        </div>
        <p class="soft" id="hw">Detecting hardware\u2026</p>
        <label class="field"><span>CPU threads: <b id="thlabel">-</b></span><input type="range" id="threads" min="1" max="1" value="1"></label>
        <label class="field"><span class="toggle"><input type="checkbox" id="gpu"> Use GPU - Pearl (PearlHash; NVIDIA / AMD / Intel Arc)</span></label>
        <button class="btn fill big" id="mine">Start earning</button>
        <div class="stat-grid" style="margin-top:14px">
          <div class="stat"><b id="cpuhs">0 H/s</b><span>CPU \u00b7 Monero (RandomX)</span></div>
          <div class="stat"><b id="gpuhs">0 H/s</b><span>GPU \u00b7 Pearl (PearlHash)</span></div>
          <div class="stat"><b id="vshares">0</b><span>Verified shares (proxy)</span></div>
          <div class="stat"><b id="earned">0</b><span>Earned ABA</span></div>
        </div>
        <p class="fineprint" id="poolline">Pool: -</p>
      </div>
      <div class="card">
        <div class="label">Network</div>
        <div class="stat-grid">
          <div class="stat"><b id="price">-</b><span>ABA price (DEX)</span></div>
          <div class="stat"><b id="basis">-</b><span>Payout basis</span></div>
        </div>
        <p class="fineprint">Split 88% host / 4% stakers / 4% treasury / 4% burn, paid by verified shares. Payouts settle once a day (~13:00 UTC, unMineable auto-withdraw); your shares accrue until then and convert to ABA at settlement.
          <a href="${EXPLORER}">Explorer</a> \u00b7 <a href="${DEX}">DEX</a> \u00b7 <a href="${POOL}">Pool</a></p>
      </div>`;
    setupMining();
    refreshLive();
  } else if (activeTab === "host") {
    c.innerHTML = `
      <div class="card" id="hostcard">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
          <div><div class="label">Host</div><h2>Rent out this machine</h2></div>
          <span class="badge off" id="hostbadge"><span class="pulse"></span> \u2026</span>
        </div>
        <p class="soft" id="hosthint">Checks the local <span class="mono">abakos-provider</span> service (Linux / k3s).</p>
        <div class="addr" style="margin-top:12px"><span class="atype">host_uri</span><code id="hosturi">-</code><span class="copy" id="hosturicopy">copy</span></div>
        <div class="actions" style="margin-top:14px">
          <button class="btn fill big" id="hostbtn">Start hosting</button>
        </div>
        <p class="msg" id="hostmsg"></p>
        <p class="fineprint" id="hostline">Unit: abakos-provider</p>
      </div>
      <div class="card" id="provcard">
        <div class="label">Your provider</div>
        <div id="provbody"><p class="fineprint">loading…</p></div>
      </div>
      <div class="card">
        <div class="label">How hosting works</div>
        <p class="fineprint">Tenants deploy via <a href="https://console.abakos.ai">console.abakos.ai</a>. Your gateway must be publicly reachable (tunnel or public IP on :8443). Compute hosting runs on k3s (Linux containers), so it needs Linux. On Windows, run the provider inside <b>WSL2</b> (Ubuntu) or a Linux VM, then open this tab there to start/stop. Mining (CPU/GPU) works natively on Windows and is independent of hosting.</p>
      </div>`;
    setupHost();
    refreshHost();
    renderProviderDashboard();
  } else if (activeTab === "settings") {
    c.innerHTML = `
      <div class="card">
        <div class="label">Support the project</div>
        <p class="fineprint">Abakos is open source. A GitHub star is the single biggest help - it's how the next person earning on idle hardware finds it.</p>
        <div class="actions" style="margin-top:8px"><button class="btn" id="starbtn">⭐ Star on GitHub</button> <a class="btn" href="https://discord.gg/zBxNvdMjtM">Discord</a></div>
      </div>
      <div class="card">
        <div class="label">Security</div>
        <label class="field"><span>Password (to reveal secrets)</span><input id="spw" type="password" placeholder="password"></label>
        <div class="actions"><button class="btn" id="showkey">Show private key</button><button class="btn" id="showmn">Show recovery phrase</button></div>
        <pre class="mono secretbox" id="secret" style="display:none"></pre>
        <p class="msg" id="setmsg"></p>
        <div class="actions" style="margin-top:8px"><button class="btn" id="lock">Lock wallet</button></div>
      </div>
      <div class="card">
        <div class="label">Address book</div>
        <label class="field"><span>Name</span><input id="bookname" placeholder="e.g. My provider VM" maxlength="40"></label>
        <label class="field" style="margin-top:6px"><span>Address (0x or abakos1)</span><input id="bookaddr" placeholder="0x\u2026 or abakos1\u2026"></label>
        <div class="actions" style="margin-top:8px"><button class="btn" id="booksave">Save address</button></div>
        <p class="msg" id="bookmsg"></p>
        <div id="booklist" class="fineprint" style="margin-top:10px">loading\u2026</div>
      </div>
      <div class="card">
        <div class="label">Appearance</div>
        <h2>Theme</h2>
        <p class="fineprint" style="margin-top:0">Pick a look - it's saved and stays after you reopen the app.</p>
        <div class="themegrid" id="themegrid">
          ${THEMES.map((t) => `<button class="themeswatch" data-theme-id="${t.id}"><span class="themedot" style="background:${t.swatch}"></span>${t.label}</button>`).join("")}
        </div>
      </div>
      <div class="card">
        <div class="label">App</div>
        <p class="fineprint">Version <b id="appver">\u2026</b> \u00b7 updates are downloaded and installed in-app.</p>
        <div class="actions" style="margin-top:8px"><button class="btn" id="checkupd">Check for updates</button></div>
      </div>
      <div class="card">
        <div class="label">Network</div>
        <p class="fineprint">Abakos sandbox \u00b7 EVM chain 9721 \u00b7 <a href="${EXPLORER}">Explorer</a> \u00b7 <a href="${DEX}">DEX</a> \u00b7 <a href="${POOL}">Pool</a></p>
      </div>
      <div class="card warn">
        <div class="label">Danger zone</div>
        <p class="fineprint">Removes this wallet from this device. Make sure you have your recovery phrase or private key.</p>
        <button class="btn danger" id="forget">Forget wallet</button>
      </div>`;
    wireSettings();
  }
}

function wireCopy(): void {
  document.querySelectorAll(".copy[data-copy]").forEach((el) =>
    ((el as HTMLElement).onclick = () => copy((el as HTMLElement).dataset.copy as string)),
  );
}

async function refreshBalance(): Promise<void> {
  const el = document.getElementById("bal");
  if (el) {
    try {
      el.textContent = fmtAba(await wallet.balanceAba());
    } catch {
      el.textContent = "-";
    }
  }
  const cos = document.getElementById("cosbal");
  if (cos) {
    try {
      cos.textContent = fmtAba(await wallet.balanceCosmos());
    } catch {
      cos.textContent = "-";
    }
  }
}

// ---------------------------------------------------------------- transactions
let txCache: TxInfo[] = [];
let txShown = 12;
let bookNames: Map<string, string> = new Map();

async function refreshBookNames(): Promise<void> {
  try {
    bookNames = new Map((await wallet.getContacts()).map((c) => [c.addr, c.name]));
  } catch {
    /* names are cosmetic */
  }
}

function nameFor(addr?: string): string {
  if (!addr) return "";
  return bookNames.get(addr) || short(addr, 8);
}

function txRowHtml(t: TxInfo, compact = false): string {
  const dirCls = t.direction === "in" ? "in" : t.direction === "out" ? "out" : "none";
  const arrow = t.direction === "in" ? "\u2193" : t.direction === "out" ? "\u2191" : "\u00b7";
  const sign = t.direction === "in" ? "+" : t.direction === "out" ? "\u2212" : "";
  const amt = t.amountText ? `${sign}${t.amountText}` : t.amountAba > 0 ? `${sign}${fmtAba(t.amountAba)} ABA` : "";
  const cp = t.counterparty ? `${t.direction === "in" ? "from" : "to"} ${nameFor(t.counterparty)}` : "";
  const when = t.ts ? new Date(t.ts).toLocaleString() : `block ${t.height}`;
  const meta = [cp, when, t.ok ? "" : "FAILED"].filter(Boolean).join(" \u00b7 ");
  return `
    <div class="txrow${t.ok ? "" : " fail"}">
      <span class="txdir ${dirCls}">${arrow}</span>
      <div class="txmain">
        <b>${t.label}${t.account === "provider" ? ' <span class="txsrc">provider</span>' : ""}</b>
        <span>${meta}</span>
      </div>
      <div class="txside">
        <b class="txamt ${dirCls}">${amt}</b>
        ${compact ? "" : `<a class="mono" href="${EXPLORER}#tx/${t.hash}">${short(t.hash, 6)} \u2197</a>`}
      </div>
    </div>`;
}

async function watchedProvider(): Promise<string | null> {
  try {
    return (await kvGet("watch_provider")) || null;
  } catch {
    return null;
  }
}

async function loadActivity(): Promise<void> {
  const el = document.getElementById("activity");
  if (!el || !addresses) return;
  await refreshBookNames();
  txCache = await fetchTxsWithProvider(addresses.aba, await watchedProvider());
  if (!document.getElementById("activity")) return; // tab switched meanwhile
  el.innerHTML = txCache.length
    ? txCache.slice(0, 5).map((t) => txRowHtml(t, true)).join("")
    : `<p class="fineprint">No transactions yet (or indexer unavailable).</p>`;
}

function paintTxList(): void {
  const el = document.getElementById("txlist");
  const more = document.getElementById("txmore") as HTMLButtonElement | null;
  if (!el) return;
  el.innerHTML = txCache.length
    ? txCache.slice(0, txShown).map((t) => txRowHtml(t)).join("")
    : `<p class="fineprint">No transactions found for this account (or indexer unavailable).</p>`;
  if (more) more.style.display = txCache.length > txShown ? "" : "none";
}

async function setupTxs(): Promise<void> {
  const load = async (): Promise<void> => {
    if (!addresses) return;
    await refreshBookNames();
    txCache = await fetchTxsWithProvider(addresses.aba, await watchedProvider(), 50);
    paintTxList();
  };
  (document.getElementById("txrefresh") as HTMLButtonElement).onclick = load;
  (document.getElementById("txmore") as HTMLButtonElement).onclick = () => {
    txShown += 12;
    paintTxList();
  };
  if (txCache.length) paintTxList(); // show cached rows instantly, then refresh
  await load();
}

// --- Send tab -----------------------------------------------------------------
const isValidAddr = (v: string): boolean =>
  /^0x[0-9a-fA-F]{40}$/.test(v) || /^abakos1[0-9a-z]{38,}$/.test(v);

async function setupSend(): Promise<void> {
  const to = document.getElementById("to") as HTMLInputElement;
  if (pendingRecipient) {
    to.value = pendingRecipient;
    pendingRecipient = "";
  }
  to.oninput = updateToHint;
  (document.getElementById("send") as HTMLButtonElement).onclick = doSend;
  (document.getElementById("savec") as HTMLButtonElement).onclick = openSaveRow;
  (document.getElementById("savego") as HTMLButtonElement).onclick = saveContactInline;
  (document.getElementById("savecancel") as HTMLButtonElement).onclick = closeSaveRow;
  (document.getElementById("sendmax") as HTMLElement).onclick = async (e) => {
    e.preventDefault();
    try {
      (document.getElementById("amt") as HTMLInputElement).value = String(await wallet.balanceAba());
    } catch {
      /* ignore */
    }
  };
  await refreshBookNames();
  loadContacts();
  updateToHint();
  refreshSendBalance();
}

async function refreshSendBalance(): Promise<void> {
  const el = document.getElementById("sendbal");
  if (!el) return;
  try {
    el.textContent = `${fmtAba(await wallet.balanceAba())} available`;
  } catch {
    el.textContent = "";
  }
}

function updateToHint(): void {
  const to = (document.getElementById("to") as HTMLInputElement).value.trim();
  const hint = document.getElementById("tohint");
  if (!hint) return;
  if (!to) {
    hint.textContent = "";
    hint.className = "tohint";
  } else if (!isValidAddr(to)) {
    hint.textContent = "Keep typing a full abakos1\u2026 or 0x\u2026 address";
    hint.className = "tohint";
  } else {
    const name = bookNames.get(to);
    hint.textContent = name ? `\u2713 ${name}` : "\u2713 Valid address";
    hint.className = "tohint ok";
  }
}

async function loadContacts(): Promise<void> {
  const el = document.getElementById("contacts");
  if (!el) return;
  const book = await wallet.getContacts();
  if (!book.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = book
    .map((c, i) => `<button class="chip" data-i="${i}" title="${c.addr}">${esc(c.name) || short(c.addr, 6)}</button>`)
    .join("");
  el.querySelectorAll(".chip").forEach((b) =>
    ((b as HTMLElement).onclick = () => {
      (document.getElementById("to") as HTMLInputElement).value = book[Number((b as HTMLElement).dataset.i)].addr;
      updateToHint();
    }),
  );
}

function showSendMsg(text: string, kind: "ok" | "err" | ""): void {
  const el = document.getElementById("sendresult");
  if (el) el.innerHTML = `<p class="msg ${kind}">${text}</p>`;
}

function openSaveRow(): void {
  const to = (document.getElementById("to") as HTMLInputElement).value.trim();
  if (!isValidAddr(to)) {
    showSendMsg("Enter a valid address first.", "err");
    return;
  }
  const name = document.getElementById("savename") as HTMLInputElement;
  name.value = bookNames.get(to) || "";
  (document.getElementById("saverow") as HTMLElement).style.display = "flex";
  name.focus();
}

function closeSaveRow(): void {
  (document.getElementById("saverow") as HTMLElement).style.display = "none";
}

async function saveContactInline(): Promise<void> {
  const to = (document.getElementById("to") as HTMLInputElement).value.trim();
  const name = (document.getElementById("savename") as HTMLInputElement).value.trim();
  if (!isValidAddr(to)) {
    showSendMsg("Enter a valid address first.", "err");
    return;
  }
  if (!name) {
    showSendMsg("Enter a name.", "err");
    return;
  }
  await wallet.addContact(name, to);
  await refreshBookNames();
  closeSaveRow();
  loadContacts();
  updateToHint();
  showSendMsg(`Saved "${esc(name)}".`, "ok");
}

async function doSend(): Promise<void> {
  const to = (document.getElementById("to") as HTMLInputElement).value.trim();
  const amtEl = document.getElementById("amt") as HTMLInputElement;
  const amt = amtEl.value.trim();
  const btn = document.getElementById("send") as HTMLButtonElement;
  const res = document.getElementById("sendresult") as HTMLElement;
  if (!isValidAddr(to)) {
    showSendMsg("Enter a valid abakos1\u2026 or 0x\u2026 address.", "err");
    return;
  }
  const n = Number(amt);
  if (!amt || !Number.isFinite(n) || n <= 0) {
    showSendMsg("Enter an amount greater than 0.", "err");
    return;
  }
  btn.disabled = true;
  res.innerHTML = `<p class="msg">Sending ${fmtAba(n)} ABA\u2026</p>`;
  try {
    const evmHash = await wallet.sendAba(to, amt);
    const name = bookNames.get(to);
    const dest = name ? `"${esc(name)}"` : short(to, 6);
    res.innerHTML = `
      <div class="sent">
        <div class="sent-top"><span class="sent-check">\u2713</span> Sent <b>${fmtAba(n)} ABA</b> to ${dest}</div>
        <div class="addr" style="margin-top:10px"><span class="atype">tx</span><code>${short(evmHash, 8)}</code><span class="copy" data-copy="${evmHash}">copy</span> <a id="sentlink" class="mono" href="${EXPLORER}#acct/${(addresses as Addresses).aba}">Explorer \u2197</a></div>
      </div>`;
    wireCopy();
    amtEl.value = "";
    setTimeout(() => {
      refreshBalance();
      refreshSendBalance();
    }, 2500);
    void upgradeSentLink(evmHash);
  } catch (e) {
    showSendMsg((e as Error).message || String(e), "err");
  } finally {
    btn.disabled = false;
  }
}

// The Explorer indexes by Cosmos hash; sendAba returns the EVM hash. Point the link
// at the account page immediately (always resolves), then upgrade it to the exact tx
// once the wrapping Cosmos tx indexes.
async function upgradeSentLink(evmHash: string): Promise<void> {
  for (let i = 0; i < 6; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const cosmos = await cosmosHashForEvmTx(evmHash);
    if (cosmos) {
      const link = document.getElementById("sentlink") as HTMLAnchorElement | null;
      if (link) link.href = `${EXPLORER}#tx/${cosmos}`;
      return;
    }
  }
}

function sendTo(addr: string): void {
  pendingRecipient = addr;
  switchTab("send");
}

function wireSettings(): void {
  const setmsg = document.getElementById("setmsg") as HTMLElement;
  const secret = document.getElementById("secret") as HTMLElement;
  const pw = (): string => (document.getElementById("spw") as HTMLInputElement).value;
  const reveal = async (fn: () => Promise<string>, label: string): Promise<void> => {
    try {
      const v = await fn();
      secret.style.display = "block";
      secret.textContent = `${label}:\n${v}`;
      setmsg.textContent = "";
    } catch (e) {
      setmsg.className = "msg err";
      setmsg.textContent = (e as Error).message || String(e);
    }
  };
  const starbtn = document.getElementById("starbtn") as HTMLButtonElement | null;
  if (starbtn) starbtn.onclick = () => openUrl("https://github.com/Abakos-ABA/abakos").catch(() => {});
  (document.getElementById("showkey") as HTMLButtonElement).onclick = () =>
    reveal(() => wallet.exportPrivateKey(pw()), "Private key (0x)");
  (document.getElementById("showmn") as HTMLButtonElement).onclick = () =>
    reveal(() => wallet.exportMnemonic(pw()), "Recovery phrase");
  (document.getElementById("lock") as HTMLButtonElement).onclick = () => {
    wallet.lock();
    boot();
  };
  (document.getElementById("forget") as HTMLButtonElement).onclick = async () => {
    if (confirm("Forget this wallet? Make sure you have your recovery phrase or private key.")) {
      await wallet.forget();
      boot();
    }
  };
  const ver = document.getElementById("appver");
  if (ver) getVersion().then((v) => (ver.textContent = v)).catch(() => (ver.textContent = "-"));
  const cu = document.getElementById("checkupd") as HTMLButtonElement | null;
  if (cu) cu.onclick = () => checkForUpdate({ silent: false });
  const booksave = document.getElementById("booksave") as HTMLButtonElement | null;
  if (booksave) {
    booksave.onclick = async () => {
      const bmsg = document.getElementById("bookmsg") as HTMLElement;
      const nameEl = document.getElementById("bookname") as HTMLInputElement;
      const addrEl = document.getElementById("bookaddr") as HTMLInputElement;
      const name = nameEl.value.trim();
      const addr = addrEl.value.trim();
      const valid = /^0x[0-9a-fA-F]{40}$/.test(addr) || /^abakos1[0-9a-z]{38,}$/.test(addr);
      if (!valid) {
        bmsg.className = "msg err";
        bmsg.textContent = "Enter a valid 0x or abakos1 address.";
        return;
      }
      if (!name) {
        bmsg.className = "msg err";
        bmsg.textContent = "Enter a name for this address.";
        return;
      }
      await wallet.addContact(name, addr);
      nameEl.value = "";
      addrEl.value = "";
      bmsg.className = "msg ok";
      bmsg.textContent = "Saved.";
      loadBook();
    };
  }
  wireThemes();
  loadBook();
}

function wireThemes(): void {
  const grid = document.getElementById("themegrid");
  if (!grid) return;
  const active = document.documentElement.dataset.theme || "midnight";
  const mark = (id: string): void =>
    grid.querySelectorAll(".themeswatch").forEach((b) =>
      b.classList.toggle("on", (b as HTMLElement).dataset.themeId === id),
    );
  mark(active);
  grid.querySelectorAll(".themeswatch").forEach((b) =>
    ((b as HTMLElement).onclick = () => {
      const id = (b as HTMLElement).dataset.themeId as string;
      applyTheme(id); // instant, live preview
      mark(id);
      kvSet("theme", id).catch(() => {}); // persist for next launch
    }),
  );
}

async function loadBook(): Promise<void> {
  const el = document.getElementById("booklist");
  if (!el) return;
  const book = await wallet.getContacts();
  if (!book.length) {
    el.innerHTML = `<p class="fineprint">No saved addresses yet - add one above.</p>`;
    return;
  }
  el.innerHTML = book
    .map((c, i) => {
      const initial = (c.name || "?").trim().charAt(0).toUpperCase() || "?";
      return `<div class="bookrow">
        <div class="bookav">${esc(initial)}</div>
        <div class="bookmeta"><b>${esc(c.name) || "(unnamed)"}</b><span class="mono" title="${c.addr}">${short(c.addr, 10)}</span></div>
        <div class="bookact"><span class="copy" data-copy="${c.addr}">copy</span><a data-send="${i}">send</a><a class="rm" data-rm="${i}">remove</a></div>
      </div>`;
    })
    .join("");
  wireCopy();
  el.querySelectorAll("[data-rm]").forEach((a) =>
    ((a as HTMLElement).onclick = async (e) => {
      e.preventDefault();
      await wallet.removeContact(Number((a as HTMLElement).dataset.rm));
      loadBook();
    }),
  );
  el.querySelectorAll("[data-send]").forEach((a) =>
    ((a as HTMLElement).onclick = (e) => {
      e.preventDefault();
      sendTo(book[Number((a as HTMLElement).dataset.send)].addr);
    }),
  );
}

// ---------------------------------------------------------------- mining
let mineHardwareThreads = 1;
let mining_ = false;
let hwOs = "";
let lastReportMs = 0;
let applyingChange = false;

async function setupMining(): Promise<void> {
  const hw = document.getElementById("hw") as HTMLElement;
  const range = document.getElementById("threads") as HTMLInputElement;
  const thlabel = document.getElementById("thlabel") as HTMLElement;
  const gpu = document.getElementById("gpu") as HTMLInputElement;

  // Wire the controls immediately so the tab is usable even while hardware is being
  // detected. Changing threads/GPU while mining restarts with the new settings;
  // while stopped it just updates what the next start will use. `touched` prevents a
  // late-resolving detection from overwriting a value the user just set.
  let touched = false;
  thlabel.textContent = range.value;
  range.oninput = () => { touched = true; thlabel.textContent = range.value; };
  range.onchange = () => { touched = true; thlabel.textContent = range.value; applyMiningChange(); };
  gpu.onchange = () => { touched = true; applyMiningChange(); };
  (document.getElementById("mine") as HTMLButtonElement).onclick = toggleMining;

  // Reflect an already-running miner (fast, no blocking).
  try {
    const st = await mining.minerStatus();
    mining_ = st.state === "running" || st.state === "starting";
    paintMineButton();
  } catch {
    /* ignore */
  }

  // Last-used settings (persisted), so the tab shows real values whether or not the
  // miner is currently running -- falling back to hardware-based defaults.
  const savedThreadsRaw = await kvGet("mine_threads");
  const savedThreads = Number(savedThreadsRaw || 0);
  const savedGpu = (await kvGet("mine_gpu")) === "1";
  const hasSaved = savedThreadsRaw !== null && savedThreads > 0;

  // Hardware detection is async in the core (off the main thread) so this await does
  // not freeze the app. Then populate the slider + GPU from saved prefs or defaults.
  try {
    const info = await mining.hardwareInfo();
    mineHardwareThreads = Math.max(1, info.cpu_threads);
    hwOs = `${info.os}/${info.arch}`;
    hw.textContent = `${info.os}/${info.arch} \u00b7 ${info.cpu_threads} CPU threads \u00b7 GPU: ${info.has_nvidia ? "NVIDIA detected" : "detect on start"}`;
    range.max = String(mineHardwareThreads);
    if (!touched) {
      const val = hasSaved ? Math.min(savedThreads, mineHardwareThreads) : Math.max(1, Math.floor(mineHardwareThreads / 2));
      range.value = String(val);
      thlabel.textContent = range.value;
      gpu.checked = hasSaved ? savedGpu : info.has_nvidia;
    }
    gpu.disabled = false;
  } catch {
    hw.textContent = "hardware detection unavailable";
    gpu.disabled = false;
  }
}

// Remember the user's mining choices so the tab reloads them next time.
async function savePrefs(threads: number, gpuOn: boolean): Promise<void> {
  try {
    await kvSet("mine_threads", String(threads));
    await kvSet("mine_gpu", gpuOn ? "1" : "0");
  } catch {
    /* prefs are best-effort */
  }
}

// Live-apply a threads/GPU change: if mining, restart the miner with the new
// settings; if stopped, it simply takes effect on the next Start.
async function applyMiningChange(): Promise<void> {
  const range = document.getElementById("threads") as HTMLInputElement;
  const gpuOn = (document.getElementById("gpu") as HTMLInputElement).checked;
  savePrefs(Number(range.value), gpuOn); // remember even while stopped
  if (!mining_ || applyingChange || !addresses) return;
  applyingChange = true;
  const pool = document.getElementById("poolline");
  if (pool) pool.textContent = "Applying new settings\u2026";
  try {
    await mining.stopMiner();
    await new Promise((r) => setTimeout(r, 400));
    await mining.startMiner(addresses.aba, Number(range.value), true, gpuOn);
    mining_ = true;
    paintMineButton();
  } catch (e) {
    if (pool) pool.textContent = "error: " + ((e as Error).message || String(e));
  } finally {
    applyingChange = false;
    refreshLive();
  }
}

function paintMineButton(): void {
  const btn = document.getElementById("mine") as HTMLButtonElement | null;
  if (btn) {
    btn.textContent = mining_ ? "Stop" : "Start earning";
    btn.classList.toggle("fill", !mining_);
    btn.classList.toggle("danger", mining_);
  }
}

async function toggleMining(): Promise<void> {
  const a = addresses as Addresses;
  const range = document.getElementById("threads") as HTMLInputElement;
  try {
    if (mining_) {
      await mining.stopMiner();
      mining_ = false;
      // Tell the pool immediately that we stopped, so it doesn't show a stale hashrate.
      reportStats({ address: a.aba, cpu_hashrate_hs: 0, gpu_hashrate_hs: 0, cpu_coin: "Monero", gpu_coin: "Pearl", miner: "abakos-app", os: hwOs });
    } else {
      const gpuOn = (document.getElementById("gpu") as HTMLInputElement).checked;
      // One-time: let the miner past Windows Defender via a single UAC prompt.
      if ((await kvGet("defender_ok")) !== "1") {
        const pool = document.getElementById("poolline");
        if (pool) pool.textContent = "Allowing mining - please accept the Windows prompt\u2026";
        try {
          await enableMining();
          await kvSet("defender_ok", "1");
        } catch {
          /* user may have declined; try mining anyway */
        }
      }
      await mining.startMiner(a.aba, Number(range.value), true, gpuOn);
      savePrefs(Number(range.value), gpuOn);
      mining_ = true;
    }
    paintMineButton();
    refreshLive();
  } catch (e) {
    const pool = document.getElementById("poolline");
    if (pool) pool.textContent = "error: " + ((e as Error).message || String(e));
  }
}

// Report live CPU+GPU hashrate to the agent (every ~25s while running) so the pool
// page shows this rig's per-device stats. Display only; never affects payouts.
async function maybeReport(miner: mining.MinerStatus): Promise<void> {
  if (!addresses || miner.state !== "running") return;
  const now = Date.now();
  if (now - lastReportMs < 25000) return;
  lastReportMs = now;
  await reportStats({
    address: addresses.aba,
    cpu_hashrate_hs: miner.cpu_hashrate || 0,
    gpu_hashrate_hs: miner.gpu_hashrate || 0,
    cpu_coin: "Monero",
    gpu_coin: "Pearl",
    miner: "abakos-app",
    os: hwOs,
  });
}

async function refreshLive(): Promise<void> {
  if (!addresses) return;
  let live;
  try {
    live = await mining.fetchLive(addresses.aba);
  } catch {
    return;
  }
  const { miner, agent, provider } = live;
  mining_ = miner.state === "running" || miner.state === "starting";
  paintMineButton();
  maybeReport(miner);

  const badge = document.getElementById("minerbadge");
  if (badge) {
    const running = miner.state === "running";
    badge.className = "badge " + (running ? "live" : "off");
    badge.innerHTML = `<span class="pulse"></span> ${miner.state}`;
  }
  const set = (id: string, v: string): void => {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
  };
  set("cpuhs", fmtHs(miner.cpu_hashrate) + (miner.shares_good ? ` \u00b7 ${miner.shares_good} sh` : ""));
  set("gpuhs", fmtHs(miner.gpu_hashrate) + (miner.gpu_shares_good ? ` \u00b7 ${miner.gpu_shares_good} sh` : ""));
  set("poolline", `CPU: ${miner.pool}${miner.cpu_running ? " \u25cf" : ""} \u00b7 GPU: ${miner.pool}${miner.gpu_running ? " \u25cf" : ""}${miner.error ? " \u00b7 " + miner.error : ""}`);
  set("vshares", provider ? fmtAba(provider.window_shares) : "0");
  set("earned", provider ? fmtAba(provider.earned_aba) + " ABA" : "0 ABA");
  if (agent) {
    set("price", "$" + Number(agent.aba_price_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 6 }));
    const b = agent.payout_basis?.source;
    set("basis", b === "proxy-shares" ? "verified shares" : b || "-");
  }
  if (activeTab === "host") refreshHost();
}

// ---------------------------------------------------------------- host (compute provider)
let hosting_ = false;

// Lease-income earnings from the provider account's tx history (in-direction "lease" txs).
function computeEarnings(txs: TxInfo[]): { d7: number; d30: number; perDay: number } {
  const now = Date.now();
  let d7 = 0;
  let d30 = 0;
  for (const t of txs) {
    if (t.direction !== "in" || !/lease/i.test(t.label)) continue;
    const age = t.ts ? now - new Date(t.ts).getTime() : Infinity;
    if (age <= 7 * 864e5) d7 += t.amountAba;
    if (age <= 30 * 864e5) d30 += t.amountAba;
  }
  return { d7, d30, perDay: d30 > 0 ? d30 / 30 : d7 > 0 ? d7 / 7 : 0 };
}

// Unified provider dashboard. The wallet (this app) and the on-chain provider
// account are DIFFERENT addresses; this shows the provider's holdings, active
// leases and earnings, plus the optional wallet sponsorship of its bid deposits.
async function renderProviderDashboard(): Promise<void> {
  const body = document.getElementById("provbody");
  if (!body || !addresses) return;
  let provs: { owner: string; host_uri: string }[] = [];
  try {
    provs = await chainProviders();
  } catch {
    /* ignore */
  }
  const walletAddr = addresses.aba;
  const provider = provs.find((p) => p.owner === walletAddr) || provs[0];
  if (!provider) {
    body.innerHTML = `<p class="fineprint">No compute provider is registered on-chain yet. Start hosting above and run the one-time registration, then it shows up here. Each bid escrows ${BID_DEPOSIT_ABA} ABA as a refundable deposit.</p>`;
    return;
  }
  const provAddr = provider.owner;
  const isSelf = provAddr === walletAddr;
  if (!isSelf) void kvSet("watch_provider", provAddr); // surface its bids/earnings in Transactions

  const [provBal, walletBal, leases, txs, limit, res] = await Promise.all([
    cosmosBalanceAba(provAddr).catch(() => 0),
    wallet.balanceCosmos().catch(() => 0),
    activeLeases(provAddr).catch(() => ({ count: 0, owners: [] as string[] })),
    fetchTxs(provAddr, 100).catch(() => [] as TxInfo[]),
    isSelf ? Promise.resolve(0) : wallet.hostingLimitAba(provAddr).catch(() => 0),
    providerResources().catch(() => null),
  ]);
  const earn = computeEarnings(txs);
  const sponsored = (limit ?? 0) > 0;
  const fundBal = sponsored ? (limit as number) : provBal;
  const capacity = Math.max(0, Math.floor(fundBal / BID_DEPOSIT_ABA));
  const renting = leases.count;

  const sponsor = isSelf
    ? `<p class="fineprint">This wallet <b>is</b> the provider account, so bid deposits come from its own balance. Keep at least ${BID_DEPOSIT_ABA + 1} ABA here so it keeps bidding.</p>`
    : `
      <div class="provsub">Sponsor from your wallet (optional)</div>
      <p class="fineprint">Let <b>your wallet</b> cover the provider's ${BID_DEPOSIT_ABA} ABA bid deposits, capped and revolving (freed when each bid or lease closes). The provider key then holds nothing.</p>
      <p class="fineprint">Your wallet: <span class="mono">${short(walletAddr, 10)}</span> · ${fmtAba(walletBal)} ABA</p>
      <label class="field" style="margin-top:8px"><span>Max ABA for hosting (spend cap)</span>
        <input type="number" id="sponsormax" min="${BID_DEPOSIT_ABA}" step="${BID_DEPOSIT_ABA}" value="${sponsored ? Math.round(limit as number) : 25}" inputmode="numeric"></label>
      <div class="actions" style="margin-top:10px">
        <button class="btn fill" id="sponsorbtn">${sponsored ? "Update limit" : "Activate sponsorship"}</button>
        ${sponsored ? '<button class="btn danger" id="sponsorrevoke">Revoke</button>' : ""}
      </div>
      <p class="msg ${sponsored ? "ok" : ""}" id="sponsormsg">${sponsored ? `Active · up to ${fmtAba(limit as number)} ABA sponsored (revolving).` : ""}</p>`;

  body.innerHTML = `
    <p class="fineprint">Two accounts are involved: <b>your wallet</b> (this app) and the <b>provider account</b> below. They are different on-chain addresses; the provider is the operator key the daemon signs with.</p>
    <div class="provsub">Provider account (on-chain, earns lease income)</div>
    <div class="addr"><span class="atype">provider</span><code>${provAddr}</code><span class="copy" data-copy="${provAddr}">copy</span></div>
    <div class="provstats">
      <div class="pstat"><b>${fmtAba(provBal)}</b><span>ABA held</span></div>
      <div class="pstat"><b>${renting}</b><span>active lease${renting === 1 ? "" : "s"}</span></div>
      <div class="pstat"><b>~${capacity}</b><span>bids fundable</span></div>
    </div>
    ${
      res
        ? `<div class="provsub">Resources free / total</div>
    <div class="provstats">
      <div class="pstat"><b>${res.cpuFree.toFixed(1)}</b><span>of ${res.cpuTotal.toFixed(0)} CPU cores free</span></div>
      <div class="pstat"><b>${res.memFree.toFixed(1)}</b><span>of ${res.memTotal.toFixed(0)} GB RAM free</span></div>
      <div class="pstat"><b>${res.storFree.toFixed(0)}</b><span>of ${res.storTotal.toFixed(0)} GB disk free</span></div>
      ${res.gpuTotal > 0 ? `<div class="pstat"><b>${res.gpuFree}</b><span>of ${res.gpuTotal} GPU free</span></div>` : ""}
    </div>`
        : ""
    }
    <div class="provsub">Earnings (lease payouts)</div>
    <div class="provstats">
      <div class="pstat"><b>${fmtAba(earn.d7)}</b><span>last 7 days</span></div>
      <div class="pstat"><b>${fmtAba(earn.d30)}</b><span>last 30 days</span></div>
      <div class="pstat"><b>~${fmtAba(earn.perDay)}</b><span>ABA / day</span></div>
      <div class="pstat"><b>~${fmtAba(earn.perDay * 30)}</b><span>ABA / month</span></div>
    </div>
    <p class="fineprint">Per-day/month are estimates from the last 30 days of lease payouts. Each bid escrows ${BID_DEPOSIT_ABA} ABA as a refundable deposit, returned when the bid or lease closes.</p>
    ${sponsor}`;

  wireCopy();
  if (isSelf) return;

  const g = provAddr;
  const msg = document.getElementById("sponsormsg") as HTMLElement;
  const btn = document.getElementById("sponsorbtn") as HTMLButtonElement | null;
  if (btn) {
    btn.onclick = async () => {
      const max = Number((document.getElementById("sponsormax") as HTMLInputElement).value);
      if (!Number.isFinite(max) || max < BID_DEPOSIT_ABA) {
        msg.className = "msg err";
        msg.textContent = `Enter at least ${BID_DEPOSIT_ABA} ABA.`;
        return;
      }
      if (!wallet.isUnlocked()) {
        msg.className = "msg err";
        msg.textContent = "Unlock your wallet first.";
        return;
      }
      btn.disabled = true;
      msg.className = "msg";
      msg.textContent = "Signing grant…";
      try {
        const hash = await wallet.grantHosting(g, max);
        msg.className = "msg ok";
        msg.textContent = `Sponsorship set to ${max} ABA · ${hash.slice(0, 10)}…`;
        setTimeout(() => void renderProviderDashboard(), 3000);
      } catch (e) {
        msg.className = "msg err";
        msg.textContent = (e as Error).message || String(e);
      } finally {
        btn.disabled = false;
      }
    };
  }
  const rev = document.getElementById("sponsorrevoke") as HTMLButtonElement | null;
  if (rev) {
    rev.onclick = async () => {
      if (!wallet.isUnlocked()) {
        msg.className = "msg err";
        msg.textContent = "Unlock your wallet first.";
        return;
      }
      rev.disabled = true;
      msg.className = "msg";
      msg.textContent = "Revoking…";
      try {
        const hash = await wallet.revokeHosting(g);
        msg.className = "msg ok";
        msg.textContent = `Revoked · ${hash.slice(0, 10)}…`;
        setTimeout(() => void renderProviderDashboard(), 3000);
      } catch (e) {
        msg.className = "msg err";
        msg.textContent = (e as Error).message || String(e);
      } finally {
        rev.disabled = false;
      }
    };
  }
}

async function setupHost(): Promise<void> {
  (document.getElementById("hostbtn") as HTMLButtonElement).onclick = toggleHost;
  renderProviderDashboard();
  const uriCopy = document.getElementById("hosturicopy");
  if (uriCopy) {
    uriCopy.onclick = () => {
      const u = (document.getElementById("hosturi") as HTMLElement)?.textContent || "";
      if (u && u !== "-") void copy(u);
    };
  }
  try {
    const st = await host.providerDaemonStatus();
    hosting_ = st.state === "running" || st.state === "starting";
    paintHostButton();
  } catch {
    /* ignore */
  }
}

function paintHostButton(): void {
  const btn = document.getElementById("hostbtn") as HTMLButtonElement | null;
  if (!btn) return;
  btn.textContent = hosting_ ? "Stop hosting" : "Start hosting";
  btn.classList.toggle("fill", !hosting_);
  btn.classList.toggle("danger", hosting_);
  btn.disabled = false;
}

async function toggleHost(): Promise<void> {
  const msg = document.getElementById("hostmsg") as HTMLElement | null;
  try {
    if (hosting_) {
      await host.stopProvider();
      hosting_ = false;
    } else {
      await host.startProvider();
      hosting_ = true;
    }
    paintHostButton();
    if (msg) {
      msg.className = "msg ok";
      msg.textContent = hosting_ ? "provider starting\u2026" : "provider stopped";
    }
    refreshHost();
  } catch (e) {
    if (msg) {
      msg.className = "msg err";
      msg.textContent = (e as Error).message || String(e);
    }
  }
}

async function refreshHost(): Promise<void> {
  if (!addresses) return;
  let live;
  try {
    live = await host.fetchHostLive(addresses.aba);
  } catch {
    return;
  }
  const { daemon, chainHostUri } = live;
  hosting_ = daemon.state === "running" || daemon.state === "starting";
  paintHostButton();

  const badge = document.getElementById("hostbadge");
  if (badge) {
    const liveState = daemon.state === "running";
    badge.className = "badge " + (liveState ? "live" : "off");
    badge.innerHTML = `<span class="pulse"></span> ${daemon.state}`;
  }
  const uri = chainHostUri || daemon.host_uri || "-";
  const uriEl = document.getElementById("hosturi");
  if (uriEl) uriEl.textContent = uri;

  const hint = document.getElementById("hosthint");
  if (hint) {
    if (!daemon.platform_ok) {
      hint.textContent =
        "This machine can't run the provider daemon (it needs Linux). Open Abakos on your Linux host to start or stop it. See How hosting works below.";
    } else if (daemon.error) {
      hint.textContent = daemon.error;
    } else {
      hint.innerHTML =
        "Local unit <span class=\"mono\">" +
        (daemon.unit || "abakos-provider") +
        "</span> \u00b7 tenants reach you via the on-chain host_uri.";
    }
  }
  const line = document.getElementById("hostline");
  if (line) {
    const parts = [`Local unit: ${daemon.unit || "abakos-provider"} \u00b7 ${daemon.state}`];
    if (daemon.error) parts.push(daemon.error);
    line.textContent = parts.join(" \u00b7 ");
  }
  const btn = document.getElementById("hostbtn") as HTMLButtonElement | null;
  if (btn && !daemon.platform_ok) {
    btn.disabled = true;
    btn.textContent = "Hosting needs Linux";
    btn.classList.remove("fill", "danger");
  }
}

// Apply the saved theme before the first render (avoids a flash of the default),
// then boot the app.
initTheme().finally(boot);
// Check for a newer signed release shortly after launch (silent if up to date).
setTimeout(() => { checkForUpdate({ silent: true }).catch(() => {}); }, 1500);
