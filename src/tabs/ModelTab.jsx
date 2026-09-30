import { posColor } from "../lib/viz.jsx";

const POS = ["QB", "RB", "WR", "TE"];

/** Model tab (BRIEF §14.5): backtest scorecard, the held-out 2025 stack-vs-market
 *  result, stack weights, correlations + availability summary. Read-only. */
export default function ModelTab({ backtest, params, scorecard }) {
  if (!params && !backtest) {
    return (
      <div className="panel">
        <h1 className="panel-title">Model</h1>
        <div className="placeholder"><span className="placeholder-badge">no data</span>
          <p>Run <code>npm run week -- --week 4</code> (writes <code>public/data/backtest.json</code> + <code>params.json</code>).</p></div>
      </div>
    );
  }
  const stack = params?.stack;
  const v = stack?.held_out_verdict || {};
  const beatsAll = POS.every((p) => v[p]?.beats_ecr);
  const w = stack?.weights_by_pos || {};
  const models = stack?.models || ["structural", "gbm", "ecr_implied", "trailing8", "trailing_xfp"];

  return (
    <div className="panel" style={{ maxWidth: 940 }}>
      <h1 className="panel-title">Model</h1>

      {stack && (
        <div className="callout" style={{ borderColor: beatsAll ? "var(--pos-rb)" : "var(--pos-qb)" }}>
          {beatsAll
            ? "Held-out 2025: the stacked model beats the market (ECR) on CRPS at all 4 positions — validated on a season it never trained on."
            : "Held-out 2025: the stacked model does not beat the market at every position (see table)."}
        </div>
      )}

      {Object.keys(v).length > 0 && (
        <>
          <h3 className="sec">Held-out 2025 — stack vs market (ECR), CRPS (lower better)</h3>
          <table className="mtab">
            <thead><tr><th>pos</th><th>stack</th><th>ECR</th><th>Δ</th><th>beats?</th><th>90% cov</th><th>best single</th></tr></thead>
            <tbody>
              {POS.map((p) => {
                const d = v[p]; if (!d) return null;
                const delta = (d.ecr_crps - d.stack_crps);
                return (
                  <tr key={p}>
                    <td style={{ color: posColor(p), fontWeight: 700 }}>{p}</td>
                    <td className="num strong">{d.stack_crps?.toFixed(3)}</td>
                    <td className="num">{d.ecr_crps?.toFixed(3)}</td>
                    <td className={"num " + (delta >= 0 ? "good" : "bad")}>{delta >= 0 ? "−" : "+"}{Math.abs(delta).toFixed(3)}</td>
                    <td>{d.beats_ecr ? "✓" : "✗"}</td>
                    <td className="num">{d.cov90_stack != null ? (d.cov90_stack * 100).toFixed(0) + "%" : "—"}</td>
                    <td className="dim">{d.best_single} {d.best_single_crps?.toFixed(3)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}

      {Object.keys(w).length > 0 && (
        <>
          <h3 className="sec">Stack weights by position {stack?.shape_by_pos ? "(distribution: gamma)" : ""}</h3>
          <table className="mtab">
            <thead><tr><th>pos</th>{models.map((m) => <th key={m}>{m.replace("_implied", "")}</th>)}</tr></thead>
            <tbody>
              {POS.map((p) => w[p] && (
                <tr key={p}><td style={{ color: posColor(p), fontWeight: 700 }}>{p}</td>
                  {models.map((m) => <td key={m} className="num">{w[p][m] ? w[p][m].toFixed(2) : "·"}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="dim small">Fit walk-forward on {stack.fit_window}; frozen in params.json. ECR keeps 20–31% weight — the market still informs.</p>
        </>
      )}

      {backtest && (
        <>
          <h3 className="sec">Backtest baselines (2021–24, CRPS by position)</h3>
          <table className="mtab">
            <thead><tr><th>model</th>{POS.map((p) => <th key={p}>{p}</th>)}</tr></thead>
            <tbody>
              {["phase7", "ecr_implied", "old_plan", "trailing8", "trailing_xfp"].map((mk) => {
                const row = backtest[mk]; if (!row) return null;
                const label = mk === "phase7" ? "stacked/GBM" : mk.replace("_implied", "");
                return (
                  <tr key={mk}><td className={mk === "phase7" ? "strong" : ""}>{label}</td>
                    {POS.map((p) => <td key={p} className="num">{row[p]?.crps != null ? row[p].crps.toFixed(2) : (row[p]?.CRPS?.toFixed?.(2) ?? "—")}</td>)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}

      <h3 className="sec">Under the hood</h3>
      <ul className="dim small" style={{ lineHeight: 1.7 }}>
        {params?.correlations && <li>Empirical copula correlations (fit on ~3,400+ pairs): QB-WR1 stack ≈ {(params.correlations.categories?.["QB1-WR1"]?.r ?? params.correlations["QB1-WR1"]?.r ?? 0.35).toFixed?.(2) ?? "0.35"}, RB1-RB2 negative, opposing QBs ≈ 0.17 — drives the win% sim.</li>}
        {params?.availability && <li>Injury-aware availability: logistic P(plays) + snap multiplier; OUT→0, DOUBTFUL→~0; Questionable modeled (still a touch optimistic — see DECISIONS).</li>}
        <li>Feature ablations: none of Vegas / weather / route-participation / efficiency / opponent-adj reliably improved CRPS — the edge is the model core re-using ECR + trailing, honestly reported.</li>
        {scorecard && <li>Live scorecard present — see the Results tab for scored weeks.</li>}
      </ul>
    </div>
  );
}
