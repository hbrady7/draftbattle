import { useState } from 'react'

// Six tabs from BRIEF §14. Phase 0 ships the shell that serves on :5175;
// Board / Draft Room / Data get built in Phase 5, the rest in Phase 11.
const TABS = [
  { id: 'board', label: 'Board', note: 'Player table with our mean, 90% CI range bar, edge vs DB, flags. Row drawer opens the PDF + component breakdown.' },
  { id: 'draft', label: 'Draft Room', note: '8×11 snake grid, my seat highlighted. Live win % (expected fill + floor), pick recommendations, opponent next-pick strips.' },
  { id: 'opponents', label: 'Opponents', note: 'Seven editable AI profiles (weights, temperature, notes). Test replays a saved draft for pick hit-rate.' },
  { id: 'results', label: 'Results', note: 'After scoring: each of my players vs his 90% CI, contest coverage, portfolio report.' },
  { id: 'model', label: 'Model', note: 'Backtest + live scorecard, PIT histogram, 90% coverage by position, stack weights, ablation table.' },
  { id: 'data', label: 'Data', note: 'Week selector, CSV drop preview, build status from meta.json, unmatched names, scoring-check result, cache ages.' },
]

export default function App() {
  const [tab, setTab] = useState('board')
  const active = TABS.find((t) => t.id === tab)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◆</span> Draft Battle
          <span className="brand-sub">best-ball projection model · localhost:5175</span>
        </div>
        <div className="build-status">Phase 0 · baseline shell</div>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={'tab' + (t.id === tab ? ' tab-active' : '')}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="panel">
        <h1 className="panel-title">{active.label}</h1>
        <p className="panel-note">{active.note}</p>
        <div className="placeholder">
          <span className="placeholder-badge">under construction</span>
          <p>This tab wires up in a later phase. The app serves and the shell is live.</p>
        </div>
      </main>
    </div>
  )
}
