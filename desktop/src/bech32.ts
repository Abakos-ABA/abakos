// bech32 (BIP173) <-> 0x for Abakos accounts. On the Abakos EVM the cosmos
// `abakos1...` address and the `0x...` address are the SAME 20 account bytes,
// just encoded differently (ported from the web wallet).

const CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";
const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];

function polymod(values: number[]): number {
  let chk = 1;
  for (const v of values) {
    const b = chk >> 25;
    chk = ((chk & 0x1ffffff) << 5) ^ v;
    for (let i = 0; i < 5; i++) if ((b >> i) & 1) chk ^= GEN[i];
  }
  return chk;
}

function hrpExpand(hrp: string): number[] {
  const out: number[] = [];
  for (let i = 0; i < hrp.length; i++) out.push(hrp.charCodeAt(i) >> 5);
  out.push(0);
  for (let i = 0; i < hrp.length; i++) out.push(hrp.charCodeAt(i) & 31);
  return out;
}

function checksum(hrp: string, data: number[]): number[] {
  const values = hrpExpand(hrp).concat(data).concat([0, 0, 0, 0, 0, 0]);
  const mod = polymod(values) ^ 1;
  const out: number[] = [];
  for (let i = 0; i < 6; i++) out.push((mod >> (5 * (5 - i))) & 31);
  return out;
}

function encode(hrp: string, data: number[]): string {
  const combined = data.concat(checksum(hrp, data));
  let s = hrp + "1";
  for (const d of combined) s += CHARSET.charAt(d);
  return s;
}

function decode(str: string): { hrp: string; data: number[] } {
  const pos = str.lastIndexOf("1");
  const data: number[] = [];
  for (let i = pos + 1; i < str.length; i++) data.push(CHARSET.indexOf(str.charAt(i)));
  return { hrp: str.substring(0, pos), data: data.slice(0, data.length - 6) };
}

function convertBits(data: number[], from: number, to: number, pad: boolean): number[] {
  let acc = 0;
  let bits = 0;
  const out: number[] = [];
  const max = (1 << to) - 1;
  for (const value of data) {
    acc = (acc << from) | value;
    bits += from;
    while (bits >= to) {
      bits -= to;
      out.push((acc >> bits) & max);
    }
  }
  if (pad && bits > 0) out.push((acc << (to - bits)) & max);
  return out;
}

export function ethToAbakos(hex: string, hrp = "abakos"): string {
  const clean = hex.replace(/^0x/, "").toLowerCase();
  const bytes: number[] = [];
  for (let i = 0; i < clean.length; i += 2) bytes.push(parseInt(clean.substr(i, 2), 16));
  return encode(hrp, convertBits(bytes, 8, 5, true));
}

export function abakosToEth(addr: string): string {
  const { data } = decode(addr);
  const bytes = convertBits(data, 5, 8, false);
  return "0x" + bytes.map((x) => x.toString(16).padStart(2, "0")).join("");
}
