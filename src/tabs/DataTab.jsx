import { useState } from "react";

function parseCsv(text, maxRows = 12) {
  const lines = text.trim().split(/\r?\n/);
  const split = (l) => l.match(/(".*?"|[^,]+)(?=,|$)/g)?.map((s) => s.replace(/^"|"$/g, "")) ?? [];
  const header = split(lines[0]);
  const rows = lines.slice(1, maxRows + 1).map(split);
  return { header, rows, total: lines.length - 1 };
}

export default function DataTab({ meta }) {
  const [preview, setPreview] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setPreview({ name: file.name, ...parseCsv(String(reader.result)) });
    reader.readAsText(file);
  };

  const built = meta?.built_at ? new Date(meta.built_at).toLocaleString() : "—";
  return (
    <div className="data-tab">
      <section className="card">
        <h3>Build status</h3>
        <div className="kv-grid">
          <div><span className="k">week</span><span className="v">{meta?.week ?? "—"} ({meta?.season ?? "—"})</span></div>
          <div><span className="k">built</span><span className="v">{built}</span></div>
          <div><span className="k">players</span><span className="v">{meta?.n_players ?? "—"}</span></div>
          <div><span className="k">DB-only</span><span className="v">{meta?.db_only ?? "—"}</span></div>
          <div><span className="k">backup QB</span><span className="v">{meta?.backup_qb ?? "—"}</span></div>
          <div><span className="k">phase</span><span className="v">{meta?.phase ?? "—"}</span></div>
        </div>
        <p className="muted small">mean recipe: {meta?.mean_recipe ?? "—"}</p>
      </section>

      <section className="card">
        <h3>Scoring config</h3>
        <div className="scoring-row">
          {meta?.scoring && Object.entries(meta.scoring).filter(([k]) => !k.startsWith("_")).map(([k, v]) => (
            <span key={k} className="pill">{k} <b>{v}</b></span>
          ))}
        </div>
        <p className="phase-note">The FFA scoring-mismatch check (4 vs 6 pt pass TD) and cache-age
          readout are wired in <b>Phase 11</b>. Unmatched names live in <code>build/unmatched.txt</code>
          (0 rows this build; not served over HTTP).</p>
      </section>

      <section className="card">
        <h3>New week CSV preview</h3>
        <p className="muted small">Drop an <code>ffa.csv</code> or DB CSV to preview it (parsed locally, nothing is uploaded).</p>
        <div className={"dropzone" + (dragOver ? " over" : "")}
             onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
             onDragLeave={() => setDragOver(false)} onDrop={onDrop}>
          {preview ? `${preview.name} — ${preview.total} rows` : "drop a .csv here"}
        </div>
        {preview && (
          <div className="table-wrap">
            <table className="preview-table">
              <thead><tr>{preview.header.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
              <tbody>{preview.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
