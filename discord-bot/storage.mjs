// Minimal JSON persistence. Swap for a DB later if needed.
import { readFileSync, writeFileSync, existsSync } from "node:fs";

const load = (name) => {
  const f = new URL(`./${name}`, import.meta.url);
  if (!existsSync(f)) return {};
  try { return JSON.parse(readFileSync(f, "utf8")); } catch { return {}; }
};
const save = (name, data) => writeFileSync(new URL(`./${name}`, import.meta.url), JSON.stringify(data, null, 2));

export const loadLinks = () => load("links.json");
export const saveLinks = (d) => save("links.json", d);

// invites.json: { inviterId: count }
export const loadInvites = () => load("invites.json");
export const saveInvites = (d) => save("invites.json", d);

// state.json: misc bot state (e.g. { leaderboardMsgId })
export const loadMisc = () => load("state.json");
export const saveMisc = (d) => save("state.json", d);

// verify.json: { lastBlock: number, refunded: { <txhash>: <refundHash|true> } }
// Tracks how far the verify poller has scanned and which incoming txs were already refunded,
// so refunds survive restarts and are never sent twice.
export const loadVerifyState = () => load("verify.json");
export const saveVerifyState = (d) => save("verify.json", d);
