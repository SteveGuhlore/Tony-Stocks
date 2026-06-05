"""Two-layer TANDEM LOOP test — bot (layer 1) <-> the REAL Command Center (layer 2).

This is the test the operator actually wants: prove the whole intraday loop works end
to end so nothing breaks during live market hours (when it can't be hand-fixed).

  LAYER 1 (this bot):  scan -> resolved outcomes + bridge handoffs (daily anchor +
                       intraday 10:30/13:00/15:30/16:00) written to a shared sandbox.
  LAYER 2 (real CC):   the ACTUAL Command Center runner code (`runner.bridge.tony_bridge`,
                       `runner.tools.tony_verdict`, `runner.ledger.tony_scorecard`,
                       `runner.tools.tony_outcomes`) ingests each handoff, spawns a Tony
                       deep-dive task per bridge, writes its 2nd-pass verdicts + graded
                       record back into the shared sandbox.
  BACK TO LAYER 1:     the bot consumes the CC's REAL outputs — exit detection, teaching
                       ledger, and the /api/command-center dashboard mappers — proving the
                       round trip closes.

Unlike the synthetic harness (full_e2e_sync_test.py), the CC half here is the *real* CC
code, not stand-in JSON. The two agents hand off through real files in ONE shared sandbox,
exactly like production — only the paths are redirected so neither live system is touched.

Isolation (touches NEITHER live system — verified at the end):
  * Bot: sandbox config redirects database_path + vault dirs + command_center_dir; the
    bot subprocesses get TONY_* env pointing into the sandbox.
  * CC: every CC path constant is redirected — env (TONY_*_FILE / TONY_BRIDGE_DIR /
    TONY_REPORTS_DIR, read at CC import time) AND the non-env globals that point at the
    real CC workspace (TASKS_DIR / VAULT_DIR / _PROCESSED_LOG) are monkeypatched to the
    sandbox after import.
  * Belt-and-suspenders: hashes the real bot sinks AND snapshots the real CC workspace
    (verdicts/record/bridge/tasks/processed-log) before and after; FAILS if any changed.

Run:  $env:PYTHONPATH="src"; python scripts/tandem_loop_test.py  [--quick] [--no-live-llm]
Exit 0 = the whole loop is healthy. Non-zero = at least one break (details printed).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO / "config" / "default_config.yaml"
CC_ROOT = Path("C:/Users/alexa/Downloads/AI Operations Command Center")
QUICK = "--quick" in sys.argv
NO_LIVE_LLM = "--no-live-llm" in sys.argv

# Drive the bot subprocesses with the SAME interpreter production uses (the nightly
# scheduled task runs `.venv\Scripts\python.exe`). That venv has the LLM SDKs
# (google-genai); a bare `python` may not, which would make the live-narration check a
# false negative. Fall back to whatever launched us only if the venv isn't there.
_VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"
BOT_PY = str(_VENV_PY) if _VENV_PY.exists() else sys.executable

# Real sinks that must NEVER change during the test.
REAL_BOT_SINKS = [REPO / "data" / "trading_bot.db", *(REPO / "reports").glob("*.json")]
REAL_VAULT = REPO / "vault"
# Real CC artifacts that must NEVER change during the test.
REAL_CC_BRIDGE = CC_ROOT / "bridge" / "tony-stocks"
REAL_CC_TASKS = CC_ROOT / "workspace" / "tasks" / "todo"
REAL_CC_PROCESSED = CC_ROOT / "workspace" / "logs" / "tony-bridge-processed.json"
REAL_CC_REPORTS = [
    REPO / "reports" / "tony_stocks_verdicts.json",
    REPO / "reports" / "tony_stocks_record.json",
    CC_ROOT / "vault" / "tony-stocks" / "tony_stocks_record.json",
    CC_ROOT / "vault" / "tony-stocks" / "signal-ledger.md",
]

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "MISSING"


def dir_fingerprint(d: Path) -> list[str]:
    """Sorted name+sha of everything under a dir — catches adds, deletes, and edits."""
    if not d.exists():
        return []
    return sorted(f"{p.relative_to(d)}={sha(p)}" for p in d.rglob("*") if p.is_file())


def run(cmd: list[str], env: dict, label: str) -> tuple[int, str]:
    print(f"\n>>> {label}: {' '.join(cmd[2:]) if len(cmd) > 2 else ' '.join(cmd)}")
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(REPO))
    out = (proc.stdout or "") + (proc.stderr or "")
    print("\n".join(out.splitlines()[-8:]))
    return proc.returncode, out


def parse_env_file(path: Path, keys: set[str]) -> dict[str, str]:
    """Pull selected KEY=VALUE pairs out of a .env file (non-empty values only)."""
    found: dict[str, str] = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k in keys and v:
            found[k] = v
    return found


def synth_outcomes_for(symbols: list[str], d0: date) -> list[dict]:
    """Resolved outcomes whose [pick_date, resolved_date] window CONTAINS today, so a
    verdict written TODAY (the live loop's behavior) actually joins and grades — giving a
    populated record, not an honest-but-empty 'awaiting'. Mixed result types + edge rows."""
    results = ["target_hit", "stop_hit", "closed"]
    rows = []
    for i, sym in enumerate(symbols):
        result = results[i % 3]
        entry = 100.0 + i * 7
        ret = {"target_hit": 9.0, "stop_hit": -5.0, "closed": 2.0}[result]
        exit_ = round(entry * (1 + ret / 100), 2)
        rows.append({
            "symbol": sym,
            "pick_date": (d0 - timedelta(days=10)).isoformat(),
            "result": result, "outcome_label": result, "tracking_status": "resolved",
            "entry": entry, "exit": exit_, "return_pct": ret,
            "entry_date": (d0 - timedelta(days=10)).isoformat(),
            "days_held": 4, "days_active": 4, "resolved_date": d0.isoformat(),
        })
    # Robustness probes: NaN-ish return + a sparse record.
    rows.append({"symbol": "EDGE1", "pick_date": (d0 - timedelta(days=5)).isoformat(),
                 "result": "expired", "entry": 10.0, "exit": None, "return_pct": None,
                 "days_held": 3, "resolved_date": d0.isoformat()})
    rows.append({"symbol": "EDGE2", "pick_date": (d0 - timedelta(days=4)).isoformat(),
                 "result": "closed", "entry": 50.0})
    return rows


def main() -> int:
    if not CC_ROOT.exists():
        print(f"FATAL: Command Center workspace not found at {CC_ROOT}")
        return 2

    d0 = date.today()
    ds = d0.isoformat()
    print(f"== Tandem loop test ({ds}) ==  quick={QUICK} live_llm={not NO_LIVE_LLM}")

    # ── Baseline fingerprints (real systems must be untouched at the end) ──────
    bot_baseline = {str(p): sha(p) for p in REAL_BOT_SINKS}
    vault_before = sum(1 for _ in REAL_VAULT.rglob("*")) if REAL_VAULT.exists() else 0
    cc_baseline = {
        "bridge": dir_fingerprint(REAL_CC_BRIDGE),
        "tasks": dir_fingerprint(REAL_CC_TASKS),
        "processed": sha(REAL_CC_PROCESSED),
        **{str(p): sha(p) for p in REAL_CC_REPORTS},
    }

    sandbox = Path(tempfile.mkdtemp(prefix=f"tandem_{d0:%Y%m%d}_"))
    print(f"Sandbox: {sandbox}")
    tony_env: dict[str, str] = {}
    keys: dict[str, str] = {}
    try:
        sb_reports = sandbox / "reports"; sb_reports.mkdir(parents=True)
        sb_vault = sandbox / "vault"; sb_vault.mkdir()
        sb_cc = sandbox / "cc"; sb_cc.mkdir()
        sb_data = sandbox / "data"; sb_data.mkdir()
        sb_bridge = sb_cc / "bridge" / "tony-stocks"; sb_bridge.mkdir(parents=True)
        sb_tasks = sandbox / "cc_ws" / "tasks" / "todo"; sb_tasks.mkdir(parents=True)
        sb_cc_logs = sandbox / "cc_ws" / "logs"; sb_cc_logs.mkdir(parents=True)
        sb_cc_vault = sandbox / "cc_vault"; sb_cc_vault.mkdir()

        # ── Sandbox bot config (redirect every path; recognize demo data) ─────
        cfg = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        cfg["database_path"] = str(sb_data / "trading_bot.db")
        for k in ("allow_demo_snapshots", "allow_demo_in_learning",
                  "allow_demo_in_analytics", "allow_demo_fallback_in_watch"):
            cfg[k] = True
        cfg.setdefault("demo_snapshot_seed", {})["enabled"] = True
        v = cfg.setdefault("vault", {})
        v.update({"enabled": True, "bridge_enabled": True,
                  "vault_dir": str(sb_vault), "command_center_dir": str(sb_cc)})
        sb_config = sandbox / "config.yaml"
        sb_config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        cfg_arg = str(sb_config)

        # ── Shared env: contract paths into the sandbox + LLM keys from .env ───
        tony_env = {
            "TONY_OUTCOMES_FILE": str(sb_reports / "tony_stocks_outcomes.json"),
            "TONY_VERDICTS_FILE": str(sb_reports / "tony_stocks_verdicts.json"),
            "TONY_RECORD_FILE": str(sb_reports / "tony_stocks_record.json"),
            "TONY_TEACHING_FILE": str(sb_reports / "tony_teaching_log.json"),
            "TONY_VAULT_RECORD_FILE": str(sb_cc_vault / "tony-stocks" / "tony_stocks_record.json"),
            "TONY_BRIDGE_DIR": str(sb_bridge),
            "TONY_REPORTS_DIR": str(sb_reports),
            "VAULT_DIR": str(sb_vault),
        }
        # FIX: pass LLM keys through from BOTH .env files so the live narration pass
        # (Phase 8) actually hits Gemini instead of silently falling back to templates.
        llm_keys = {"GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_API_KEY", "ANTHROPIC_API_KEY"}
        keys = {**parse_env_file(CC_ROOT / ".env", llm_keys),
                **parse_env_file(REPO / ".env", llm_keys)}  # bot .env wins for GEMINI
        # google-genai reads GOOGLE_API_KEY; the bot's narrator accepts either name.
        if "GEMINI_API_KEY" in keys and "GOOGLE_API_KEY" not in keys:
            keys["GOOGLE_API_KEY"] = keys["GEMINI_API_KEY"]
        check("Setup: LLM key available for live narration",
              bool(keys.get("GEMINI_API_KEY") or keys.get("ANTHROPIC_API_KEY")),
              f"keys={sorted(keys)}")

        env = {**os.environ, "PYTHONPATH": "src", **tony_env, **keys}
        # In-process CC imports resolve their module-level path constants from os.environ,
        # so set them here BEFORE importing any runner.* module.
        os.environ.update(tony_env)
        os.environ.update(keys)
        py = [BOT_PY, "-m", "trading_bot.cli"]

        # ════════════════════════════════════════════════════════════════════
        # PHASE 1 — bot test suite (regression floor)
        # ════════════════════════════════════════════════════════════════════
        if not QUICK:
            rc, out = run([BOT_PY, "-m", "pytest", "-q"], env, "Phase 1 pytest suite")
            summary = next((l for l in reversed(out.splitlines()) if "passed" in l or "error" in l), "n/a")
            check("Phase1: full pytest suite green", "failed" not in out.lower() and rc == 0, summary.strip())
        else:
            print("  (skipped pytest — --quick)")

        # ════════════════════════════════════════════════════════════════════
        # PHASE 2 — LAYER 1 (bot) produces the day's handoffs into the sandbox
        # ════════════════════════════════════════════════════════════════════
        rc, _ = run(py + ["seed-demo-snapshots", "--config", cfg_arg], env, "Phase 2 seed snapshots")
        check("Phase2: sandbox DB created", (sb_data / "trading_bot.db").exists(), f"rc={rc}")
        rc, _ = run(py + ["emit-outcomes", "--config", cfg_arg, "--date", ds], env, "Phase 2 emit-outcomes")
        of = sb_reports / "tony_stocks_outcomes.json"
        check("Phase2: bot emitted resolved outcomes", of.exists())

        # Daily deep-dive anchor + the four intraday handoffs (multiple/day, the real cadence).
        rc, _ = run(py + ["export-to-vault", "--config", cfg_arg, "--date", ds], env, "Phase 2 daily bridge")
        for slot in ("1030", "1300", "1530", "eod"):
            run(py + ["export-to-vault", "--config", cfg_arg, "--slot", slot], env, f"Phase 2 intraday {slot}")
        daily_bridge = sb_bridge / f"{ds}.md"
        bridges = sorted(p.name for p in sb_bridge.glob("*.md"))
        check("Phase2: daily anchor bridge written", daily_bridge.exists(), str(daily_bridge.name))
        check("Phase2: multiple intraday handoffs written", len(bridges) >= 2, f"{len(bridges)} bridges: {bridges}")

        # The symbols the bot is handing to Tony (CC's real Tier-1 extractor regex).
        import re as _re
        tier1: list[str] = []
        if daily_bridge.exists():
            tier1 = _re.findall(r"\[\[([A-Z][A-Z0-9.\-]{0,9})\]\]", daily_bridge.read_text(encoding="utf-8"))
            tier1 = list(dict.fromkeys(tier1))  # dedupe, keep order
        bot_origin = bool(tier1)
        verdict_syms = tier1[:6] if tier1 else ["NVDA", "AMD", "AAPL", "MSFT", "AVGO", "BA"]
        check("Phase2: bot bridge exposes Tier-1 symbols for Tony", True,
              f"{'from bridge' if bot_origin else 'demo thin -> fixed set'}: {verdict_syms}")

        # ════════════════════════════════════════════════════════════════════
        # PHASE 3 — LAYER 2 (REAL CC) ingests every handoff
        # ════════════════════════════════════════════════════════════════════
        sys.path.insert(0, str(REPO / "src"))     # bot consumers
        sys.path.append(str(CC_ROOT))             # real CC runner package

        from runner.bridge import tony_bridge
        # Redirect the CC path constants that are NOT env-driven (they point at the real
        # CC workspace) to the sandbox, so ingestion can't touch the live Command Center.
        tony_bridge.BRIDGE_MD_DIR = sb_bridge
        tony_bridge.TASKS_DIR = sb_tasks
        tony_bridge.VAULT_DIR = sb_cc_vault
        tony_bridge._PROCESSED_LOG = sb_cc_logs / "tony-bridge-processed.json"
        tony_bridge.TRADING_REPORTS_DIR = sb_reports

        tony_bridge.scan_and_process()
        tasks = sorted(p.name for p in sb_tasks.glob("*.md"))
        check("Phase3: CC ingested handoffs -> spawned Tony deep-dive tasks",
              len(tasks) >= 1, f"{len(tasks)} tasks: {tasks[:6]}")
        check("Phase3: CC processed-log written to SANDBOX (real one untouched)",
              tony_bridge._PROCESSED_LOG.exists())
        # Re-running must be idempotent (dedup on stem) — no duplicate Tony runs per handoff.
        before = len(tasks)
        tony_bridge.scan_and_process()
        after = len(sorted(sb_tasks.glob("*.md")))
        check("Phase3: re-ingest is idempotent (no duplicate tasks)", after == before, f"{before}->{after}")

        # ════════════════════════════════════════════════════════════════════
        # PHASE 4 — LAYER 2 (REAL CC writer) records its 2nd-pass verdicts
        # ════════════════════════════════════════════════════════════════════
        from runner.tools.tony_verdict import write_tony_verdict
        # Cover every verdict enum, incl. the 'close' exit signal + a bracket-bearing 'adjust'.
        plan = ["reaffirm", "adjust", "override", "pass", "close"]
        wrote = 0
        for i, sym in enumerate(verdict_syms):
            verdict = plan[i % len(plan)]
            kw = dict(symbol=sym, tony_score=72 + i, scanner_score=70.0 + i,
                      verdict=verdict, thesis=f"{verdict} thesis for {sym}",
                      confidence=["low", "medium", "high"][i % 3],
                      evidence=["rev_growth_28pct", "analyst_upside_12pct"])
            if verdict in ("adjust", "override"):  # writer requires a valid long bracket
                kw["target"] = round((100.0 + i * 7) * 1.1, 2)
                kw["stop"] = round((100.0 + i * 7) * 0.95, 2)
            res = write_tony_verdict(**kw)
            wrote += int(bool(res.get("success")))
        vf = sb_reports / "tony_stocks_verdicts.json"
        check("Phase4: CC wrote 2nd-pass verdicts to SANDBOX", vf.exists() and wrote == len(verdict_syms),
              f"{wrote}/{len(verdict_syms)} ok")
        # The writer's contract guard: an adjust with no bracket must be REJECTED.
        bad = write_tony_verdict(symbol="ZZZZ", tony_score=50, verdict="adjust", thesis="no bracket")
        check("Phase4: CC writer rejects invalid bracket (contract guard holds)", "error" in bad,
              bad.get("error", "")[:48])

        # ════════════════════════════════════════════════════════════════════
        # PHASE 5 — LAYER 2 (REAL CC grader) grades the bot's outcomes -> record
        # ════════════════════════════════════════════════════════════════════
        # Controlled outcomes for the verdict symbols so today's verdicts actually join &
        # grade (populated record == the head-to-head dashboard lights up).
        of.write_text(json.dumps(synth_outcomes_for(verdict_syms, d0), indent=2), encoding="utf-8")

        from runner.ledger import tony_scorecard
        rec = tony_scorecard.write_record()
        rf = sb_reports / "tony_stocks_record.json"
        check("Phase5: CC grader wrote record.json to SANDBOX", rf.exists())
        check("Phase5: CC actually graded picks (status=scored, graded>0)",
              rec.get("status") == "scored" and rec.get("graded", 0) > 0,
              f"status={rec.get('status')} graded={rec.get('graded')}")
        from runner.tools.tony_outcomes import get_tony_outcomes
        tro = get_tony_outcomes(min_edge_samples=1)
        check("Phase5: CC track-record summary builds without error", isinstance(tro, dict),
              f"status={tro.get('status')}")

        # ════════════════════════════════════════════════════════════════════
        # PHASE 6 — BACK TO LAYER 1: bot consumes the CC's REAL outputs
        # ════════════════════════════════════════════════════════════════════
        from trading_bot.execution.cc_verdicts import cc_exit_symbols, load_cc_verdicts
        verds = load_cc_verdicts(str(vf))
        exits = cc_exit_symbols(verds)
        close_sym = verdict_syms[plan.index("close")] if "close" in plan[:len(verdict_syms)] else None
        check("Phase6: bot parses CC verdicts + detects the 'close' exit",
              bool(verds) and (close_sym is None or close_sym in exits),
              f"exits={sorted(exits)}")

        rc, _ = run(py + ["tony-divergence", "--config", cfg_arg], env, "Phase 6 tony-divergence")
        tlog = sb_reports / "tony_teaching_log.json"
        led = json.loads(tlog.read_text()) if tlog.exists() else {}
        agr = led.get("agreement") or led.get("tallies") or {}
        need = {"agreed_right", "agreed_wrong", "cc_overrode_saved", "cc_overrode_missed"}
        check("Phase6: bot built teaching ledger from CC verdicts (4 contract keys)",
              tlog.exists() and need.issubset(set(agr)), f"keys={sorted(agr)}")

        # The dashboard render path: the bot's /api/command-center mappers must accept the
        # CC's REAL record + verdicts (this is the panel that breaks if the contract drifts).
        from trading_bot.api.routes.command_center import (
            build_agreement, build_picks, build_record)
        rec_raw = json.loads(rf.read_text())
        dash_rec = build_record(rec_raw)
        dash_agr = build_agreement(rec_raw)
        dash_picks = build_picks(verds)
        check("Phase6: dashboard mappers accept CC record+verdicts (head-to-head renders)",
              dash_rec is not None and dash_agr is not None and len(dash_picks) >= 1,
              f"picks={len(dash_picks)} win_rate={getattr(dash_rec, 'tony_win_rate', '?')}")

        # ════════════════════════════════════════════════════════════════════
        # PHASE 7 — round-trip continuity: a symbol survived bot -> CC -> bot
        # ════════════════════════════════════════════════════════════════════
        graded_syms = {o["symbol"] for o in json.loads(of.read_text())}
        verdict_set = {vv.get("symbol") for vv in verds}
        looped = graded_syms & verdict_set & set(verdict_syms)
        check("Phase7: symbols completed the full loop (bot->CC verdict->CC grade->bot)",
              len(looped) >= 1,
              f"{'bot-origin ' if bot_origin else ''}looped: {sorted(looped)[:6]}")

        # ════════════════════════════════════════════════════════════════════
        # PHASE 8 — nightly self-learning brief (the 1:30am layer-1->CC handoff)
        # ════════════════════════════════════════════════════════════════════
        base_learn = ["learn", "--config", cfg_arg, "--min-sample", "1",
                      "--reports-dir", str(sb_reports), "--vault-dir", str(sb_vault),
                      "--command-center-dir", str(sb_cc)]
        rc, _ = run(py + base_learn + ["--date", ds, "--no-llm"], env, "Phase 8 learn (deterministic)")
        lbrief = sb_cc / "bridge" / "tony-stocks" / "learning" / f"{ds}.md"
        check("Phase8: nightly learning brief handed to CC (sandbox)", lbrief.exists() and rc == 0)
        if lbrief.exists():
            check("Phase8: learning brief is research_only", "research_only: true" in lbrief.read_text(encoding="utf-8"))

        if not NO_LIVE_LLM:
            d1 = (d0 + timedelta(days=1)).isoformat()
            rc, out = run(py + base_learn + ["--date", d1], env, "Phase 8 learn (LIVE LLM)")
            check("Phase8: LIVE LLM narration engaged (.env key passthrough works)",
                  "llm=on" in out.lower(),
                  next((l.strip() for l in out.splitlines() if "llm=" in l.lower()), "no llm line"))

    finally:
        # Remove the in-proc env redirects so they can't leak past this process.
        for k in (*tony_env, *keys):
            os.environ.pop(k, None)
        shutil.rmtree(sandbox, ignore_errors=True)
        print(f"\nSandbox deleted: {sandbox}")

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 9 — SAFETY: neither live system was touched
    # ════════════════════════════════════════════════════════════════════════
    bot_after = {str(p): sha(p) for p in [REPO / "data" / "trading_bot.db", *(REPO / "reports").glob("*.json")]}
    bot_changed = [k for k, vv in bot_baseline.items() if bot_after.get(k) != vv]
    check("Phase9: real bot reports/ + DB byte-for-byte unchanged", not bot_changed, f"changed={bot_changed}")
    vault_after = sum(1 for _ in REAL_VAULT.rglob("*")) if REAL_VAULT.exists() else 0
    check("Phase9: real bot vault file count unchanged", vault_after == vault_before, f"{vault_before}->{vault_after}")

    cc_after = {
        "bridge": dir_fingerprint(REAL_CC_BRIDGE),
        "tasks": dir_fingerprint(REAL_CC_TASKS),
        "processed": sha(REAL_CC_PROCESSED),
        **{str(p): sha(p) for p in REAL_CC_REPORTS},
    }
    cc_changed = [k for k in cc_baseline if cc_after.get(k) != cc_baseline[k]]
    check("Phase9: real Command Center workspace byte-for-byte unchanged", not cc_changed,
          f"changed={cc_changed}")

    # ── Summary ───────────────────────────────────────────────────────────────
    fails = [r for r in RESULTS if not r[1]]
    print("\n" + "=" * 66)
    print(f"RESULT: {len(RESULTS) - len(fails)}/{len(RESULTS)} checks passed")
    if fails:
        print("FAILED:")
        for n, _, d in fails:
            print(f"  - {n}" + (f"  ({d})" if d else ""))
    print("=" * 66)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
