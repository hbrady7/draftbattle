#!/usr/bin/env node
/** `npm run week -- --week N [--refresh] [--score]` → scripts/make_week.py (§18). */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";

const args = process.argv.slice(2);
const py = existsSync("venv/bin/python") ? "venv/bin/python" : "python3";
const wi = args.indexOf("--week");
const week = wi >= 0 ? args[wi + 1] : "4";
console.log(`→ ${py} scripts/make_week.py ${args.join(" ")}`);
try {
  execFileSync(py, ["scripts/make_week.py", ...args], { stdio: "inherit" });
  if (!args.includes("--score")) console.log(`\nWeek ${week} ready · npm run dev → http://localhost:5175`);
} catch (e) {
  console.error("make_week failed:", e.status ?? e.message);
  process.exit(e.status ?? 1);
}
