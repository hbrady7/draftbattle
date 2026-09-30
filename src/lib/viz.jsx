/** Tiny inline-SVG visualizations (BRIEF §14: no chart library). */
import { summarize } from "../sim/projDist.js";

const POS_COLOR = { QB: "var(--pos-qb)", RB: "var(--pos-rb)", WR: "var(--pos-wr)", TE: "var(--pos-te)" };

/** 90% CI range bar: [p05,p95] bar, mean dot, DB proj tick. Shared 0..domainMax. */
export function CIBar({ p05, p95, mean, dbProj, domainMax = 45, w = 130, h = 14 }) {
  const x = (v) => Math.max(0, Math.min(1, v / domainMax)) * w;
  const y = h / 2;
  return (
    <svg width={w} height={h} className="cibar" role="img">
      <line x1={0} y1={y} x2={w} y2={y} stroke="var(--border)" strokeWidth="1" />
      <rect x={x(p05)} y={y - 3} width={Math.max(1, x(p95) - x(p05))} height={6}
            rx="2" fill="var(--accent)" opacity="0.28" />
      {Number.isFinite(dbProj) && (
        <line x1={x(dbProj)} y1={y - 6} x2={x(dbProj)} y2={y + 6}
              stroke="var(--muted)" strokeWidth="1.5" />
      )}
      <circle cx={x(mean)} cy={y} r="3" fill="var(--accent)" />
    </svg>
  );
}

/** Density curve from min/max/knots, with p05/p50/p95 guides + DNP mass note. */
export function PdfCurve({ min, max, knots, pPlay = 1, p05, p50, p95, w = 320, h = 120 }) {
  const s = summarize(min, max, knots);
  if (!s) return null;
  const n = s.knots.length;
  const peak = Math.max(...s.knots, 1e-9);
  const pad = 8;
  const iw = w - pad * 2, ih = h - pad * 2;
  const px = (i) => pad + (i / (n - 1)) * iw;
  const py = (v) => pad + ih - (v / peak) * ih;
  const line = s.knots.map((v, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");
  const area = `${line} L${px(n - 1).toFixed(1)},${(pad + ih).toFixed(1)} L${px(0).toFixed(1)},${(pad + ih).toFixed(1)} Z`;
  const vx = (val) => pad + Math.max(0, Math.min(1, (val - min) / (max - min))) * iw;
  const dnp = Math.round((1 - pPlay) * 100);
  return (
    <div>
      <svg width={w} height={h} className="pdfcurve" role="img">
        <path d={area} fill="var(--accent)" opacity="0.14" />
        <path d={line} fill="none" stroke="var(--accent)" strokeWidth="1.6" />
        {[[p05, "p05"], [p50, "p50"], [p95, "p95"]].map(([v, lbl]) =>
          Number.isFinite(v) ? (
            <g key={lbl}>
              <line x1={vx(v)} y1={pad} x2={vx(v)} y2={pad + ih} stroke="var(--muted)"
                    strokeWidth="1" strokeDasharray="2,2" />
              <text x={vx(v)} y={h - 1} fontSize="8" fill="var(--muted)" textAnchor="middle">{lbl}</text>
            </g>
          ) : null)}
      </svg>
      {dnp > 0 && <div className="dnp-note">+ {dnp}% chance did-not-play (point mass at 0)</div>}
    </div>
  );
}

export function PosDot({ position }) {
  return <span className="posdot" style={{ background: POS_COLOR[position] || "var(--muted)" }}>{position}</span>;
}

export function posColor(position) { return POS_COLOR[position] || "var(--muted)"; }
