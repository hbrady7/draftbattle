/** Results tab (BRIEF §14.4): after `make_week.py --week N --score`, each of my
 *  drafted players' actual vs his 90% CI, plus contest coverage. Read-only. */
export default function ResultsTab({ scorecard }) {
  if (!scorecard || !(scorecard.weeks?.length || scorecard.my_results?.length)) {
    return (
      <div className="panel">
        <h1 className="panel-title">Results</h1>
        <div className="placeholder">
          <span className="placeholder-badge">no scored week yet</span>
          <p>After the games, run <code>python scripts/make_week.py --week N --score</code>. This pulls
            the actual box scores (re-scored with your scoring), compares each of your drafted players to his
            90% interval, and reports contest coverage + how the model did vs FFA / DB / ECR. It then shows up here.</p>
        </div>
      </div>
    );
  }
  const rows = scorecard.my_results || [];
  const cov = scorecard.coverage90;
  return (
    <div className="panel" style={{ maxWidth: 820 }}>
      <h1 className="panel-title">Results</h1>
      {cov != null && (
        <div className="callout">90% interval coverage this week: {(cov * 100).toFixed(0)}%
          {rows.length ? ` (${rows.filter((r) => r.in_ci).length}/${rows.length} of your players)` : ""}.</div>
      )}
      {rows.length > 0 && (
        <table className="mtab">
          <thead><tr><th>player</th><th>pos</th><th>actual</th><th>90% CI</th><th>in CI?</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id || r.name}>
                <td>{r.name}</td><td>{r.position}</td>
                <td className="num strong">{r.actual?.toFixed(1)}</td>
                <td className="num dim">[{r.p05?.toFixed(0)}–{r.p95?.toFixed(0)}]</td>
                <td>{r.in_ci ? "✓" : "✗"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
