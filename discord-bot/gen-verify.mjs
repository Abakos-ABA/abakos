// One-off: generate a verify wallet and switch .env to VERIFY_METHOD=tx.
// Prints ONLY the public address. Run on the host that keeps the secret:
//   node gen-verify.mjs
import { ethers } from "ethers";
import { readFileSync, writeFileSync } from "node:fs";

const w = ethers.Wallet.createRandom();
const file = new URL("./.env", import.meta.url);
let env = readFileSync(file, "utf8");

const setKey = (k, v) => {
  const line = `${k}=${v}`;
  env = new RegExp(`^${k}=.*$`, "m").test(env) ? env.replace(new RegExp(`^${k}=.*$`, "m"), line) : env.trimEnd() + "\n" + line + "\n";
};
setKey("VERIFY_METHOD", "tx");
setKey("VERIFY_ADDRESS", w.address);
setKey("VERIFY_PRIVKEY", w.privateKey);
writeFileSync(file, env);

console.log("VERIFY_ADDRESS=" + w.address); // public — safe to show
console.log("VERIFY_METHOD set to tx. Fund this address with a little ABA so it can refund test transactions.");
