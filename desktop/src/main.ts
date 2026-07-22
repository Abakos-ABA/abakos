import QRCode from "qrcode";
import * as wallet from "./wallet";
import type { Addresses } from "./wallet";
import * as mining from "./mining";
import { EXPLORER, DEX, enableMining, kvGet, kvSet, recentTxs, reportStats } from "./net";
import { checkForUpdate } from "./update";
import { getVersion } from "@tauri-apps/api/app";

const POOL = "https://pool.abakos.ai/";

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
      <div class="brand"><span class="dot"></span> Abakos Provider</div>
      <span class="badge off" id="netbadge"><span class="pulse"></span> sandbox</span>
    </div>
    <div class="wrap">${inner}</div>`;
}

function renderOnboarding(): void {
  shell(`
    <div class="center">
      <div class="card">
        <div class="label">Welcome</div>
        <h2>Set up your ABA wallet</h2>
        <p class="soft">One wallet earns your mining payouts and holds your ABA. Sandbox only &mdash; ABA has no value here.</p>
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
  ["mining", "Mining"],
  ["settings", "Settings"],
];

function renderApp(): void {
  shell(`
    <div class="apptabs">
      ${TABS.map(([id, label]) => `<button class="apptab${id === activeTab ? " on" : ""}" data-t="${id}">${label}</button>`).join("")}
    </div>
    <div id="tabc"></div>`);
  document.querySelectorAll(".apptab").forEach((b) =>
    ((b as HTMLElement).onclick = () => {
      activeTab = (b as HTMLElement).dataset.t as string;
      renderApp();
    }),
  );
  renderTab();
  refreshBalance();
  if (!balanceTimer) balanceTimer = window.setInterval(refreshBalance, 15000);
  if (!liveTimer) liveTimer = window.setInterval(refreshLive, 4000);
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
        <div class="actions" style="margin-top:12px"><button class="btn" id="refresh">Refresh</button><button class="btn fill" id="faucet">Get test ABA</button></div>
        <p class="msg" id="walletmsg"></p>
      </div>
      <div class="card">
        <div class="label">Recent activity</div>
        <div id="activity" class="fineprint">loading\u2026</div>
        <p class="fineprint" style="margin-top:8px"><a href="${EXPLORER}#acct/${a.aba}">View account on Explorer \u2192</a></p>
      </div>`;
    wireCopy();
    (document.getElementById("refresh") as HTMLButtonElement).onclick = refreshBalance;
    (document.getElementById("faucet") as HTMLButtonElement).onclick = doFaucet;
    loadActivity();
  } else if (activeTab === "send") {
    c.innerHTML = `
      <div class="card">
        <div class="label">Send ABA</div>
        <label class="field"><span>Recipient (abakos1\u2026 or 0x\u2026)</span><input id="to" placeholder="abakos1\u2026 or 0x\u2026"></label>
        <div id="contacts" class="contacts"></div>
        <label class="field"><span>Amount (ABA)</span><input id="amt" type="number" min="0" step="0.000001" placeholder="1.0"></label>
        <div class="actions"><button class="btn fill" id="send">Send</button><button class="btn" id="savec">Save recipient</button></div>
        <p class="msg" id="sendmsg"></p>
      </div>`;
    (document.getElementById("send") as HTMLButtonElement).onclick = doSend;
    (document.getElementById("savec") as HTMLButtonElement).onclick = saveContact;
    loadContacts();
  } else if (activeTab === "receive") {
    c.innerHTML = `
      <div class="card" style="text-align:center">
        <div class="label" style="text-align:left">Receive</div>
        <p class="soft" style="text-align:left">Same account, two encodings \u2014 share either. Cosmos wallets use <span class="mono">abakos1\u2026</span>, MetaMask/EVM uses <span class="mono">0x\u2026</span>.</p>
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
        <label class="field"><span>CPU threads: <b id="thlabel">\u2013</b></span><input type="range" id="threads" min="1" max="1" value="1"></label>
        <label class="field"><span class="toggle"><input type="checkbox" id="gpu"> Use GPU \u2014 Pearl (PearlHash; NVIDIA / AMD / Intel Arc)</span></label>
        <button class="btn fill big" id="mine">Start earning</button>
        <div class="stat-grid" style="margin-top:14px">
          <div class="stat"><b id="cpuhs">0 H/s</b><span>CPU \u00b7 Monero (RandomX)</span></div>
          <div class="stat"><b id="gpuhs">0 H/s</b><span>GPU \u00b7 Pearl (PearlHash)</span></div>
          <div class="stat"><b id="vshares">0</b><span>Verified shares (proxy)</span></div>
          <div class="stat"><b id="earned">0</b><span>Earned ABA</span></div>
        </div>
        <p class="fineprint" id="poolline">Pool: \u2013</p>
      </div>
      <div class="card">
        <div class="label">Network</div>
        <div class="stat-grid">
          <div class="stat"><b id="price">\u2013</b><span>ABA price (DEX)</span></div>
          <div class="stat"><b id="basis">\u2013</b><span>Payout basis</span></div>
        </div>
        <p class="fineprint">Split 88% host / 4% stakers / 4% treasury / 4% burn, paid by verified shares.
          <a href="${EXPLORER}">Explorer</a> \u00b7 <a href="${DEX}">DEX</a> \u00b7 <a href="${POOL}">Pool</a></p>
      </div>`;
    setupMining();
    refreshLive();
  } else if (activeTab === "settings") {
    c.innerHTML = `
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
        <div id="booklist" class="fineprint">loading\u2026</div>
      </div>
      <div class="card warn">
        <div class="label">Danger zone</div>
        <p class="fineprint">Removes this wallet from this device. Make sure you have your recovery phrase or private key.</p>
        <button class="btn danger" id="forget">Forget wallet</button>
      </div>
      <div class="card">
        <div class="label">App</div>
        <p class="fineprint">Version <b id="appver">\u2026</b> \u00b7 updates are downloaded and installed in-app.</p>
        <div class="actions" style="margin-top:8px"><button class="btn" id="checkupd">Check for updates</button></div>
      </div>
      <div class="card">
        <div class="label">Network</div>
        <p class="fineprint">Abakos sandbox \u00b7 EVM chain 9721 \u00b7 <a href="${EXPLORER}">Explorer</a> \u00b7 <a href="${DEX}">DEX</a> \u00b7 <a href="${POOL}">Pool</a></p>
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
      el.textContent = "\u2013";
    }
  }
  const cos = document.getElementById("cosbal");
  if (cos) {
    try {
      cos.textContent = fmtAba(await wallet.balanceCosmos());
    } catch {
      cos.textContent = "\u2013";
    }
  }
}

async function doFaucet(): Promise<void> {
  const msg = document.getElementById("walletmsg") as HTMLElement;
  msg.className = "msg";
  msg.textContent = "requesting test ABA\u2026";
  try {
    const tx = await wallet.faucet();
    msg.className = "msg ok";
    msg.innerHTML = `faucet sent \u00b7 <a href="${EXPLORER}#tx/${tx}">${short(tx)}</a>`;
    setTimeout(refreshBalance, 4000);
  } catch (e) {
    msg.className = "msg err";
    msg.textContent = (e as Error).message || String(e);
  }
}

async function loadActivity(): Promise<void> {
  const el = document.getElementById("activity");
  if (!el || !addresses) return;
  const rows = await recentTxs(addresses.aba);
  el.innerHTML = rows.length
    ? rows
        .map((r) => `<div class="actrow"><a class="mono" href="${EXPLORER}#tx/${r.hash}">${short(r.hash, 8)}</a> <span class="mut">block ${r.height}${r.ts ? " \u00b7 " + new Date(r.ts).toLocaleString() : ""}</span></div>`)
        .join("")
    : "No recent sends found (or indexer unavailable). Use the Explorer link below.";
}

async function loadContacts(): Promise<void> {
  const el = document.getElementById("contacts");
  if (!el) return;
  const book = await wallet.getContacts();
  el.innerHTML = book.length
    ? book.map((c) => `<button class="chip" data-addr="${c.addr}">${c.name || short(c.addr, 8)}</button>`).join("")
    : "";
  el.querySelectorAll(".chip").forEach((b) =>
    ((b as HTMLElement).onclick = () => {
      (document.getElementById("to") as HTMLInputElement).value = (b as HTMLElement).dataset.addr as string;
    }),
  );
}

async function saveContact(): Promise<void> {
  const to = (document.getElementById("to") as HTMLInputElement).value.trim();
  if (!to) return;
  const name = prompt("Name for this address?", short(to, 8)) || "";
  await wallet.addContact(name, to);
  loadContacts();
}

async function doSend(): Promise<void> {
  const msg = document.getElementById("sendmsg") as HTMLElement;
  const to = (document.getElementById("to") as HTMLInputElement).value;
  const amt = (document.getElementById("amt") as HTMLInputElement).value;
  if (!to || !amt) {
    msg.className = "msg err";
    msg.textContent = "enter a recipient and amount";
    return;
  }
  msg.className = "msg";
  msg.textContent = "sending\u2026";
  try {
    const tx = await wallet.sendAba(to, amt);
    msg.className = "msg ok";
    msg.innerHTML = `sent \u00b7 <a href="${EXPLORER}#tx/${tx}">${short(tx)}</a>`;
    setTimeout(refreshBalance, 2500);
  } catch (e) {
    msg.className = "msg err";
    msg.textContent = (e as Error).message || String(e);
  }
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
  if (ver) getVersion().then((v) => (ver.textContent = v)).catch(() => (ver.textContent = "\u2013"));
  const cu = document.getElementById("checkupd") as HTMLButtonElement | null;
  if (cu) cu.onclick = () => checkForUpdate({ silent: false });
  loadBook();
}

async function loadBook(): Promise<void> {
  const el = document.getElementById("booklist");
  if (!el) return;
  const book = await wallet.getContacts();
  el.innerHTML = book.length
    ? book
        .map((c, i) => `<div class="actrow"><b>${c.name || "(unnamed)"}</b> <span class="mono">${short(c.addr, 10)}</span> <a href="#" data-rm="${i}">remove</a></div>`)
        .join("")
    : "No saved addresses yet. Save recipients from the Send tab.";
  el.querySelectorAll("[data-rm]").forEach((a) =>
    ((a as HTMLElement).onclick = async (e) => {
      e.preventDefault();
      await wallet.removeContact(Number((a as HTMLElement).dataset.rm));
      loadBook();
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
        if (pool) pool.textContent = "Allowing mining \u2014 please accept the Windows prompt\u2026";
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
  set("cpuhs", fmtHs(miner.cpu_hashrate));
  set("gpuhs", fmtHs(miner.gpu_hashrate) + (miner.gpu_shares_good ? ` \u00b7 ${miner.gpu_shares_good} sh` : ""));
  set("poolline", `CPU: ${miner.pool}${miner.cpu_running ? " \u25cf" : ""} \u00b7 GPU: prl.kryptex.network:7048${miner.gpu_running ? " \u25cf" : ""}${miner.error ? " \u00b7 " + miner.error : ""}`);
  set("vshares", provider ? fmtAba(provider.window_shares) : "0");
  set("earned", provider ? fmtAba(provider.earned_aba) + " ABA" : "0 ABA");
  if (agent) {
    set("price", "$" + Number(agent.aba_price_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 6 }));
    const b = agent.payout_basis?.source;
    set("basis", b === "proxy-shares" ? "verified shares" : b || "\u2013");
  }
}

boot();
// Check for a newer signed release shortly after launch (silent if up to date).
setTimeout(() => { checkForUpdate({ silent: true }).catch(() => {}); }, 1500);
