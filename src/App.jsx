import { useState } from "react";
import { useData } from "./lib/useData.js";
import BoardTab from "./tabs/BoardTab.jsx";
import DraftRoomTab from "./tabs/DraftRoomTab.jsx";
import DataTab from "./tabs/DataTab.jsx";
import ModelTab from "./tabs/ModelTab.jsx";
import OpponentsTab from "./tabs/OpponentsTab.jsx";
import ResultsTab from "./tabs/ResultsTab.jsx";

const TABS = [
  { id: "board", label: "Board" },
  { id: "draft", label: "Draft Room" },
  { id: "opponents", label: "Opponents" },
  { id: "results", label: "Results" },
  { id: "model", label: "Model" },
  { id: "data", label: "Data" },
];

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

      <main className={tab === "draft" ? "panel-wide" : (tab === "board" || tab === "data") ? "panel" : "panelhost"}>
        {data.loading && <div className="placeholder">Loading build data…</div>}
        {data.error && <div className="placeholder error">Failed to load /data/*.json — run <code>npm run week -- --week 4</code> first.<br />{data.error}</div>}
        {!data.loading && !data.error && (
          <>
            {tab === "board" && <BoardTab board={data.board} />}
            {tab === "draft" && <DraftRoomTab board={data.board} sim={data.sim} opponents={data.opponents} aiData={data.aiData} />}
            {tab === "data" && <DataTab meta={data.meta} />}
            {tab === "model" && <ModelTab backtest={data.backtest} params={data.params} scorecard={data.scorecard} />}
            {tab === "opponents" && <OpponentsTab aiData={data.aiData} />}
            {tab === "results" && <ResultsTab scorecard={data.scorecard} />}
          </>
        )}
      </main>
    </div>
  );
}
