import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig, Easing} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Inter';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';
import D from './durations.json';
import M from './marks.json';
import CAP from './captions.json';
const FONT = loadFont('normal', {weights: ['500', '700', '800', '900']}).fontFamily;
const MONO = loadMono('normal', {weights: ['500', '700']}).fontFamily;
const C = {bg: '#0b0d12', red: '#ff4d57', grn: '#3fb950', pur: '#a371f7', blue: '#58a6ff', yel: '#ffd33d', ink: '#e8eaf0', dim: '#8a93a6', panel: '#141822'};
const FPS = 30, PAD = 0.6, LEAD = 0.25;
const IDS = ['s01','s02','s03','s04','s05','s06','s07','s08','s09','s10','s11','s12','s13'] as const;
type Id = typeof IDS[number];
const len = (s: Id) => Math.round(((D as any)[s] + PAD + LEAD) * FPS);
const starts: Record<string, number> = {}; let acc = 0;
for (const s of IDS) { starts[s] = acc; acc += len(s); }
export const total = acc + 45;
const UI = new Set(['s04','s05','s06','s07','s08','s10','s11']);
const LAST = 's13';

const pop = (f: number, d = 0) => spring({frame: f - d, fps: FPS, config: {damping: 14, stiffness: 120}});

// ---------- graph (real UI recording, cropped to the graph) ----------
const GX = 150, GY = 330, GW = 1030, GH = 430;
const Graph: React.FC<{s: Id; vertical: boolean}> = ({s, vertical}) => {
  const f = useCurrentFrame();
  const startFrom = Math.round(((M as any)[s] - LEAD) * FPS);
  const boxW = vertical ? 960 : 1800, cw = vertical ? 440 : GW;
  const k = boxW / cw, boxH = GH * k;
  // vertical: pan the crop window along the cascade
  const panTargets: Record<string, [number, number]> = {s04: [150, 740], s05: [150, 200], s06: [150, 740], s07: [740, 740], s08: [380, 380], s10: [740, 150], s11: [450, 450]};
  const [p0, p1] = panTargets[s];
  const x0 = vertical ? interpolate(f, [0, len(s) * 0.8], [p0, p1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)}) : GX;
  const zoom = interpolate(f, [0, len(s)], [1, 1.035]);
  const faq = s === 's08';
  const fx = (580.6 - x0) * k, fy = (533.5 - GY) * k;
  return (
    <div style={{position: 'absolute', left: 60, top: vertical ? 300 : 70, width: boxW, height: boxH, overflow: 'hidden', borderRadius: 22, ...(vertical ? {WebkitMaskImage: 'linear-gradient(to right, transparent 0, #000 70px, #000 calc(100% - 70px), transparent 100%)'} : {}), background: '#000', boxShadow: '0 0 0 1px #222a36'}}>
      <div style={{position: 'absolute', inset: 0, transform: `scale(${zoom})`, transformOrigin: '50% 50%'}}>
        <OffthreadVideo src={staticFile('ui.mp4')} startFrom={Math.max(0, startFrom)} muted
          style={{position: 'absolute', left: -x0 * k, top: -GY * k, width: 1920 * k, height: 1080 * k, maxWidth: 'none'}} />
        {faq && <div style={{position: 'absolute', left: fx - 70, top: fy - 70, width: 140, height: 140, borderRadius: 999,
          border: `6px solid ${C.grn}`, opacity: interpolate(f, [10, 22], [0, 1], {extrapolateRight: 'clamp'}),
          transform: `scale(${1 + 0.08 * Math.sin(f / 5)})`, boxShadow: `0 0 40px ${C.grn}`}} />}
      </div>
    </div>);
};

// ---------- callouts (values are the real API outputs from the run) ----------
const Chip: React.FC<{c: string; children: React.ReactNode; d?: number; big?: boolean}> = ({c, children, d = 0, big}) => {
  const f = useCurrentFrame(); const p = pop(f, d);
  return <div style={{display: 'inline-flex', alignItems: 'center', gap: 12, padding: big ? '16px 26px' : '10px 18px', margin: 6, borderRadius: 14,
    background: C.panel, border: `2px solid ${c}`, color: C.ink, fontSize: big ? 34 : 26, fontWeight: 700, opacity: p, transform: `translateY(${(1 - p) * 20}px)`}}>{children}</div>;
};
const Dot: React.FC<{c: string}> = ({c}) => <span style={{width: 16, height: 16, borderRadius: 99, background: c, display: 'inline-block'}} />;
const Callout: React.FC<{s: Id; v?: boolean}> = ({s, v}) => {
  const f = useCurrentFrame();
  switch (s) {
    case 's04': return <><Chip c={C.grn} d={30}><Dot c={C.grn} />Sources</Chip><Chip c={C.pur} d={75}><Dot c={C.pur} />Claims</Chip><Chip c={C.blue} d={130}><Dot c={C.blue} />Artifacts the bots built</Chip></>;
    case 's05': return <><Chip c={C.red} d={20}>✗ “Records for 35 hours” · said 35, source says 3.5</Chip><Chip c={C.red} d={200}>✗ “Trusted by 10000 teams” · no source cited</Chip></>;
    case 's06': { const n = Math.min(10, Math.max(0, Math.floor(interpolate(f, [25, 90], [0, 10], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}))));
      return <>{v && <Chip c={C.red} d={0}>▶ “Mark ‘35 h’ claim corrected → taint everything built on it”</Chip>}<Chip c={C.red} big d={15}><span style={{fontSize: 56, fontWeight: 900, color: C.red, fontVariantNumeric: 'tabular-nums'}}>{n}</span> artifacts tainted</Chip><Chip c={C.red} big d={60}>up to <b style={{color: C.red}}>4 hops</b> deep · one Cypher query</Chip></>; }
    case 's07': { const rows: [string, string, number][] = [['YouTube Short', 'Reel', 27400], ['Landing page hero', 'Quill', 18500], ['X launch post', 'Quill', 12100], ['Link preview image', 'Quill', 9300], ['Waitlist email', 'Quill', 6400], ['Launch blog post', 'Quill', 4200], ['X reply thread', 'Quill', 1800]];
      return <div style={{background: C.panel, border: `2px solid ${C.red}`, borderRadius: 18, padding: v ? '18px 30px' : '12px 26px', width: v ? 860 : 970, boxShadow: '0 20px 60px rgba(0,0,0,.6)', opacity: pop(f, 5)}}>
        <div style={{color: C.ink, fontSize: v ? 27 : 24, fontWeight: 800, marginBottom: 6}}>Recall plan · most-viewed first · <span style={{color: C.yel}}>79,700</span> synthetic est. reach</div>
        <div style={{color: C.yel, fontSize: v ? 22 : 18, fontWeight: 700, marginBottom: 6}}>6 synthetic example URLs · synthetic demo metrics</div>
        <div style={{display: 'grid', gridTemplateColumns: v ? '1fr' : '1fr 1fr', columnGap: 34}}>{(v ? rows.slice(0, 5) : rows).map(([t, o, r], k) => { const p = pop(f, 30 + k * 14);
          return <div key={t} style={{display: 'flex', justifyContent: 'space-between', color: C.ink, fontSize: v ? 30 : 21, fontWeight: 700, padding: v ? '7px 0' : '4px 0', borderTop: '1px solid #222a36', opacity: p, transform: `translateX(${(1 - p) * 30}px)`}}>
            <span>{k + 1}. {t} <span style={{color: C.dim, fontWeight: 600}}>· {o}</span></span><span style={{color: C.yel, fontVariantNumeric: 'tabular-nums'}}>{r.toLocaleString('en-US')} est.</span></div>; })}</div></div>; }
    case 's08': return <><Chip c={C.grn} big d={15}>✓ FAQ page · no path to the bad claim → no recall</Chip></>;
    case 's10': { const path = ['YouTube Short', '30s Short script', 'Launch blog post', 'Launch brief', '“35 hours” claim'];
      return <>{path.map((p, i) => <Chip key={p} c={i === 4 ? C.red : C.yel} d={30 + i * 26}>{p}{i < 4 ? '  →' : ''}</Chip>)}<Chip c={C.grn} d={30 + 5 * 26}>source: “Battery life: 3.5 hours”</Chip></>; }
    case 's11': return <><Chip c={C.blue} d={10}>Reel ← redo: YouTube Short · Short captions · 30s script</Chip><Chip c={C.blue} d={30}>Quill ← redo: brief · blog · landing · preview · X posts · email</Chip></>;
  }
  return null;
};

// ---------- full-screen cards ----------
const Hook: React.FC = () => {
  const f = useCurrentFrame(); const strike = interpolate(f, [55, 75], [0, 100], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fix = pop(f, 80);
  return <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', gap: 10}}>
    <div style={{fontSize: 70, color: C.dim, fontWeight: 700}}>source: <span style={{color: C.grn}}>3.5 hours</span></div>
    <div style={{position: 'relative', fontSize: 200, fontWeight: 900, color: C.red, opacity: pop(f, 10)}}>35 hours
      <div style={{position: 'absolute', left: 0, top: '52%', height: 16, width: `${strike}%`, background: C.ink, borderRadius: 8}} /></div>
    <div style={{fontSize: 46, color: C.ink, fontWeight: 700, opacity: fix}}>…one dropped decimal.</div>
  </AbsoluteFill>;
};
const Spread: React.FC<{vertical: boolean}> = ({vertical}) => {
  const items: [string, string][] = [['YouTube Short', '27.4k'], ['Landing page', '18.5k'], ['X post', '12.1k'], ['Link preview', '9.3k'], ['Waitlist email', '6.4k'], ['Blog post', '4.2k'], ['X thread', '1.8k']];
  return <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: 80}}>
    <div style={{fontSize: 54, color: C.ink, fontWeight: 800, marginBottom: 30}}>Imagine it goes live in…</div>
    <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', maxWidth: vertical ? 640 : 1500}}>
      {items.map(([t, v], i) => <Chip key={t} c={C.red} big d={12 + i * 16}>{t} <span style={{color: C.yel, fontVariantNumeric: 'tabular-nums'}}>{v} views</span></Chip>)}</div>
    <div style={{fontSize: 26, color: C.dim, marginTop: 24, fontWeight: 600}}>est. reach, synthetic demo data</div></AbsoluteFill>;
};
const Title: React.FC<{vertical?: boolean}> = ({vertical}) => { const f = useCurrentFrame();
  return <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', textAlign: 'center'}}>
    <div style={{fontSize: vertical ? 96 : 130, fontWeight: 900, color: C.ink, opacity: pop(f), transform: `scale(${0.9 + 0.1 * pop(f)})`}}>Taint <span style={{color: C.red}}>+</span> Receipts</div>
    <div style={{fontSize: 40, color: C.dim, fontWeight: 600, marginTop: 10, opacity: pop(f, 20)}}>a recall system for published content</div>
    <div style={{fontSize: 34, color: C.yel, fontWeight: 700, marginTop: 30, opacity: pop(f, 40)}}>built on FalkorDB</div></AbsoluteFill>; };
const Code: React.FC<{vertical: boolean}> = ({vertical}) => { const f = useCurrentFrame();
  const lines = ["MATCH (bad:Claim {id:$id})", "SET bad.status = 'corrected'", "WITH bad", "MATCH p = (x:Artifact)", "      -[:DERIVED_FROM*1..10]->(bad)", "SET x.status = 'tainted'", "RETURN x.title, length(p)", "", "// recall plan", "ORDER BY x.reach DESC"];
  const tools = ['assert_claim', 'register_artifact', 'check_receipts', 'correct_claim', 'recall_plan', 'why_tainted', 'requeue_tainted', 'trust_ledger'];
  return <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: 60}}>
    <div style={{background: C.panel, borderRadius: 20, padding: '34px 44px', border: '1px solid #2a3240'}}>
      {lines.map((l, i) => <div key={i} style={{fontFamily: MONO, fontSize: vertical ? 32 : 40, color: l.includes('DERIVED_FROM') ? C.red : l.startsWith('//') ? C.dim : l.includes('reach') ? C.yel : C.ink, opacity: pop(f, i * 5), whiteSpace: 'pre'}}>{l}</div>)}</div>
    <div style={{marginTop: 30, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', maxWidth: vertical ? 1000 : 1600}}>
      <Chip c={C.yel} d={50}>MCP</Chip>{tools.map((t, i) => <Chip key={t} c={C.blue} d={60 + i * 6}><span style={{fontFamily: MONO, fontSize: 24}}>{t}</span></Chip>)}</div></AbsoluteFill>; };
const Bench: React.FC<{vertical: boolean}> = ({vertical}) => { const f = useCurrentFrame();
  const out = ["$ python -m teamgraph.scale 1000 25", "seeded in 0.7s", "nodes            26,004", "edges            51,099", "max_hops         10", "traverse p50     0.62 ms", "traverse max     9.01 ms", "correct+recall   14.93 ms"];
  const typed = Math.floor(interpolate(f, [5, 40], [0, out[0].length], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}));
  return <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: 50}}>
    <div style={{background: '#06080c', borderRadius: 18, padding: '30px 40px', border: '1px solid #2a3240', width: vertical ? 1000 : 1300, boxShadow: '0 30px 80px rgba(0,0,0,.5)'}}>
      <div style={{display: 'flex', gap: 10, marginBottom: 20}}>{['#ff5f57', '#febc2e', '#28c840'].map((c) => <div key={c} style={{width: 16, height: 16, borderRadius: 9, background: c}} />)}</div>
      <div style={{fontFamily: MONO, fontSize: vertical ? 40 : 40, color: C.grn, whiteSpace: 'pre'}}>{out[0].slice(0, typed)}</div>
      {out.slice(1).map((l, i) => <div key={l} style={{fontFamily: MONO, fontSize: vertical ? 40 : 40, whiteSpace: 'pre', color: /p50|recall/.test(l) ? C.yel : C.ink, fontWeight: /p50|recall/.test(l) ? 700 : 500, opacity: f > 48 + i * 8 ? 1 : 0}}>{l}</div>)}</div>
    <div style={{fontSize: 24, color: C.dim, marginTop: 22, fontWeight: 600, opacity: pop(f, 110)}}>fresh run, FalkorDB (embedded), 14 Oct 2026 · synthetic graph</div></AbsoluteFill>; };
const End: React.FC = () => { const f = useCurrentFrame();
  return <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: 60}}>
    <div style={{fontSize: 110, fontWeight: 900, color: C.ink, opacity: pop(f)}}>Taint <span style={{color: C.red}}>+</span> Receipts</div>
    <div style={{fontSize: 48, color: C.ink, fontWeight: 700, marginTop: 16, opacity: pop(f, 15)}}>One wrong number. <span style={{color: C.red}}>Every place it reached.</span> <span style={{color: C.yel}}>Biggest audience first.</span></div>
    <div style={{fontSize: 30, color: C.dim, fontWeight: 600, marginTop: 40, opacity: pop(f, 35)}}>FalkorDB · MCP · Graph Hacks 2026 · Company Brain · Agent Memory & Coordination · Connected Data</div>
    <div style={{fontSize: 40, color: C.yel, fontWeight: 800, marginTop: 36, opacity: pop(f, 25)}}>github.com/by42ppcrps-dev/taint-receipts</div>
    <div style={{fontSize: 30, color: C.ink, fontWeight: 600, marginTop: 10, opacity: pop(f, 30)}}>taint-receipts.lumegridai.workers.dev</div>
    <div style={{fontSize: 24, color: C.dim, marginTop: 18, opacity: pop(f, 45)}}>All demo data is synthetic.</div></AbsoluteFill>; };

// ---------- captions ----------
const Captions: React.FC<{s: Id; vertical: boolean}> = ({s, vertical}) => {
  const f = useCurrentFrame(); const t = f / FPS - LEAD; const w = (CAP as any)[s] as {w: string; s: number; e: number}[];
  // chunk into ~6-word phrases, break on punctuation
  // split on punctuation first, then balance long phrases so no word is orphaned (e.g. "…in the" / "quote.")
  const MAX = vertical ? 4 : 7; const phrases: typeof w[] = []; let cur: typeof w = [];
  w.forEach((x) => { cur.push(x); if (/[.?!,:]$/.test(x.w)) { phrases.push(cur); cur = []; } });
  if (cur.length) phrases.push(cur);
  const chunks: typeof w[] = [];
  phrases.forEach((p) => { const n = Math.ceil(p.length / MAX), sz = Math.ceil(p.length / n); for (let i = 0; i < p.length; i += sz) chunks.push(p.slice(i, i + sz)); });
  const ch = chunks.find((c, i) => t >= c[0].s - 0.1 && t < (chunks[i + 1] ? chunks[i + 1][0].s - 0.1 : c[c.length - 1].e + 0.5));
  if (!ch) return null;
  return <div style={{position: 'absolute', left: 0, right: 0, bottom: vertical ? 110 : 40, textAlign: 'center', padding: '0 60px'}}>
    <span style={{background: 'rgba(0,0,0,.72)', padding: '10px 22px', borderRadius: 12, fontSize: vertical ? 54 : 44, fontWeight: 800, color: C.ink, lineHeight: 1.5, boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone'}}>
      {ch.map((x, i) => <span key={i} style={{color: t >= x.s ? C.ink : '#9aa3b5'}}>{x.w} </span>)}</span></div>;
};

const Scene: React.FC<{s: Id; vertical: boolean}> = ({s, vertical}) => {
  const f = useCurrentFrame(); const fade = interpolate(f, [0, 8, len(s) - 6, len(s)], [0, 1, 1, s === LAST ? 1 : 0.85], {extrapolateRight: 'clamp'});
  return <AbsoluteFill style={{opacity: fade}}>
    {s === 's01' && <Hook />}{s === 's02' && <div style={{position:'absolute',inset:0,transform: vertical ? 'scale(1.5)' : undefined}}><Spread vertical={vertical} /></div>}{s === 's03' && <Title vertical={vertical} />}
    {s === 's09' && <Bench vertical={vertical} />}{s === 's12' && <Code vertical={vertical} />}{s === 's13' && <End />}
    {UI.has(s) && <>
      {vertical && <div style={{position: 'absolute', top: 110, left: 0, right: 0, textAlign: 'center', fontSize: 64, fontWeight: 900, color: C.ink}}>Taint <span style={{color: C.red}}>+</span> Receipts</div>}
      <Graph s={s} vertical={vertical} />
      {!vertical && s === 's06' && <div style={{position: 'absolute', left: 110, top: 110}}><Chip c={C.red} d={0}>▶ clicked: “Mark ‘35 h’ claim corrected → taint everything built on it”</Chip></div>}
      <div style={{position: 'absolute', left: vertical ? 175 : (s === 's07' ? 860 : 40), right: vertical ? 175 : (s === 's07' ? 90 : 40), top: vertical ? (s === 's07' ? 1090 : s === 's06' ? 1250 : 1390) : (s === 's07' ? 645 : 840), transform: vertical ? (s === 's07' ? 'scale(1)' : s === 's06' ? 'scale(1.15)' : 'scale(1.3)') : (s === 's10' ? 'scale(0.9)' : undefined), transformOrigin: '50% 0', display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center'}}><Callout s={s} v={vertical} /></div>
    </>}
    <Captions s={s} vertical={vertical} />
    <Sequence from={Math.round(LEAD * FPS)}><Audio src={staticFile(`${s}.wav`)} /></Sequence>
  </AbsoluteFill>;
};

export const Demo: React.FC<{vertical: boolean}> = ({vertical}) => (
  <AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 30%, #151a26 0%, ${C.bg} 70%)`, fontFamily: FONT}}>
    {IDS.map((s) => <Sequence key={s} from={starts[s]} durationInFrames={s === LAST ? len(s) + 45 : len(s)}><Scene s={s} vertical={vertical} /></Sequence>)}
    <div style={vertical ? {position: 'absolute', left: 0, right: 0, top: 232, textAlign: 'center'} : {position: 'absolute', right: 80, top: 44}}><span style={{display: 'inline-block', padding: '6px 16px', borderRadius: 999, background: '#3d2e00', border: '2px solid #d29922', color: C.yel, fontSize: vertical ? 24 : 20, fontWeight: 800, letterSpacing: 1}}>SYNTHETIC DEMO DATA</span></div>
  </AbsoluteFill>);
