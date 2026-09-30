/**
 * `npm run week -- --week N`  (BRIEF §18)
 *
 * Rebuilds public/data/*.json for the week: board -> sim -> opponents.
 * --refresh also re-downloads the §5 sources first (latest injuries/lines).
 *
 * NOTE (baseline): build_board.py / sim.py are Week-4-fixed for now; generalizing
 * --week through the Python pipeline is Phase 11. The flag is accepted and echoed.
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const VENV = join(ROOT, "venv", "bin", "python");
const PY = existsSync(VENV) ? VENV : "python3";

const args = process.argv.slice(2);
const weekIdx = args.indexOf("--week");
const week = weekIdx >= 0 ? args[weekIdx + 1] : "4";
const refresh = args.includes("--refresh");

function run(script, extra = []) {
  console.log(`\n$ ${PY} scripts/${script} ${extra.join(" ")}`);
  execFileSync(PY, [join("scripts", script), ...extra], { cwd: ROOT, stdio: "inherit" });
}

console.log(`=== draftbattle.js weekly build — Week ${week}${refresh ? " (refresh)" : ""} ===`);
if (week !== "4") {
  console.log("  [baseline] Python build is Week-4-fixed; --week is echoed only until Phase 11.");
}
try {
  if (refresh) run("data_sources.py", ["--summary", "--refresh"]);
  run("build_board.py", ["--check"]);
  run("sim.py", ["--build"]);
  run("opponents.py");
  console.log("\n✓ Build complete. public/data updated.");
  console.log("  Open the dashboard:  npm run dev   →  http://localhost:5175");
} catch (e) {
  console.error(`\n✗ Build failed: ${e.message}`);
  process.exit(1);
}
