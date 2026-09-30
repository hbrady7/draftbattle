import { useMemo, useState } from "react";
import { CIBar, PdfCurve, posColor } from "../lib/viz.jsx";

const POSITIONS = ["ALL", "QB", "RB", "WR", "TE"];

function edgeStyle(edge) {
  const mag = Math.min(1, Math.abs(edge) / 8);
  const hue = edge >= 0 ? 145 : 5;
  return { color: `hsl(${hue} 70% ${55 + mag * 15}%)`, fontWeight: Math.abs(edge) > 3 ? 700 : 400 };
}

function Drawer({ p, onClose }) {
  const src = p.sources || {};
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="drawer-close" onClick={onClose}>×</button>
        <h2 style={{ borderLeft: `3px solid ${posColor(p.position)}`, paddingLeft: 8 }}>
          {p.name} <span className="muted">{p.position} · {p.team ?? "—"} vs {p.opp ?? "—"}</span>
        </h2>
        <div className="drawer-grid">
          <div><span className="k">our mean</span><span className="v">{p.mean?.toFixed(1)}</span></div>
          <div><span className="k">SD</span><span className="v">{p.sd?.toFixed(1)}</span></div>
          <div><span className="k">P(plays)</span><span className="v">{(p.p_play * 100).toFixed(0)}%</span></div>
          <div><span className="k">90% CI</span><span className="v">{p.ci90?.[0]}–{p.ci90?.[1]}</span></div>
          <div><span className="k">DB proj</span><span className="v">{p.db_proj?.toFixed(1)}</span></div>
          <div><span className="k">implied tot</span><span className="v">{p.implied_total ?? "—"}</span></div>
        </div>
        <h3>Weekly distribution</h3>
        <PdfCurve min={p.min} max={p.max} knots={p.knots} pPlay={p.p_play}
                  p05={p.p05} p50={p.p50} p95={p.p95} />
        <h3>Sources</h3>
        <table className="src-table">
          <tbody>
            <tr><td>Our model</td><td>{p.mean?.toFixed(1)}</td></tr>
            <tr><td>FFA</td><td>{src.ffa ?? "—"}</td></tr>
            <tr><td>ECR (rank)</td><td>{src.ecr ?? "—"}</td></tr>
            <tr><td>ECR-implied pts</td><td>{src.ecr_implied ?? "—"}</td></tr>
            <tr><td>DB proj</td><td>{p.db_proj?.toFixed(1)}</td></tr>
          </tbody>
        </table>
        <p className="phase-note">Component breakdown (targets × yds/tgt, TDs), game log, and
          target-share trend arrive with the structural model in <b>Phase 7</b>.</p>
      </aside>
    </div>
  );
}

export default function BoardTab({ board, draftedIds }) {
  const [pos, setPos] = useState("ALL");
  const [hideDrafted, setHideDrafted] = useState(false);
  const [dbOnly, setDbOnly] = useState(false);
  const [injured, setInjured] = useState(false);
  const [sel, setSel] = useState(null);

  const drafted = draftedIds || new Set();
  const rows = useMemo(() => {
    let r = board.filter((p) => (pos === "ALL" || p.position === pos));
    if (hideDrafted) r = r.filter((p) => !drafted.has(p.id));
    if (dbOnly) r = r.filter((p) => p.flags?.db_only);
    if (injured) r = r.filter((p) => p.flags?.injury);
    return r.sort((a, b) => (b.mean ?? 0) - (a.mean ?? 0));
  }, [board, pos, hideDrafted, dbOnly, injured, drafted]);

  const domainMax = useMemo(() => Math.max(30, ...rows.slice(0, 60).map((p) => p.p95 || 0)), [rows]);

  return (
    <div className="board">
      <div className="filters">
        {POSITIONS.map((x) => (
          <button key={x} className={"chip" + (pos === x ? " chip-on" : "")} onClick={() => setPos(x)}>{x}</button>
        ))}
        <label className="chk"><input type="checkbox" checked={dbOnly} onChange={(e) => setDbOnly(e.target.checked)} /> DB-only</label>
        <label className="chk"><input type="checkbox" checked={injured} onChange={(e) => setInjured(e.target.checked)} /> injured</label>
        {draftedIds && <label className="chk"><input type="checkbox" checked={hideDrafted} onChange={(e) => setHideDrafted(e.target.checked)} /> hide drafted</label>}
        <span className="count">{rows.length} players</span>
      </div>
      <div className="table-wrap">
        <table className="board-table">
          <thead>
            <tr>
              <th>Pos</th><th>Name</th><th>Tm</th><th>Opp</th><th>ImpTot</th>
              <th>DBrk</th><th>DBproj</th><th>Mean</th><th>90% CI</th><th>Edge</th><th>SD</th><th>P(play)</th><th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} onClick={() => setSel(p)} className="board-row">
                <td style={{ borderLeft: `3px solid ${posColor(p.position)}` }} className="pos-cell">{p.position}</td>
                <td className="name-cell">{p.name}</td>
                <td>{p.team ?? "—"}</td>
                <td>{p.opp ?? "—"}</td>
                <td>{p.implied_total ?? "—"}</td>
                <td className="muted">{p.db_rank}</td>
                <td className="muted">{p.db_proj?.toFixed(1)}</td>
                <td className="mean-cell">{p.mean?.toFixed(1)}</td>
                <td><CIBar p05={p.p05} p95={p.p95} mean={p.mean} dbProj={p.db_proj} domainMax={domainMax} /></td>
                <td style={edgeStyle(p.edge)}>{p.edge > 0 ? "+" : ""}{p.edge?.toFixed(1)}</td>
                <td className="muted">{p.sd?.toFixed(1)}</td>
                <td className={p.p_play < 1 ? "warn" : "muted"}>{(p.p_play * 100).toFixed(0)}%</td>
                <td className="flags">
                  {p.flags?.db_only && <span className="flag flag-db">DB</span>}
                  {p.flags?.backup_qb && <span className="flag">BKP</span>}
                  {p.flags?.injury && <span className="flag flag-inj">{p.flags.injury.slice(0, 1)}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sel && <Drawer p={sel} onClose={() => setSel(null)} />}
    </div>
  );
}
