// Minimal RESP client for FalkorDB over Cloudflare TCP sockets (GRAPH.QUERY only).
import { connect } from "cloudflare:sockets";
const enc = new TextEncoder(), dec = new TextDecoder();
export function encode(args) {
  let s = `*${args.length}\r\n`;
  for (const a of args) { const b = enc.encode(String(a)); s += `$${b.length}\r\n${String(a)}\r\n`; }
  return enc.encode(s);
}
export function lit(v) {
  if (v === null || v === undefined) return "null";
  if (Array.isArray(v)) return "[" + v.map(lit).join(",") + "]";
  if (typeof v === "number") return Number.isFinite(v) ? String(v) : "null";
  if (typeof v === "boolean") return String(v);
  if (typeof v === "object") throw new Error("bad param");
  // Escape \, ", and controls so a value cannot close the Cypher string or inject a newline.
  const s = String(v).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/[\u0000-\u001f\u007f\u0085\u2028\u2029]/g, c => c === "\n" ? "\\n" : c === "\r" ? "\\r" : c === "\t" ? "\\t" : " ");
  return '"' + s + '"';
}
export function withParams(q, p = {}) {
  const ks = Object.keys(p);
  for (const k of ks) if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(k)) throw new Error("bad param name"); return ks.length ? "CYPHER " + ks.map(k => `${k}=${lit(p[k])}`).join(" ") + " " + q : q;
}
// Parser over a byte buffer; returns [value, nextIndex] or null if incomplete.
export function parse(buf, i = 0) {
  const nl = buf.indexOf(13, i); if (nl < 0 || nl + 1 >= buf.length) return null;
  const t = String.fromCharCode(buf[i]), line = dec.decode(buf.subarray(i + 1, nl)); let j = nl + 2;
  if (t === "+") return [line, j];
  if (t === "-") return [new Error(line), j];
  if (t === ":") return [Number(line), j];
  if (t === ",") return [Number(line), j];
  if (t === "$") { const n = Number(line); if (n < 0) return [null, j]; if (buf.length < j + n + 2) return null; return [dec.decode(buf.subarray(j, j + n)), j + n + 2]; }
  if (t === "*") { const n = Number(line); if (n < 0) return [null, j]; const out = [];
    for (let k = 0; k < n; k++) { const r = parse(buf, j); if (!r) return null; out.push(r[0]); j = r[1]; } return [out, j]; }
  throw new Error("RESP type " + t);
}
export class Falkor {
  constructor(url) { this.u = new URL(url); }
  async open() {
    const tls = this.u.protocol === "rediss:";
    this.sock = connect({ hostname: this.u.hostname, port: Number(this.u.port || 6379) }, { secureTransport: tls ? "on" : "off" });
    this.w = this.sock.writable.getWriter(); this.r = this.sock.readable.getReader(); this.buf = new Uint8Array(0);
    if (this.u.password) await this.cmd(this.u.username ? ["AUTH", decodeURIComponent(this.u.username), decodeURIComponent(this.u.password)] : ["AUTH", decodeURIComponent(this.u.password)]);
  }
  async cmd(args) {
    await this.w.write(encode(args));
    for (;;) {
      const r = this.buf.length ? parse(this.buf) : null;
      if (r) { this.buf = this.buf.subarray(r[1]); if (r[0] instanceof Error) throw r[0]; return r[0]; }
      const { value, done } = await this.r.read(); if (done) throw new Error("socket closed");
      const nb = new Uint8Array(this.buf.length + value.length); nb.set(this.buf); nb.set(value, this.buf.length); this.buf = nb;
    }
  }
  async query(graph, q, p) {
    const res = await this.cmd(["GRAPH.QUERY", graph, withParams(q, p)]);
    if (res.length < 3) return [];             // write-only: [stats]
    return res[1];                             // rows of scalar values
  }
  close() { try { this.sock.close(); } catch {} }
}
