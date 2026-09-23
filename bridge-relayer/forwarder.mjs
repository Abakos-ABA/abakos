/* Abakos bridge forwarder: mining payouts -> USDC (Noble) -> IBC -> buyback wallet.
 *
 * Two intake lanes, both balance-triggered and resumable (state.json phase machine):
 *
 *  ATOM lane (primary): unMineable pays ATOM to our Cosmos Hub address (same key as the
 *    Hermes relayer, prefix cosmos). One Skip msgs_direct call returns a single
 *    MsgTransfer (ibc-hooks memo does the ATOM->USDC swap on Osmosis + forward to
 *    Noble). We sign it with the relayer mnemonic and broadcast to a public Hub RPC.
 *    Cost ~0% (no CCTP relay fee), latency ~1 min.
 *
 *  POL lane (backup): anything landing on the Polygon hot EOA is swapped+CCTP'd to
 *    Noble via Skip EVM txs (fixed ~$0.11 relay fee — hence only the backup).
 *
 * Shared leg 2: Hermes CLI ft-transfer Noble -> abakos-sandbox-1, receiver = buyback
 * wallet; the agent then swaps USDC -> native ABA on the DEX and distributes by shares.
 */
import { ethers } from "ethers";
import fs from "node:fs";
import http from "node:http";
import { execFile } from "node:child_process";
import { DirectSecp256k1HdWallet, Registry } from "@cosmjs/proto-signing";
import { SigningStargateClient, GasPrice, defaultRegistryTypes } from "@cosmjs/stargate";

const env = (k, d) => process.env[k] ?? d;
// shared
const STATE = env("ABA_FWD_STATE", "/opt/abakos-forwarder/state.json");
const SKIP = env("ABA_FWD_SKIP", "https://api.skip.build");
const NOBLE_REST = env("ABA_FWD_NOBLE_REST", "https://rest.cosmos.directory/noble");
const NOBLE_ADDR = env("ABA_FWD_NOBLE_ADDR", "noble19hn74t0xe0l6e9jufp3mym3aa648ej4ap83ury");
const RECEIVER = env("ABA_FWD_RECEIVER", "abakos175wca4q7lej002hs37lyyptr22kdksdm90sepj");
const HERMES = env("ABA_FWD_HERMES", "/usr/local/bin/hermes");
const SRC_CHANNEL = env("ABA_FWD_SRC_CHANNEL", "channel-600"); // noble-1 side
const LOCAL_REST = env("ABA_FWD_LOCAL_REST", "http://127.0.0.1:1317");
const USDC_DENOM_ABAKOS = env("ABA_FWD_USDC_DENOM", "ibc/8E27BA2D5493AF5636760E354E46004562C46AB7EC0CC4C1CA14E9E20E2545B5");
const POLL_SEC = Number(env("ABA_FWD_POLL_SEC", "60"));
const PORT = Number(env("ABA_FWD_PORT", "8093"));
const SLIPPAGE = env("ABA_FWD_SLIPPAGE", "1");
// ATOM lane
const MNEMONIC_FILE = env("ABA_FWD_MNEMONIC", "/root/.hermes/relayer.mnemonic");
const HUB_ADDR = env("ABA_FWD_HUB_ADDR", "cosmos19hn74t0xe0l6e9jufp3mym3aa648ej4afyy5m2");
const OSMO_ADDR = env("ABA_FWD_OSMO_ADDR", "osmo19hn74t0xe0l6e9jufp3mym3aa648ej4aplhydc");
const HUB_REST = env("ABA_FWD_HUB_REST", "https://rest.cosmos.directory/cosmoshub");
const HUB_RPCS = env("ABA_FWD_HUB_RPC", "https://cosmos-rpc.polkachu.com,https://rpc.cosmos.directory/cosmoshub").split(",");
const MIN_ATOM = BigInt(env("ABA_FWD_MIN_UATOM", "2000000"));      // start above 2 ATOM
const RESERVE_ATOM = BigInt(env("ABA_FWD_RESERVE_UATOM", "150000")); // keep 0.15 ATOM for fees
// POL lane
const POLY_RPCS = env("ABA_FWD_POLY_RPC", "https://polygon-bor-rpc.publicnode.com,https://polygon-rpc.com").split(",");
const KEYFILE = env("ABA_FWD_KEY", "/opt/abakos-forwarder/hot.key");
const MIN_POL = ethers.parseEther(env("ABA_FWD_MIN_POL", "150"));       // fixed $0.11 relay fee -> batch big
const RESERVE_POL = ethers.parseEther(env("ABA_FWD_RESERVE_POL", "1.5"));
// Noble forwarding accounts (DEX in-app deposits: CCTP mints to a per-user Noble
// address that auto-forwards over channel-600 to the user's own Abakos account)
const NOBLE_RPCS = env("ABA_FWD_NOBLE_RPC", "https://noble-rpc.polkachu.com,https://rpc.cosmos.directory/noble").split(",");
const FWD_FEE = { amount: [{ denom: "uusdc", amount: env("ABA_FWD_REG_FEE_UUSDC", "25000") }], gas: env("ABA_FWD_REG_GAS", "250000") };
const FWD_MAX_PER_DAY = Number(env("ABA_FWD_REG_PER_DAY", "300"));
const FWD_RATE_PER_MIN = Number(env("ABA_FWD_REG_PER_MIN_IP", "10"));

const log = (...a) => console.log(new Date().toISOString(), ...a);
let state = fs.existsSync(STATE) ? JSON.parse(fs.readFileSync(STATE, "utf8")) : {};
// migrate v1 layout (single POL lane at top level)
if (state.phase !== undefined && !state.pol) state = { pol: { phase: state.phase, cycle: state.cycle }, history: state.history || [], errors: state.errors || [] };
state.pol ??= { phase: "idle", cycle: null };
state.atom ??= { phase: "idle", cycle: null };
state.history ??= []; state.errors ??= [];
state.fwd ??= {};                                  // abakos addr -> registered noble forwarding account
state.fwdPending ??= {};                           // abakos addr -> derived-but-unregistered account (lazy)
state.fwdStats ??= { day: "", count: 0 };
const save = () => fs.writeFileSync(STATE, JSON.stringify(state, null, 2));
const pushErr = (lane, m) => { state.errors.unshift({ t: new Date().toISOString(), lane, m: String(m).slice(0, 300) }); state.errors.length = Math.min(state.errors.length, 20); save(); };

async function skip(pathname, body) {
  const r = await fetch(SKIP + pathname, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok || j.message) throw new Error("skip " + pathname + ": " + (j.message || r.status));
  return j;
}
async function bankBalance(rest, addr, denom) {
  const r = await fetch(`${rest}/cosmos/bank/v1beta1/balances/${addr}`);
  const j = await r.json();
  const c = (j.balances || []).find((b) => b.denom === denom);
  return BigInt(c ? c.amount : 0);
}
const nobleUusdc = () => bankBalance(NOBLE_REST, NOBLE_ADDR, "uusdc");
const abakosUsdc = () => bankBalance(LOCAL_REST, RECEIVER, USDC_DENOM_ABAKOS);
const hubUatom = () => bankBalance(HUB_REST, HUB_ADDR, "uatom");

function hermesTransfer(amount6) {
  const args = ["tx", "ft-transfer", "--src-chain", "noble-1", "--dst-chain", "abakos-sandbox-1",
    "--src-port", "transfer", "--src-channel", SRC_CHANNEL, "--amount", String(amount6),
    "--denom", "uusdc", "--receiver", RECEIVER, "--timeout-seconds", "300"];
  return new Promise((res, rej) => {
    execFile(HERMES, args, { timeout: 120000 }, (err, stdout, stderr) => {
      const out = String(stdout) + String(stderr);
      if (err || /ERROR/.test(out)) rej(new Error("hermes: " + out.slice(-300)));
      else res(out);
    });
  });
}

// Shared: noble arrival wait + leg2 delivery. Returns true when the lane cycle is done.
async function awaitNobleAndDeliver(lane, c) {
  if (lane.phase === "await_noble") {
    const now = await nobleUusdc();
    const arrived = now - BigInt(c.noble_before);
    const expect = c.expected_out ? (BigInt(c.expected_out) * 90n) / 100n : 1n;
    if (arrived >= expect) { c.arrived = arrived.toString(); lane.phase = "leg2"; save(); log("noble arrival:", c.arrived, "uusdc"); }
    else if (Date.now() - (c.await_since || 0) > 45 * 60 * 1000) throw new Error("noble arrival timeout (arrived=" + arrived + ")");
    else return false;
  }
  if (lane.phase === "leg2") {
    const before = await abakosUsdc();
    let lastErr;
    for (let i = 0; i < 5; i++) {
      try { await hermesTransfer(BigInt(c.arrived)); lastErr = null; break; }
      catch (e) { lastErr = e; log("leg2 retry", i + 1, e.message); await new Promise((r) => setTimeout(r, 10000)); }
    }
    if (lastErr) throw lastErr;
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 10000));
      if ((await abakosUsdc()) > before) break;
    }
    state.history.unshift({ t: new Date().toISOString(), lane: c.lane, in: c.amount_display, uusdc: c.arrived, txs: c.txs });
    state.history.length = Math.min(state.history.length, 50);
    lane.phase = "idle"; lane.cycle = null; save();
    log(c.lane, "cycle complete:", c.arrived, "uusdc delivered");
    return true;
  }
  return false;
}

// ---------- ATOM lane (primary) ----------
let hubClient = null, hubWallet = null;
async function hubConnect() {
  if (hubClient) return;
  hubWallet = await DirectSecp256k1HdWallet.fromMnemonic(fs.readFileSync(MNEMONIC_FILE, "utf8").trim(), { prefix: "cosmos" });
  const [acct] = await hubWallet.getAccounts();
  if (acct.address !== HUB_ADDR) throw new Error("hub address mismatch: " + acct.address);
  for (const url of HUB_RPCS) {
    try {
      hubClient = await SigningStargateClient.connectWithSigner(url.trim(), hubWallet, { gasPrice: GasPrice.fromString("0.005uatom") });
      return;
    } catch (e) { log("hub rpc failed:", url, e.message); }
  }
  throw new Error("no hub rpc reachable");
}

async function atomTick() {
  const lane = state.atom;
  if (!lane.cycle) {
    const bal = await hubUatom();
    const spendable = bal - RESERVE_ATOM;
    if (spendable < MIN_ATOM) return;
    lane.cycle = { lane: "atom", started: new Date().toISOString(), amount: spendable.toString(), amount_display: (Number(spendable) / 1e6).toFixed(6) + " ATOM", txs: [] };
    lane.phase = "route"; save();
  }
  const c = lane.cycle;

  if (lane.phase === "route") {
    const msgs = await skip("/v2/fungible/msgs_direct", {
      source_asset_denom: "uatom", source_asset_chain_id: "cosmoshub-4",
      dest_asset_denom: "uusdc", dest_asset_chain_id: "noble-1",
      amount_in: c.amount,
      swap_venues: [{ chain_id: "osmosis-1", name: "osmosis-poolmanager" }],
      chain_ids_to_addresses: { "cosmoshub-4": HUB_ADDR, "osmosis-1": OSMO_ADDR, "noble-1": NOBLE_ADDR },
      slippage_tolerance_percent: SLIPPAGE, allow_multi_tx: false,
    });
    const ct = msgs.txs?.[0]?.cosmos_tx;
    if (!ct || ct.chain_id !== "cosmoshub-4" || ct.msgs?.length !== 1) throw new Error("unexpected skip tx shape");
    const m = ct.msgs[0];
    if (m.msg_type_url !== "/ibc.applications.transfer.v1.MsgTransfer") throw new Error("unexpected msg type " + m.msg_type_url);
    c.expected_out = msgs.route?.amount_out ?? null;
    c.noble_before = (await nobleUusdc()).toString();
    c.skip_msg = m.msg; // JSON string of the MsgTransfer
    lane.phase = "sign"; save();
    log("atom cycle:", c.amount_display, "-> expect", c.expected_out, "uusdc");
  }

  if (lane.phase === "sign") {
    await hubConnect();
    const j = JSON.parse(c.skip_msg);
    const msg = {
      typeUrl: "/ibc.applications.transfer.v1.MsgTransfer",
      value: {
        sourcePort: j.source_port, sourceChannel: j.source_channel,
        token: j.token, sender: j.sender, receiver: j.receiver,
        timeoutHeight: j.timeout_height ? { revisionNumber: BigInt(j.timeout_height.revision_number || 0), revisionHeight: BigInt(j.timeout_height.revision_height || 0) } : undefined,
        timeoutTimestamp: BigInt(j.timeout_timestamp || 0),
        memo: j.memo || "",
      },
    };
    const res = await hubClient.signAndBroadcast(HUB_ADDR, [msg], "auto", "abakos forwarder");
    if (res.code !== 0) throw new Error("hub tx failed code " + res.code + ": " + res.rawLog?.slice(0, 200));
    c.txs.push({ kind: "hub-ibc", hash: res.transactionHash });
    lane.phase = "await_noble"; c.await_since = Date.now(); save();
    log("hub tx:", res.transactionHash);
  }

  await awaitNobleAndDeliver(lane, c);
}

// ---------- POL lane (backup) ----------
let polyProvider = null, polyWallet = null;
async function polyConnect() {
  if (polyProvider) return;
  for (const url of POLY_RPCS) {
    try {
      const p = new ethers.JsonRpcProvider(url.trim(), { chainId: 137, name: "polygon" });
      await p.getBlockNumber();
      polyProvider = p; polyWallet = new ethers.Wallet(fs.readFileSync(KEYFILE, "utf8").trim(), p);
      return;
    } catch (e) { log("poly rpc failed:", url, e.message); }
  }
  throw new Error("no polygon rpc reachable");
}

async function polTick() {
  const lane = state.pol;
  await polyConnect();
  if (!lane.cycle) {
    const bal = await polyProvider.getBalance(polyWallet.address);
    const spendable = bal - RESERVE_POL;
    if (spendable < MIN_POL) return;
    lane.cycle = { lane: "pol", started: new Date().toISOString(), amount: spendable.toString(), amount_display: ethers.formatEther(spendable) + " POL", txs: [] };
    lane.phase = "route"; save();
  }
  const c = lane.cycle;

  if (lane.phase === "route") {
    const msgs = await skip("/v2/fungible/msgs_direct", {
      source_asset_denom: "polygon-native", source_asset_chain_id: "137",
      dest_asset_denom: "uusdc", dest_asset_chain_id: "noble-1",
      amount_in: c.amount, chain_ids_to_addresses: { 137: polyWallet.address, "noble-1": NOBLE_ADDR },
      slippage_tolerance_percent: SLIPPAGE, smart_relay: true, allow_multi_tx: true,
    });
    c.expected_out = msgs.route?.amount_out ?? null;
    c.noble_before = (await nobleUusdc()).toString();
    c.pending_txs = msgs.txs.map((t) => t.evm_tx).filter(Boolean);
    if (!c.pending_txs.length) throw new Error("skip returned no evm txs");
    lane.phase = "leg1"; save();
    log("pol cycle:", c.amount_display, "-> expect", c.expected_out, "uusdc");
  }

  if (lane.phase === "leg1") {
    while (c.pending_txs.length) {
      const t = c.pending_txs[0];
      for (const ap of t.required_erc20_approvals || []) {
        const erc = new ethers.Contract(ap.token_contract, ["function approve(address,uint256) returns (bool)"], polyWallet);
        const atx = await erc.approve(ap.spender, BigInt(ap.amount));
        await atx.wait(3);
        c.txs.push({ kind: "approve", hash: atx.hash }); save();
      }
      const tx = await polyWallet.sendTransaction({ to: t.to, data: "0x" + t.data, value: BigInt(t.value || 0) });
      await tx.wait(3);
      c.txs.push({ kind: "skip", hash: tx.hash });
      c.pending_txs.shift(); save();
      log("pol leg1 confirmed:", tx.hash);
    }
    lane.phase = "await_noble"; c.await_since = Date.now(); save();
  }

  await awaitNobleAndDeliver(lane, c);
}

// ---------- Noble forwarding accounts (DEX deposit endpoint) ----------
// GET /forwarding?recipient=abakos1...  ->  { noble_address, channel, registered }
// The address is derived on Noble from (channel-600, recipient, no fallback); anything
// minted/sent there is auto-forwarded over IBC to the recipient. Registration is a
// one-time Noble tx paid by the relayer account (~0.025 USDC).

const B32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";
function b32polymod(vals) {
  const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
  let chk = 1;
  for (const v of vals) {
    const b = chk >> 25;
    chk = ((chk & 0x1ffffff) << 5) ^ v;
    for (let i = 0; i < 5; i++) if ((b >> i) & 1) chk ^= GEN[i];
  }
  return chk;
}
function validAbakosAddr(addr) {
  if (typeof addr !== "string" || !/^abakos1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{38}$/.test(addr)) return false;
  const hrp = "abakos", data = [];
  for (const c of addr.slice(7)) data.push(B32.indexOf(c));
  const exp = [];
  for (const c of hrp) exp.push(c.charCodeAt(0) >> 5);
  exp.push(0);
  for (const c of hrp) exp.push(c.charCodeAt(0) & 31);
  return b32polymod(exp.concat(data)) === 1;
}

// hand-rolled protobuf for noble.forwarding.v1.MsgRegisterAccount (4 string fields)
const varint = (n) => { const out = []; while (n > 127) { out.push((n & 127) | 128); n >>= 7; } out.push(n); return out; };
const MsgRegisterAccount = {
  encode(m) {
    const parts = [];
    const put = (field, str) => {
      if (!str) return;
      const b = Buffer.from(str, "utf8");
      parts.push(Buffer.from([(field << 3) | 2, ...varint(b.length)]), b);
    };
    put(1, m.signer); put(2, m.recipient); put(3, m.channel); put(4, m.fallback);
    const buf = Buffer.concat(parts);
    return { finish: () => new Uint8Array(buf) };
  },
  decode() { throw new Error("decode not supported"); },
  fromPartial: (m) => m,
};
const nobleRegistry = new Registry(defaultRegistryTypes);
nobleRegistry.register("/noble.forwarding.v1.MsgRegisterAccount", MsgRegisterAccount);

let nobleClient = null;
async function nobleConnect() {
  if (nobleClient) return nobleClient;
  const wallet = await DirectSecp256k1HdWallet.fromMnemonic(fs.readFileSync(MNEMONIC_FILE, "utf8").trim(), { prefix: "noble" });
  const [acct] = await wallet.getAccounts();
  if (acct.address !== NOBLE_ADDR) throw new Error("noble address mismatch: " + acct.address);
  for (const url of NOBLE_RPCS) {
    try {
      nobleClient = await SigningStargateClient.connectWithSigner(url.trim(), wallet, { registry: nobleRegistry });
      return nobleClient;
    } catch (e) { log("noble rpc failed:", url, e.message); }
  }
  throw new Error("no noble rpc reachable");
}

async function fwdQuery(recipient) {
  const r = await fetch(`${NOBLE_REST}/noble/forwarding/v1/address/${SRC_CHANNEL}/${recipient}/`);
  const j = await r.json();
  if (!r.ok || !j.address) throw new Error("forwarding query failed: " + JSON.stringify(j).slice(0, 160));
  return j; // { address, exists }
}

async function registerForwarding(recipient, address) {
  const day = new Date().toISOString().slice(0, 10);
  if (state.fwdStats.day !== day) { state.fwdStats.day = day; state.fwdStats.count = 0; }
  if (state.fwdStats.count >= FWD_MAX_PER_DAY) throw new Error("daily registration cap reached");
  const client = await nobleConnect();
  const msg = { typeUrl: "/noble.forwarding.v1.MsgRegisterAccount", value: { signer: NOBLE_ADDR, recipient, channel: SRC_CHANNEL, fallback: "" } };
  const res = await client.signAndBroadcast(NOBLE_ADDR, [msg], FWD_FEE, "abakos dex deposit");
  if (res.code !== 0 && !/already/i.test(res.rawLog || "")) throw new Error("register failed code " + res.code + ": " + String(res.rawLog || "").slice(0, 160));
  state.fwdStats.count++;
  state.fwd[recipient] = { address, registered: true, t: new Date().toISOString(), tx: res.transactionHash };
  delete state.fwdPending[recipient];
  save();
  log("forwarding registered:", recipient, "->", address, res.transactionHash);
}

// Lazy: the endpoint only derives (free); the actual registration tx is sent by
// fwdPendingTick once a deposit really landed on the derived account — so spam
// costs nothing and the relayer only pays ~0.025 USDC per genuine new user.
// Funds waiting on an unregistered account are flushed by the registration itself.
async function handleForwarding(recipient) {
  const hit = state.fwd[recipient];
  if (hit?.registered) return { noble_address: hit.address, channel: SRC_CHANNEL, registered: true };
  const q = await fwdQuery(recipient);
  if (q.exists) {
    state.fwd[recipient] = { address: q.address, registered: true, t: new Date().toISOString() };
    delete state.fwdPending[recipient]; save();
    return { noble_address: q.address, channel: SRC_CHANNEL, registered: true };
  }
  if (!state.fwdPending[recipient]) {
    const keys = Object.keys(state.fwdPending);
    if (keys.length >= 1000) delete state.fwdPending[keys[0]];
    state.fwdPending[recipient] = { address: q.address, t: new Date().toISOString() };
    save();
  }
  return { noble_address: q.address, channel: SRC_CHANNEL, registered: false, note: "registers automatically on first deposit" };
}

async function fwdPendingTick() {
  for (const [recipient, e] of Object.entries(state.fwdPending)) {
    if (Date.now() - Date.parse(e.t) > 45 * 24 * 3600 * 1000) { delete state.fwdPending[recipient]; save(); continue; }
    try {
      if (await bankBalance(NOBLE_REST, e.address, "uusdc") > 0n) await registerForwarding(recipient, e.address);
    } catch (err) { nobleClient = null; log("fwd pending error:", recipient, err.message); pushErr("fwd", err.message); }
  }
}

const fwdRate = new Map();                      // ip -> { n, t }
function rateOk(ip) {
  const now = Date.now(), e = fwdRate.get(ip);
  if (!e || now - e.t > 60000) { fwdRate.set(ip, { n: 1, t: now }); return true; }
  e.n++;
  return e.n <= FWD_RATE_PER_MIN;
}

// ---------- main ----------
async function main() {
  log("forwarder v2 up. hub:", HUB_ADDR, "| receiver:", RECEIVER, "| atom:", state.atom.phase, "| pol:", state.pol.phase);
  http.createServer(async (req, res) => {
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    const u = new URL(req.url, "http://localhost");
    if (u.pathname === "/forwarding") {
      const recipient = (u.searchParams.get("recipient") || "").trim().toLowerCase();
      if (!validAbakosAddr(recipient)) { res.statusCode = 400; return res.end(JSON.stringify({ error: "invalid abakos address" })); }
      const ip = String(req.headers["x-forwarded-for"] || req.socket.remoteAddress || "?").split(",")[0].trim();
      if (!rateOk(ip)) { res.statusCode = 429; return res.end(JSON.stringify({ error: "rate limited — try again in a minute" })); }
      try {
        return res.end(JSON.stringify(await handleForwarding(recipient)));
      } catch (e) {
        nobleClient = null;                      // reconnect after sequence/rpc errors
        pushErr("fwd", e.message);
        res.statusCode = 502;
        return res.end(JSON.stringify({ error: String(e.message || e).slice(0, 200) }));
      }
    }
    let pol = null, atom = null;
    try { if (polyProvider) pol = ethers.formatEther(await polyProvider.getBalance(polyWallet.address)); } catch {}
    try { atom = (Number(await hubUatom()) / 1e6).toFixed(6); } catch {}
    res.end(JSON.stringify({
      hub: HUB_ADDR, atom_balance: atom, atom_phase: state.atom.phase,
      pol_hot: polyWallet?.address ?? null, pol_balance: pol, pol_phase: state.pol.phase,
      forwarding_accounts: Object.keys(state.fwd).length,
      forwarding_pending: Object.keys(state.fwdPending).length,
      last: state.history[0] ?? null, errors: state.errors.slice(0, 5),
    }));
  }).listen(PORT, "127.0.0.1");
  // lanes are independent; a lane error must not stall the other
  while (true) {
    try { await atomTick(); } catch (e) { log("atom tick error:", e.message); pushErr("atom", e.message); }
    try { await polTick(); } catch (e) { log("pol tick error:", e.message); pushErr("pol", e.message); }
    try { await fwdPendingTick(); } catch (e) { log("fwd tick error:", e.message); pushErr("fwd", e.message); }
    await new Promise((r) => setTimeout(r, POLL_SEC * 1000));
  }
}
main().catch((e) => { console.error("fatal:", e); process.exit(1); });
