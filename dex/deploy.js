/* Compile + deploy the Abakos sandbox DEX to the Abakos EVM (chain 9721).
 *
 * Two-pass flow:
 *   1st run: generates a deployer key, prints its abakos1 address + how much to
 *            fund, then exits (code 2) if the balance is too low.
 *   2nd run (after funding): deploys TestUSDC + AbakosDEX, seeds ABA/USDC
 *            liquidity, and writes deployed.json (addresses + ABIs) for the UI.
 */
const fs = require("fs");
const path = require("path");
const solc = require("solc");
const { ethers } = require("ethers");

const RPC = process.env.ABA_EVM_RPC || "https://evm-rpc.abakos.ai";
const CHAIN_ID = 9721;
const KEYFILE = path.join(__dirname, ".deployer.key");
const OUT = path.join(__dirname, "deployed.json");

// Seed: 500,000 ABA + 125,000 USDC  => 1 ABA = 0.25 USDC (arbitrary sandbox price)
const ABA_SEED = ethers.parseEther("500000");
const USDC_SEED = 125000n * 10n ** 6n;
const NEED = ethers.parseEther("600000"); // seed + generous gas headroom

/* ---- bech32 (BIP173): eth 0x -> abakos1 ---- */
const B32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";
const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
function pm(v){let c=1;for(const p of v){const b=c>>25;c=((c&0x1ffffff)<<5)^p;for(let i=0;i<5;++i)if((b>>i)&1)c^=GEN[i];}return c;}
function hrpExp(h){const r=[];for(let i=0;i<h.length;++i)r.push(h.charCodeAt(i)>>5);r.push(0);for(let i=0;i<h.length;++i)r.push(h.charCodeAt(i)&31);return r;}
function checksum(h,d){const v=hrpExp(h).concat(d,[0,0,0,0,0,0]);const m=pm(v)^1;const r=[];for(let i=0;i<6;++i)r.push((m>>5*(5-i))&31);return r;}
function toWords(bytes){let acc=0,bits=0;const out=[];for(const b of bytes){acc=(acc<<8)|b;bits+=8;while(bits>=5){bits-=5;out.push((acc>>bits)&31);}}if(bits>0)out.push((acc<<(5-bits))&31);return out;}
function ethToAbakos(hex){const clean=hex.replace(/^0x/,"").toLowerCase();const bytes=[];for(let i=0;i<clean.length;i+=2)bytes.push(parseInt(clean.substr(i,2),16));const words=toWords(bytes);const comb=words.concat(checksum("abakos",words));let s="abakos1";for(const w of comb)s+=B32[w];return s;}

function compile() {
  const readSrc = (f) => fs.readFileSync(path.join(__dirname, "contracts", f), "utf8");
  const input = {
    language: "Solidity",
    sources: {
      "TestUSDC.sol": { content: readSrc("TestUSDC.sol") },
      "AbakosDEX.sol": { content: readSrc("AbakosDEX.sol") },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } },
    },
  };
  const out = JSON.parse(solc.compile(JSON.stringify(input)));
  let hard = false;
  for (const e of out.errors || []) {
    console.log(e.formattedMessage);
    if (e.severity === "error") hard = true;
  }
  if (hard) throw new Error("solc compile errors");
  return out.contracts;
}

async function main() {
  const c = compile();
  const usdcC = c["TestUSDC.sol"].TestUSDC;
  const dexC = c["AbakosDEX.sol"].AbakosDEX;
  console.log("compiled: TestUSDC + AbakosDEX");

  let key;
  if (fs.existsSync(KEYFILE)) key = fs.readFileSync(KEYFILE, "utf8").trim();
  else { key = ethers.Wallet.createRandom().privateKey; fs.writeFileSync(KEYFILE, key); try { fs.chmodSync(KEYFILE, 0o600); } catch (_) {} }

  const provider = new ethers.JsonRpcProvider(RPC, CHAIN_ID);
  const wallet = new ethers.Wallet(key, provider);
  const abakos1 = ethToAbakos(wallet.address);
  const bal = await provider.getBalance(wallet.address);
  console.log("deployer 0x     :", wallet.address);
  console.log("deployer abakos1:", abakos1);
  console.log("deployer balance:", ethers.formatEther(bal), "ABA");

  if (bal < NEED) {
    console.log("\nFUND_NEEDED: send >= " + ethers.formatEther(NEED) + " ABA to:");
    console.log("  " + abakos1);
    console.log("then re-run `node deploy.js`.");
    process.exit(2);
  }

  console.log("\ndeploying TestUSDC ...");
  const usdc = await new ethers.ContractFactory(usdcC.abi, usdcC.evm.bytecode.object, wallet).deploy();
  await usdc.waitForDeployment();
  const usdcAddr = await usdc.getAddress();
  console.log("  USDC:", usdcAddr);

  console.log("deploying AbakosDEX ...");
  const dex = await new ethers.ContractFactory(dexC.abi, dexC.evm.bytecode.object, wallet).deploy(usdcAddr);
  await dex.waitForDeployment();
  const dexAddr = await dex.getAddress();
  console.log("  DEX :", dexAddr);

  console.log("seeding liquidity:", ethers.formatEther(ABA_SEED), "ABA +", Number(USDC_SEED) / 1e6, "USDC ...");
  await (await usdc.mint(wallet.address, USDC_SEED)).wait();
  await (await usdc.approve(dexAddr, USDC_SEED)).wait();
  await (await dex.addLiquidity(USDC_SEED, { value: ABA_SEED })).wait();

  const rABA = await dex.reserveABA();
  const rUSDC = await dex.reserveUSDC();
  console.log("  reserves:", ethers.formatEther(rABA), "ABA /", Number(rUSDC) / 1e6, "USDC");

  fs.writeFileSync(OUT, JSON.stringify({
    chainId: CHAIN_ID, rpc: RPC, usdc: usdcAddr, dex: dexAddr,
    usdcAbi: usdcC.abi, dexAbi: dexC.abi,
  }, null, 2));
  console.log("\nwrote", OUT);
  console.log("DEX_DEPLOY_DONE");
}

main().catch((e) => { console.error(e); process.exit(1); });
