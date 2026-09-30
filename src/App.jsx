import { useState } from "react";
import { useData } from "./lib/useData.js";
import BoardTab from "./tabs/BoardTab.jsx";
import DraftRoomTab from "./tabs/DraftRoomTab.jsx";
import DataTab from "./tabs/DataTab.jsx";

const TABS = [
  { id: "board", label: "Board" },
  { id: "draft", label: "Draft Room" },
  { id: "opponents", label: "Opponents" },
  { id: "results", label: "Results" },
  { id: "model", label: "Model" },
  { id: "data", label: "Data" },
];

const PLACEHOLDER = {
  opponents: "Seven editable AI profiles (weights, temperature, notes) + Test replay. Profiles are built and drive the live draft now; the editor UI lands in Phase 11.",
  results: "After scoring a played week (python make_week.py --score): each of my players vs his 90% CI, contest coverage, portfolio report. Phase 11.",
  model: "Backtest + live scorecard, PIT histogram, 90% coverage by position, stack weights, ablation table. Phases 6–11.",
};

export default function App() {
  const [tab, setTab] = useState("board");
  const data = useData();

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◆</span> Draft Battle
          <span className="brand-sub">best-ball projection model · localhost:5175</span>
        </div>
        <div className="build-status">
          {data.meta ? `Week ${data.meta.week} · ${data.meta.n_players} players` : "Phase 5 · baseline"}
        </div>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={"tab" + (t.id === tab ? " tab-active" : "")} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main className={tab === "draft" ? "panel-wide" : "panel"}>
        {data.loading && <div className="placeholder">Loading build data…</div>}
        {data.error && <div className="placeholder error">Failed to load /data/*.json — run <code>npm run week -- --week 4</code> first.<br />{data.error}</div>}
        {!data.loading && !data.error && (
          <>
            {tab === "board" && <BoardTab board={data.board} />}
            {tab === "draft" && <DraftRoomTab board={data.board} sim={data.sim} opponents={data.opponents} />}
            {tab === "data" && <DataTab meta={data.meta} />}
            {PLACEHOLDER[tab] && (
              <div className="panel">
                <h1 className="panel-title">{TABS.find((t) => t.id === tab).label}</h1>
                <div className="placeholder"><span className="placeholder-badge">later phase</span><p>{PLACEHOLDER[tab]}</p></div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
