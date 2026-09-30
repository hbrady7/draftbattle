/**
 * Best Ball draft logic — 8-team, 11-round snake.
 *
 * Roster: QB, RB, RB, WR, WR, WR, TE, SUPERFLEX, FLEX, BENCH, BENCH
 *   SUPERFLEX accepts QB/RB/WR/TE
 *   FLEX      accepts RB/WR/TE
 */

export const N_TEAMS = 8;
export const N_ROUNDS = 11;

// Slot definitions in priority fill order
export const SLOT_ORDER = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "SUPERFLEX", "FLEX", "BENCH", "BENCH"];

export function emptyRoster() {
  return SLOT_ORDER.map((slot) => ({ slot, player: null }));
}

export function defaultTeamNames(myTeam) {
  return Array.from({ length: N_TEAMS }, (_, i) =>
    i === myTeam ? "My Team" : `Team ${i + 1}`
  );
}

/** 0-based pick → 0-based team index (snake) */
export function teamForPick(pickIndex, nTeams = N_TEAMS) {
  const round = Math.floor(pickIndex / nTeams);
  const pos = pickIndex % nTeams;
  return round % 2 === 0 ? pos : nTeams - 1 - pos;
}

export function pickMeta(pickIndex, nTeams = N_TEAMS) {
  const round = Math.floor(pickIndex / nTeams) + 1;
  const team = teamForPick(pickIndex, nTeams);
  const pickInRound = (pickIndex % nTeams) + 1;
  return { round, team, pickInRound, overall: pickIndex + 1 };
}

export function canSlot(slot, position) {
  if (slot === position) return true;
  if (slot === "SUPERFLEX") return ["QB", "RB", "WR", "TE"].includes(position);
  if (slot === "FLEX") return ["RB", "WR", "TE"].includes(position);
  if (slot === "BENCH") return true;
  return false;
}

// Slot priority: exact > SUPERFLEX > FLEX > BENCH
function slotPriority(slot, pos) {
  if (slot === pos) return 0;
  if (slot === "SUPERFLEX") return 1;
  if (slot === "FLEX") return 2;
  if (slot === "BENCH") return 3;
  return 4;
}

/**
 * Given a flat list of player objects, assign them to best-ball slots optimally.
 */
export function buildOptimalRoster(players) {
  const byPos = { QB: [], RB: [], WR: [], TE: [] };
  for (const p of players) {
    if (byPos[p.position]) byPos[p.position].push(p);
  }
  for (const arr of Object.values(byPos)) arr.sort((a, b) => (b.points ?? 0) - (a.points ?? 0));

  const used = new Set();
  const result = [];

  const takeFrom = (slot, pos, n = 1) => {
    let taken = 0;
    for (const p of byPos[pos] ?? []) {
      if (!used.has(p.id) && taken < n) { used.add(p.id); result.push({ slot, player: p }); taken++; }
    }
    for (let i = taken; i < n; i++) result.push({ slot, player: null });
  };

  const takeBest = (slot, positions) => {
    const cands = positions
      .flatMap((pos) => (byPos[pos] ?? []).filter((p) => !used.has(p.id)))
      .sort((a, b) => (b.points ?? 0) - (a.points ?? 0));
    if (cands.length) { used.add(cands[0].id); result.push({ slot, player: cands[0] }); }
    else result.push({ slot, player: null });
  };

  takeFrom("QB", "QB", 1);
  takeFrom("RB", "RB", 2);
  takeFrom("WR", "WR", 3);
  takeFrom("TE", "TE", 1);
  takeBest("FLEX", ["RB", "WR", "TE"]);
  takeBest("SUPERFLEX", ["QB", "RB", "WR", "TE"]);
  

  const benched = players.filter((p) => !used.has(p.id))
    .sort((a, b) => (b.points ?? 0) - (a.points ?? 0));
  for (const p of benched) result.push({ slot: "BENCH", player: p });
  while (result.length < N_ROUNDS) result.push({ slot: "BENCH", player: null });

  return result;
}

/** Add `player` to `roster` and re-optimize all slot assignments. */
export function assignPlayer(roster, player) {
  const existing = roster.filter((r) => r.player).map((r) => r.player);
  if (existing.length >= N_ROUNDS) return null;
  return buildOptimalRoster([...existing, player]);
}

export function rosterNeeds(roster) {
  const counts = {};
  const filled = {};
  for (const row of roster) {
    counts[row.slot] = (counts[row.slot] || 0) + 1;
    if (row.player) filled[row.slot] = (filled[row.slot] || 0) + 1;
  }
  const open = {};
  for (const k of Object.keys(counts)) open[k] = counts[k] - (filled[k] || 0);

  const skillOpen =
    (open.RB || 0) + (open.WR || 0) + (open.TE || 0) +
    (open.FLEX || 0) + (open.SUPERFLEX || 0);
  const qbOpen = (open.QB || 0) + (open.SUPERFLEX || 0);

  let sfOccupantPts = 0;  
  let sfOccupantPos = null;
  let flexOccupantPts = 0; 
  for (const row of roster) {
    if (row.slot === "SUPERFLEX" && row.player) {
      sfOccupantPts = row.player.points ?? 0;
      sfOccupantPos = row.player.position;
    }
    if (row.slot === "FLEX" && row.player) {
      flexOccupantPts = row.player.points ?? 0;
    }
  }
  const sfNonQbPts = sfOccupantPos && sfOccupantPos !== "QB" ? sfOccupantPts : 0;

  return { open, skillOpen, qbOpen, filled, counts,
           sfOccupantPts, sfOccupantPos, sfNonQbPts, flexOccupantPts };
}

export function marketRank(player) {
  return player.ranking ?? 999;
}

export function upsideVor(player) {
  return player.p10_vor ?? player.ceiling_vor ?? player.points_vor ?? 0;
}

export function upsidePts(player) {
  return player.p10 ?? player.ceiling ?? player.points ?? 0;
}

function needMultiplier(teamRoster, position) {
  const { open, skillOpen, qbOpen, sfNonQbPts, sfOccupantPts, flexOccupantPts } = rosterNeeds(teamRoster);
  if (position === "QB") {
    if (qbOpen > 0) return 2.8;
    if (sfNonQbPts > 0) return 1.6; 
    if (open.BENCH > 0) return 0.4;
    return 0.05;
  }
  if (position === "RB" || position === "WR" || position === "TE") {
    if (open[position] > 0) return 2.3;
    if (skillOpen > 0) return 1.4;
    if (sfOccupantPts > 0 || flexOccupantPts > 0) return 0.9;
    if (open.BENCH > 0) return 0.5;
    return 0.05;
  }
  return 0.3;
}

export function botPickScore(player, teamRoster, pickOverall) {
  const rank = marketRank(player);
  const need = needMultiplier(teamRoster, player.position);
  const ceilVal = upsideVor(player) || upsidePts(player);
  const base = 800 / (rank + 2);
  const falling = rank < 900 && pickOverall > rank ? 1 + Math.min(0.4, (pickOverall - rank) / 60) : 1;
  return base * need * (1 + ceilVal / 60) * falling;
}

export function otherPickWindow(pickIndex, myTeam, nTeams = N_TEAMS) {
  const maxPick = nTeams * N_ROUNDS;
  let i = pickIndex;
  if (teamForPick(i, nTeams) === myTeam) {
    i += 1;
    while (i < maxPick && teamForPick(i, nTeams) === myTeam) i += 1;
  }
  const indices = [];
  while (i < maxPick && indices.length < 30) {
    if (teamForPick(i, nTeams) !== myTeam) indices.push(i);
    else break;
    i += 1;
  }
  return indices;
}

export function simulateGoneAndReplacement(available, rosters, pickIndex, myTeam) {
  const pool = [...available];
  const rosterClone = rosters.map((r) => r.map((row) => ({ ...row })));
  const window = otherPickWindow(pickIndex, myTeam);
  const gone = [];

  for (const pIdx of window) {
    if (!pool.length) break;
    const team = teamForPick(pIdx);
    const overall = pIdx + 1;
    let best = null;
    let bestScore = -Infinity;
    for (const p of pool) {
      const s = botPickScore(p, rosterClone[team], overall);
      if (s > bestScore) { bestScore = s; best = p; }
    }
    if (!best) break;
    gone.push({ pick: overall, team, player: best });
    const nextRoster = assignPlayer(rosterClone[team], best);
    if (nextRoster) rosterClone[team] = nextRoster;
    const idx = pool.findIndex((p) => p.id === best.id);
    if (idx >= 0) pool.splice(idx, 1);
  }

  const replacement = {};
  for (const pos of ["QB", "RB", "WR", "TE"]) {
    const left = pool.filter((p) => p.position === pos);
    left.sort((a, b) => upsideVor(b) - upsideVor(a));
    replacement[pos] = left.length ? left[0] : null;
  }

  return { gone, replacement, remaining: pool, window };
}

export function dynamicVor(player, replacement) {
  const rep = replacement[player.position] ? upsideVor(replacement[player.position]) : 0;
  return upsideVor(player) - rep;
}

export function bestBallLineupPts(rosterPlayers, ptsFn) {
  const byPos = { QB: [], RB: [], WR: [], TE: [] };
  for (const p of rosterPlayers) {
    const pts = ptsFn(p);
    byPos[p.position]?.push({ p, pts });
  }
  for (const pos of Object.keys(byPos)) {
    byPos[pos].sort((a, b) => b.pts - a.pts);
  }
  const used = new Set();
  let total = 0;

  const take = (pos, n = 1) => {
    let taken = 0;
    for (const { p, pts } of byPos[pos]) {
      if (!used.has(p.id)) {
        used.add(p.id);
        total += pts;
        taken++;
        if (taken >= n) break;
      }
    }
  };

  take("QB", 1);
  take("RB", 2);
  take("WR", 3);
  take("TE", 1);

  const flCands = ["RB", "WR", "TE"].flatMap((pos) =>
    byPos[pos].filter(({ p }) => !used.has(p.id))
  ).sort((a, b) => b.pts - a.pts);
  if (flCands.length) { used.add(flCands[0].p.id); total += flCands[0].pts; }

  const sfCands = ["QB", "RB", "WR", "TE"].flatMap((pos) =>
    byPos[pos].filter(({ p }) => !used.has(p.id))
  ).sort((a, b) => b.pts - a.pts);
  if (sfCands.length) { used.add(sfCands[0].p.id); total += sfCands[0].pts; }

  return total;
}

export function suggestionScore(player, myRoster, pickOverall, vor) {
  const { open, skillOpen, qbOpen, sfNonQbPts, sfOccupantPts, flexOccupantPts } = rosterNeeds(myRoster);
  const pos = player.position;
  const pts = player.points ?? 0;
  let need = 0.4;

  if (pos === "QB") {
    if (qbOpen > 0) {
      need = 1.4;
    } else if (sfNonQbPts > 0) {
      const upgrade = Math.max(0, pts - sfNonQbPts);
      need = upgrade > 0 ? 0.55 + upgrade * 0.08 : 0.25;
    } else if (open.BENCH > 0) {
      need = 0.25;
    } else {
      need = 0.05;
    }
  } else {
    const exact = open[pos] || 0;
    if (exact > 0) {
      need = 1.5;
    } else if (skillOpen > 0) {
      need = 1.1;
    } else {
      const canUpgradeSF   = sfOccupantPts > 0 && pts > sfOccupantPts;
      const canUpgradeFlex = flexOccupantPts > 0 && pts > flexOccupantPts;
      if (canUpgradeSF || canUpgradeFlex) {
        const weakest = Math.min(
          canUpgradeSF   ? sfOccupantPts   : Infinity,
          canUpgradeFlex ? flexOccupantPts : Infinity
        );
        const upgrade = Math.max(0, pts - weakest);
        need = upgrade > 0 ? 0.45 + upgrade * 0.07 : 0.3;
      } else if (open.BENCH > 0) {
        need = 0.4;
      } else {
        need = 0.05;
      }
    }
  }

  const vorUse = vor ?? upsideVor(player);
  const ceil = upsidePts(player);
  const falling = pickOverall > (player.ranking ?? 999) ? 1.15 : 1.0;
  return need * (vorUse * 1.0 + ceil * 0.06) * falling;
}