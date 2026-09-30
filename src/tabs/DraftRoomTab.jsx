import { useEffect, useMemo, useState } from "react";
import { SLOT_ORDER, teamForPick, pickMeta } from "../sim/bbDraftLogic.js";
import { pickProbabilities } from "../opponents/pickModel.js";
import { useSim } from "../sim/useSim.js";
import { posColor } from "../lib/viz.jsx";

const N_TEAMS = 8, N_ROUNDS = 11;
const TARGET = { QB: 2, RB: 2, WR: 3, TE: 1 };

function needMul(counts, pos) {
  const t = TARGET[pos] ?? 0, c = counts[pos] || 0;
  if (pos === "QB") return c < 1 ? 2.6 : c < 2 ? 1.8 : 0.3;
  return c < t ? 2.2 : c < t + 2 ? 1.2 : 0.5;
}

/** P(player still available at my next pick) via the opponent model over interim picks. */
function pSurvive(player, available, picksLen, my0, profiles) {
  let o = picksLen;
  const interim = [];
  // skip to my next pick
  if (teamForPick(o) === my0) o++;
  while (o < N_TEAMS * N_ROUNDS && teamForPick(o) !== my0 && interim.length < 14) {
    interim.push(teamForPick(o)); o++;
  }
  let surv = 1;
  const counts = {};
  for (const team of interim) {
    const pr = pickProbabilities(available, counts[team] || { QB: 0, RB: 0, WR: 0, TE: 0 },
      [], profiles[team]);
    const i = available.findIndex((p) => p.id === player.id);
    if (i >= 0) surv *= (1 - (pr[i] || 0));
  }
  return surv;
}

function buildRecs(available, myRoster, picksLen, my0, profiles) {
  const counts = { QB: 0, RB: 0, WR: 0, TE: 0 };
  for (const p of myRoster) counts[p.position] = (counts[p.position] || 0) + 1;
  const scored = available.map((p) => ({ p, score: (p.mean ?? 0) * needMul(counts, p.position) }));
  scored.sort((a, b) => b.score - a.score);
  const picked = new Set();
  const recs = [];
  for (const pos of ["QB", "RB", "WR", "TE"]) {  // guarantee best-available per position
    const best = scored.find((s) => s.p.position === pos);
    if (best && !picked.has(best.p.id)) { picked.add(best.p.id); recs.push(best); }
  }
  for (const s of scored) { if (recs.length >= 8) break; if (!picked.has(s.p.id)) { picked.add(s.p.id); recs.push(s); } }
  return recs.slice(0, 8).sort((a, b) => b.score - a.score)
    .map(({ p }) => ({ p, pSurv: pSurvive(p, available, picksLen, my0, profiles) }));
}

export default function DraftRoomTab({ board, sim, opponents }) {
  const [mySeat, setMySeat] = useState(4);
  const [picks, setPicks] = useState([]);
  const [search, setSearch] = useState("");
  const simApi = useSim(board, sim, opponents, { universeSize: 200, nSim: 12000 });
  const [win, setWin] = useState({ floor: null, fill: null });
  const [myStats, setMyStats] = useState(null);

  const byId = useMemo(() => new Map(board.map((p) => [p.id, p])), [board]);
  const draftedIds = useMemo(() => new Set(picks.map((p) => p.id)), [picks]);
  const my0 = mySeat - 1;
  const currentOverall = picks.length;
  const currentTeam = currentOverall < N_TEAMS * N_ROUNDS ? teamForPick(currentOverall) : null;

  const rostersByTeam = useMemo(() => {
    const r = Array.from({ length: N_TEAMS }, () => []);
    for (const pk of picks) r[pk.team].push(byId.get(pk.id));
    return r;
  }, [picks, byId]);

  useEffect(() => {
    if (!simApi.ready || !simApi.universe) return;
    const localOf = simApi.universe.localOf;
    const rLocal = rostersByTeam.map((team) => team.map((p) => localOf.get(p.id)).filter((x) => x != null));
    if (rLocal[my0].length === 0) { setWin({ floor: null, fill: null }); setMyStats(null); return; }
    let cancel = false;
    simApi.score(rLocal, my0).then((res) => { if (!cancel) { setWin((w) => ({ ...w, floor: res.winPct })); setMyStats(res); } });
    const availableIdx = simApi.universe.players.filter((p) => !draftedIds.has(p.id)).map((p) => p.idx);
    simApi.fill(rLocal, availableIdx, currentOverall, my0, 24).then((res) => { if (!cancel) setWin((w) => ({ ...w, fill: res.winPct })); });
    return () => { cancel = true; };
  }, [picks, simApi.ready]); // eslint-disable-line react-hooks/exhaustive-deps

  const available = useMemo(() => {
    const uni = simApi.universe?.pool ?? board;
    return uni.filter((p) => !draftedIds.has(p.id));
  }, [simApi.universe, board, draftedIds]);

  const searched = useMemo(() => {
    const q = search.toLowerCase().trim();
    let a = q ? available.filter((p) => p.name.toLowerCase().includes(q)) : available;
    return a.slice().sort((x, y) => (y.mean ?? 0) - (x.mean ?? 0)).slice(0, 40);
  }, [available, search]);

  const recs = useMemo(
    () => (opponents ? buildRecs(available, rostersByTeam[my0], picks.length, my0, opponents.profiles) : []),
    [available, rostersByTeam, picks.length, my0, opponents]);

  const draft = (id) => setPicks([...picks, { overall: picks.length, team: teamForPick(picks.length), id }]);
  const undo = () => setPicks(picks.slice(0, -1));
  const reset = () => setPicks([]);

  function exportJson() {
    const out = {
      meta: { my_seat: mySeat, week: 4, n_teams: N_TEAMS, n_rounds: N_ROUNDS },
      teams: rostersByTeam.map((r, t) => ({
        seat: t + 1, is_me: t === my0,
        players: r.map((p) => ({ id: p.id, name: p.name, position: p.position, team: p.team })),
      })),
      predictions: picks.map((pk) => ({ overall: pk.overall + 1, team: pk.team + 1, id: pk.id, name: byId.get(pk.id)?.name })),
    };
    const blob = new Blob([JSON.stringify(out, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `draft_seat${mySeat}.json`; a.click();
  }

  const fmt = (v) => (v == null ? "…" : `${v.toFixed(1)}%`);
  const teamPicks = (t) => picks.filter((p) => p.team === t);

  return (
    <div className="draftroom">
      <div className="dr-header">
        <div className="seat-pick">
          <label>My seat
            <select value={mySeat} onChange={(e) => { setMySeat(+e.target.value); }}>
              {Array.from({ length: N_TEAMS }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}
            </select>
          </label>
          <div className="onclock">
            {currentTeam == null ? "Draft complete"
              : <>Pick {currentOverall + 1} · R{pickMeta(currentOverall).round} ·
                <b className={currentTeam === my0 ? " me" : ""}> {currentTeam === my0 ? "YOUR PICK" : `Team ${currentTeam + 1}`}</b></>}
          </div>
        </div>
        <div className="winbox">
          <div className="winmain">
            <span className="winlabel">win %</span>
            <span className="winval">{fmt(win.fill)}</span>
            <span className="winfloor">floor {fmt(win.floor)}</span>
          </div>
          <div className="winmeta">
            {myStats ? <>proj {myStats.myMean.toFixed(0)} pts · 90% CI [{myStats.p05.toFixed(0)}–{myStats.p95.toFixed(0)}] · rank {myStats.rank}/8</> : "draft a player to start the sim"}
          </div>
          <div className="winnote">8-team baseline is 12.5%; a strong draft lands ~18–25%.{!simApi.ready && " (sim loading…)"}</div>
        </div>
        <div className="dr-controls">
          <button onClick={undo} disabled={!picks.length}>Undo</button>
          <button onClick={reset} disabled={!picks.length}>Reset</button>
          <button onClick={exportJson} disabled={!picks.length}>Export JSON</button>
        </div>
      </div>

      <div className="dr-body">
        <div className="dr-grid-wrap">
          <table className="dr-grid">
            <thead><tr><th></th>{Array.from({ length: N_TEAMS }, (_, t) =>
              <th key={t} className={t === my0 ? "me-col" : ""}>{t === my0 ? "ME" : `T${t + 1}`}</th>)}</tr></thead>
            <tbody>
              {Array.from({ length: N_ROUNDS }, (_, r) => (
                <tr key={r}>
                  <td className="round-num">{r + 1}</td>
                  {Array.from({ length: N_TEAMS }, (_, t) => {
                    const p = teamPicks(t)[r] ? byId.get(teamPicks(t)[r].id) : null;
                    const isNext = currentTeam === t && teamPicks(t).length === r;
                    return (
                      <td key={t} className={"cell" + (t === my0 ? " me-col" : "") + (isNext ? " on-clock" : "")}>
                        {p ? <span style={{ borderLeft: `3px solid ${posColor(p.position)}`, paddingLeft: 4 }}>
                          <b>{p.position}</b> {p.name.split(" ").slice(-1)[0]}</span> : (isNext ? "◄" : "")}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pred-strips">
            {Array.from({ length: N_TEAMS }, (_, t) => t !== my0 && opponents && (
              <div key={t} className="pred-strip">
                <span className="pred-team">T{t + 1} likely next:</span>
                {(() => {
                  const counts = {}; for (const p of rostersByTeam[t]) counts[p.position] = (counts[p.position] || 0) + 1;
                  const pr = pickProbabilities(available, counts, [], opponents.profiles[t]);
                  return available.map((p, i) => ({ p, pr: pr[i] })).sort((a, b) => b.pr - a.pr).slice(0, 3)
                    .map(({ p, pr }) => <span key={p.id} className="pred-chip">{p.name.split(" ").slice(-1)[0]} {(pr * 100).toFixed(0)}%</span>);
                })()}
              </div>
            ))}
          </div>
        </div>

        <div className="dr-side">
          <div className="recs">
            <h3>Recommendations {currentTeam === my0 ? "(your pick)" : "(your next pick)"}</h3>
            {recs.map(({ p, pSurv }) => (
              <div key={p.id} className="rec" onClick={() => currentTeam === my0 && draft(p.id)}>
                <span className="rec-pos" style={{ color: posColor(p.position) }}>{p.position}</span>
                <span className="rec-name">{p.name}</span>
                <span className="rec-mean">{p.mean?.toFixed(1)}</span>
                <span className="rec-surv" title="P(available at your next pick)">{(pSurv * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
          <div className="sideboard">
            <input placeholder="search to draft…" value={search} onChange={(e) => setSearch(e.target.value)} />
            <div className="side-list">
              {searched.map((p) => (
                <div key={p.id} className="side-row" onClick={() => draft(p.id)}>
                  <span className="rec-pos" style={{ color: posColor(p.position) }}>{p.position}</span>
                  <span className="side-name">{p.name}</span>
                  <span className="muted">{p.team}</span>
                  <span className="side-mean">{p.mean?.toFixed(1)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
