import { posColor } from "../lib/viz.jsx";

/** Opponents tab (BRIEF §14.3): the real AI drafters from the 25-room data —
 *  archetype, round script, and top player targets. Read-only. */
export default function OpponentsTab({ aiData }) {
  if (!aiData?.ais?.length) {
    return (
      <div className="panel">
        <h1 className="panel-title">Opponents</h1>
        <div className="placeholder"><span className="placeholder-badge">no data</span>
          <p>Drop the AI-prediction workbook and run <code>scripts/ingest_ai_data.py</code>.</p></div>
      </div>
    );
  }
  const seven = new Set(aiData.meta?.default_seven || []);
  const ais = aiData.ais.filter((a) => seven.has(a.name)); // the usable 7

  return (
    <div className="panel" style={{ maxWidth: 1000 }}>
      <h1 className="panel-title">Opponents</h1>
      <p className="panel-note">The 7 AI drafters, modeled from {aiData.meta?.rooms ?? 25} observed rooms
        ({aiData.meta?.picks ?? 2200} picks). These drive who-falls-to-you and your win% in the Draft Room.</p>
      <div className="ai-cards">
        {ais.map((a) => {
          const top = Object.values(a.priors || {}).sort((x, y) => y.share - x.share).slice(0, 5);
          return (
            <div key={a.name} className="ai-card">
              <div className="ai-card-head">
                <span className="ai-card-name">{a.name}</span>
                <span className="ai-card-arch">{a.archetype}</span>
                <span className="dim small">{a.rooms_faced} rooms</span>
              </div>
              {a.round_script && (
                <div className="ai-script">
                  {a.round_script.map((pos, i) => (
                    <span key={i} className="ai-r" style={{ color: posColor(pos) }} title={`R${i + 1}`}>{pos}</span>
                  ))}
                </div>
              )}
              <div className="ai-targets">
                <div className="dim small" style={{ marginBottom: 3 }}>most-drafted (share of his rooms):</div>
                {top.map((t) => (
                  <div key={t.name} className="ai-target">
                    <span style={{ color: posColor(t.pos), fontWeight: 700, width: 26, display: "inline-block" }}>{t.pos}</span>
                    <span className="ai-target-name">{t.name}</span>
                    <span className="ai-target-share">{(t.share * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
