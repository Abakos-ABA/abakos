import QRCode from "qrcode";
import * as wallet from "./wallet";
import type { Addresses } from "./wallet";
import * as mining from "./mining";
import { EXPLORER, DEX } from "./net";

const app = document.getElementById("app") as HTMLElement;

const fmtHs = (h: number): string => {
  h = Number(h || 0);
  if (h >= 1e9) return (h / 1e9).toFixed(2) + " GH/s";
  if (h >= 1e6) return (h / 1e6).toFixed(2) + " MH/s";
  if (h >= 1e3) return (h / 1e3).toFixed(2) + " kH/s";
  return Math.round(h) + " H/s";
};
const fmtAba = (n: number): string =>
  Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 6 });
const short = (s: string, n = 10): string => (s.length > 2 * n ? s.slice(0, n) + "\u2026" + s.slice(-6) : s);

let addresses: Addresses | null = null;
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

// ---------------------------------------------------------------- main app
function renderApp(): void {
  const a = addresses as Addresses;
  shell(`
    <div class="topbar-inline"></div>
    <div class="grid">
      <div class="card" id="walletcard">
        <div class="label">Wallet</div>
        <div class="balance"><span id="bal">\u2026</span> <small>ABA</small></div>
        <div class="addr" style="margin-top:12px"><code id="aba">${a.aba}</code><span class="copy" data-copy="${a.aba}">copy</span></div>
        <div class="addr" style="margin-top:8px"><code id="evm">${a.evm}</code><span class="copy" data-copy="${a.evm}">copy</span></div>
        <div class="actions" style="margin-top:12px">
          <button class="btn" id="refresh">Refresh</button>
          <button class="btn" id="lock">Lock</button>
        </div>
      </div>

      <div class="card" id="receivecard">
        <div class="label">Receive</div>
        <h2>Your deposit address</h2>
        <p class="soft">Same account on Cosmos (<span class="mono">abakos1\u2026</span>) and the EVM (<span class="mono">0x\u2026</span>).</p>
        <div id="qr"></div>
      </div>
    </div>

    <div class="card">
      <div class="label">Send ABA</div>
      <div class="row">
        <label class="field"><span>Recipient (abakos1\u2026 or 0x\u2026)</span><input id="to" placeholder="abakos1\u2026 or 0x\u2026"></label>
        <label class="field" style="max-width:200px"><span>Amount (ABA)</span><input id="amt" type="number" min="0" step="0.000001" placeholder="1.0"></label>
      </div>
      <button class="btn fill" id="send">Send</button>
      <p class="msg" id="sendmsg"></p>
    </div>

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
        <a href="${EXPLORER}" id="exlink">Explorer</a> \u00b7 <a href="${DEX}" id="dexlink">DEX</a></p>
    </div>`);

  // wallet actions
  document.querySelectorAll(".copy").forEach((c) =>
    ((c as HTMLElement).onclick = () => copy((c as HTMLElement).dataset.copy as string)),
  );
  (document.getElementById("refresh") as HTMLButtonElement).onclick = refreshBalance;
  (document.getElementById("lock") as HTMLButtonElement).onclick = () => {
    wallet.lock();
    boot();
  };
  (document.getElementById("send") as HTMLButtonElement).onclick = doSend;

  // QR
  const qr = document.getElementById("qr") as HTMLElement;
  const canvas = document.createElement("canvas");
  qr.appendChild(canvas);
  QRCode.toCanvas(canvas, a.aba, { margin: 1, width: 132 }).catch(() => {
    qr.textContent = a.aba;
  });

  setupMining();
  refreshBalance();
  balanceTimer = window.setInterval(refreshBalance, 15000);
  liveTimer = window.setInterval(refreshLive, 4000);
  refreshLive();
}

async function refreshBalance(): Promise<void> {
  const el = document.getElementById("bal");
  if (!el) return;
  try {
    el.textContent = fmtAba(await wallet.balanceAba());
  } catch {
    el.textContent = "\u2013";
  }
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

// ---------------------------------------------------------------- mining
let mineHardwareThreads = 1;
let mining_ = false;

async function setupMining(): Promise<void> {
  const hw = document.getElementById("hw") as HTMLElement;
  const range = document.getElementById("threads") as HTMLInputElement;
  const thlabel = document.getElementById("thlabel") as HTMLElement;
  const gpu = document.getElementById("gpu") as HTMLInputElement;
  try {
    const info = await mining.hardwareInfo();
    mineHardwareThreads = Math.max(1, info.cpu_threads);
    hw.textContent = `${info.os}/${info.arch} \u00b7 ${info.cpu_threads} CPU threads \u00b7 GPU: ${info.has_nvidia ? "NVIDIA detected" : "detect on start"}`;
    range.max = String(mineHardwareThreads);
    range.value = String(Math.max(1, Math.floor(mineHardwareThreads / 2)));
    gpu.disabled = false;
    gpu.checked = info.has_nvidia;
  } catch {
    hw.textContent = "hardware detection unavailable";
  }
  thlabel.textContent = range.value;
  range.oninput = () => (thlabel.textContent = range.value);

  // reflect any already-running miner (e.g. after a UI reload)
  try {
    const st = await mining.minerStatus();
    mining_ = st.state === "running" || st.state === "starting";
    paintMineButton();
  } catch {
    /* ignore */
  }

  (document.getElementById("mine") as HTMLButtonElement).onclick = toggleMining;
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
    } else {
      const gpuOn = (document.getElementById("gpu") as HTMLInputElement).checked;
      await mining.startMiner(a.aba, Number(range.value), true, gpuOn);
      mining_ = true;
    }
    paintMineButton();
    refreshLive();
  } catch (e) {
    const pool = document.getElementById("poolline");
    if (pool) pool.textContent = "error: " + ((e as Error).message || String(e));
  }
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
  set("gpuhs", fmtHs(miner.gpu_hashrate));
  set("poolline", `CPU pool: ${miner.pool} \u00b7 GPU pool: prl.kryptex.network${miner.error ? " \u00b7 " + miner.error : ""}`);
  set("vshares", provider ? fmtAba(provider.window_shares) : "0");
  set("earned", provider ? fmtAba(provider.earned_aba) + " ABA" : "0 ABA");
  if (agent) {
    set("price", "$" + Number(agent.aba_price_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 6 }));
    const b = agent.payout_basis?.source;
    set("basis", b === "proxy-shares" ? "verified shares" : b || "\u2013");
  }
}

boot();
