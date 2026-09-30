/**
 * Pre-draft DRAFT PLAN vs the DETERMINISTIC bots.
 *
 * The bots take the highest-ranked available player at their script's position, so
 * the whole board is predictable. This forward-simulates the entire snake draft and,
 * at each of MY picks, grabs the best need-weighted player who will NOT survive to my
 * next pick (scarce) — deferring players the bots leave alone. That yields the key
 * move: a high-value faller (a QB a late-QB-script bot ignores until R9, say) gets
 * slotted at the last round before a bot would take him, so I spend early picks on
 * players who won't come back. Value = the ff model mean × positional need; timing =
 * the exact deterministic bot schedule.
 */
import { teamForPick } from "../sim/bbDraftLogic.js";
import { deterministicPickIndex, aiByName } from "./aiModel.js";

const N_TEAMS = 8, N_ROUNDS = 11, TOTAL = N_TEAMS * N_ROUNDS;
const TARGET = { QB: 2, RB: 2, WR: 3, TE: 1 };

function needMul(counts, pos) {
  const t = TARGET[pos] ?? 0, c = counts[pos] || 0;
  if (pos === "QB") return c < 1 ? 2.6 : c < 2 ? 1.8 : 0.3;   // superflex → want ~2 QB
  return c < t ? 2.2 : c < t + 2 ? 1.2 : 0.5;
}
const rankOf = (p) => p.db_rank ?? p.rank ?? 9999;
const val = (p, counts) => (p.mean ?? 0) * needMul(counts, p.position);

export function planDraft({ board, aiData, aiSeats, mySeat, picks = [] }) {
  const my0 = mySeat - 1;
  const aiMap = aiByName(aiData);
  const byId = new Map(board.map((p) => [p.id, p]));
  const taken = new Set(picks.map((p) => p.id));
  let pool = board.filter((p) => p && p.mean != null && !taken.has(p.id));

  const counts = Array.from({ length: N_TEAMS }, () => ({ QB: 0, RB: 0, WR: 0, TE: 0 }));
  for (const pk of picks) { const p = byId.get(pk.id); if (p) counts[pk.team][p.position]++; }
  const myCounts = counts[my0];

  const myOveralls = [];
  for (let o = picks.length; o < TOTAL; o++) if (teamForPick(o) === my0) myOveralls.push(o);

  const plan = [];
  for (let o = picks.length; o < TOTAL; o++) {
    const team = teamForPick(o), round = Math.floor(o / N_TEAMS) + 1;
    if (team !== my0) {                                   // bot pick — deterministic
      const ai = aiMap[aiSeats[team]];
      const idx = ai ? deterministicPickIndex(pool, ai, round, counts[team]) : -1;
      if (idx >= 0 && idx < pool.length) { const p = pool[idx]; counts[team][p.position]++; pool = pool.filter((_, i) => i !== idx); }
      continue;
    }
    // MY pick: simulate the bots from here to my NEXT pick → who won't survive.
    const nextO = myOveralls.find((x) => x > o) ?? TOTAL;
    const simPool = pool.slice();
    const simCounts = counts.map((c) => ({ ...c }));
    const botTake = new Map();                            // id → round a bot would take him
    for (let oo = o + 1; oo < nextO; oo++) {
      const tt = teamForPick(oo); if (tt === my0) break;
      const rr = Math.floor(oo / N_TEAMS) + 1;
      const ai = aiMap[aiSeats[tt]];
      const idx = ai ? deterministicPickIndex(simPool, ai, rr, simCounts[tt]) : -1;
      if (idx >= 0 && idx < simPool.length) { const p = simPool[idx]; botTake.set(p.id, rr); simCounts[tt][p.position]++; simPool.splice(idx, 1); }
    }
    // grab the best need-fitting player who's SCARCE (gone if I wait); else best available
    const scarceNeeded = pool.filter((p) => botTake.has(p.id) && needMul(myCounts, p.position) >= 0.8);
    const from = scarceNeeded.length ? scarceNeeded : pool;
    let pick = null;
    for (const p of from) if (!pick || val(p, myCounts) > val(pick, myCounts)) pick = p;
    if (!pick) break;

    const scarce = botTake.has(pick.id);
    const rk = rankOf(pick);
    const steal = round - Math.max(1, Math.ceil(rk / N_TEAMS));   // taken this many rounds later than rank
    let rationale;
    if (scarce && steal >= 2) rationale = `value steal — ranked #${rk} but a bot grabs him ~R${botTake.get(pick.id)}`;
    else if (scarce) rationale = `scarce — a bot takes him ~R${botTake.get(pick.id)} if you wait`;
    else rationale = "best available — nothing scarcer worth taking";
    plan.push({ round, overall: o, player: pick, value: +val(pick, myCounts).toFixed(1),
                rank: rk, mean: pick.mean, scarce, steal, rationale });

    pool = pool.filter((p) => p.id !== pick.id);
    myCounts[pick.position]++;
  }
  return plan;
}
