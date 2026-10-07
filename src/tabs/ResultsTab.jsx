import { useMemo, useState } from "react";

/** Results tab (BRIEF §14.4): after `make_week.py --week N --score`, the board we actually
 *  shipped vs the box scores. Injury-aware: players who didn't play are split out (scored
 *  by the availability model), so interval coverage + abs error are on players who played. */
const CLASS_LABEL = { played: "", injury_dnp: "injury DNP", other_dnp: "DNP" };
const pct = (x) => (x == null ? "–" : `${(x * 100).toFixed(0)}%`);
const sign = (x) => (x == null ? "–" : `${x > 0 ? "+" : ""}${x.toFixed(1)}`);

export default function ResultsTab({ scorecard }) {
  const [pos, setPos] = useState("ALL");
  const [sortBy, setSortBy] = useState("db_rank");
  const rows = useMemo(() => {
    const r = (scorecard?.my_results || []).filter((x) => pos === "ALL" || x.position === pos);
    const key = (x) => (sortBy === "abs_err" ? -(x.abs_err ?? -1) : sortBy === "actual" ? -x.actual : x.db_rank);
    return [...r].sort((a, b) => key(a) - key(b));
  }, [scorecard, pos, sortBy]);

  if (!scorecard?.played) {
    return (
      <div className="panel">
        <h1 className="panel-title">Results</h1>
        <div className="placeholder">
          <span className="placeholder-badge">no scored week yet</span>
          <p>After the games, run <code>python scripts/make_week.py --week N --score</code>. It scores the
            board snapshot from that week's build against the actual box scores.</p>
        </div>
      </div>
    );
  }
  const P = scorecard.played, A = scorecard.availability || {};
  const byPos = scorecard.by_pos || {};
  return (
    <div className="panel" style={{ maxWidth: 1000 }}>
      <h1 className="panel-title">Results · {scorecard.season} Week {scorecard.week}</h1>
      <div className="callout">
        Players who played (n={P.n}, {scorecard.universe}): <b>90% interval coverage {pct(P.coverage90)}</b>
        {" "}({pct(P.below)} below · {pct(P.above)} above) · <b>mean abs error {P.mae} pts</b> · bias {sign(P.bias)} ·
        avg interval width {P.width90}.
        <br />
        Availability: expected {A.expected_dnp} DNPs, actual {A.injury_dnp} injury + {A.other_dnp} other.
        Shipped interval incl. DNP mass covered {pct(scorecard.coverage90_shipped)} of all {scorecard.n}.
      </div>

      <table className="mtab" style={{ marginBottom: 16 }}>
        <thead><tr><th>pos</th><th className="num">n</th><th className="num">90% cov</th><th className="num">MAE</th>
          <th className="num">bias</th><th className="num">width</th></tr></thead>
        <tbody>
          {Object.entries(byPos).map(([p, v]) => (
            <tr key={p}>
              <td>{p}</td><td className="num">{v.n}</td>
              <td className={`num ${Math.abs(v.coverage90 - 0.9) <= 0.05 ? "good" : "bad"}`}>{pct(v.coverage90)}</td>
              <td className="num">{v.mae}</td><td className="num">{sign(v.bias)}</td><td className="num">{v.width90}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ display: "flex", gap: 8, marginBottom: 8, fontSize: 12.5 }}>
        {["ALL", "QB", "RB", "WR", "TE"].map((p) => (
          <button key={p} className={"chip" + (pos === p ? " chip-on" : "")} onClick={() => setPos(p)}>{p}</button>
        ))}
        <span className="dim" style={{ marginLeft: 12 }}>sort:</span>
        {[["db_rank", "DB rank"], ["abs_err", "abs error"], ["actual", "actual"]].map(([k, l]) => (
          <button key={k} className={"chip" + (sortBy === k ? " chip-on" : "")} onClick={() => setSortBy(k)}>{l}</button>
        ))}
      </div>
      <table className="mtab">
        <thead><tr><th className="num">rk</th><th>player</th><th>pos</th><th className="num">proj</th>
          <th className="num">actual</th><th className="num">abs err</th><th className="num">90% CI</th>
          <th>in CI?</th><th>status</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="num dim">{r.db_rank}</td>
              <td>{r.name}</td><td>{r.position}</td>
              <td className="num">{r.mean?.toFixed(1)}</td>
              <td className="num strong">{r.actual?.toFixed(1)}</td>
              <td className="num">{r.abs_err == null ? "–" : r.abs_err.toFixed(1)}</td>
              <td className="num dim">[{r.c05?.toFixed(0)}–{r.c95?.toFixed(0)}]</td>
              <td className={r.in_ci == null ? "dim" : r.in_ci ? "good" : "bad"}>
                {r.in_ci == null ? "–" : r.in_ci ? "✓" : r.actual > r.c95 ? "✗ high" : "✗ low"}</td>
              <td className="dim">{[CLASS_LABEL[r.class], r.status && r.status.toLowerCase(),
                r.class !== "played" && `p(play) ${pct(r.p_play)}`].filter(Boolean).join(" · ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
