"""Full, self-cleaning E2E + CC-sync test harness — runs ANYTIME (no market hours).

Exercises the WHOLE bot pipeline on synthetic-but-realistic data inside a throwaway
sandbox, then verifies the real systems were never touched. Covers BOTH directions of
the bot<->Command Center file contract:

  bot -> CC : seeded snapshots -> emit-outcomes -> export-to-vault (bridge) -> learn
              (nightly self-learning brief).
  CC -> bot : synthetic verdicts.json + record.json (locked schema) -> tony-divergence
              (teaching ledger) + cc exit-flatten detection + dashboard-shape checks.

Isolation (touches neither live system):
  * sandbox config overrides database_path + vault.vault_dir + vault.command_center_dir
    and flips allow_demo_* so synthetic data is RECOGNIZED (not dropped by real-only guards).
  * TONY_OUTCOMES_FILE / TONY_VERDICTS_FILE / TONY_RECORD_FILE / TONY_TEACHING_FILE / VAULT_DIR
    all point into the sandbox.
  * No broker calls (paper trading not invoked; live trading stays disabled).
  * Belt-and-suspenders: hashes the real sinks before/after and FAILS if any changed.

Run:  $env:PYTHONPATH="src"; python scripts/full_e2e_sync_test.py  [--quick] [--no-live-llm]
Exit code 0 = all green. Non-zero = at least one FAIL (details printed).
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
QUICK = "--quick" in sys.argv
NO_LIVE_LLM = "--no-live-llm" in sys.argv

# Real sinks that must NEVER change during the test.
REAL_SINKS = [
    REPO / "data" / "trading_bot.db",
    *(REPO / "reports").glob("*.json"),
]
REAL_CC_BRIDGE = Path(os.environ.get(
    "REAL_CC_BRIDGE_CHECK",
    "C:/Users/alexa/Downloads/AI Operations Command Center/bridge/tony-stocks"))
REAL_VAULT = REPO / "vault"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "MISSING"


def run(cmd: list[str], env: dict, label: str) -> tuple[int, str]:
    print(f"\n>>> {label}: {' '.join(cmd[2:])}")
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(REPO))
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(out.splitlines()[-8:])
    print(tail)
    return proc.returncode, out


# ── Synthetic fixtures (realistic prices so nothing is rejected as bogus) ──────

def synth_outcomes(d0: date) -> list[dict]:
    """~20 resolved episodes across sectors/dates/result-types + edge rows."""
    base = [
        ("NVDA", 138.0, 159.0, "target_hit", "Momentum / Buy"),
        ("AMD", 168.0, 154.0, "stop_hit", "Pullback / Buy"),
        ("AAPL", 228.0, 241.0, "target_hit", "Breakout / Buy"),
        ("MSFT", 462.0, 449.0, "stop_hit", "Pullback / Buy"),
        ("AVGO", 235.0, 268.0, "target_hit", "Momentum / Buy"),
        ("META", 705.0, 742.0, "closed", "Trend / Hold"),
        ("TSLA", 345.0, 312.0, "stop_hit", "Reversal / Buy"),
        ("AMZN", 222.0, 240.0, "target_hit", "Breakout / Buy"),
        ("JPM", 268.0, 259.0, "closed", "Pullback / Buy"),
        ("XOM", 112.0, 121.0, "target_hit", "Trend / Buy"),
        ("UNH", 305.0, 288.0, "stop_hit", "Reversal / Buy"),
        ("COIN", 295.0, 351.0, "target_hit", "Momentum / Buy"),
        ("MARA", 17.5, 14.9, "stop_hit", "Momentum / Buy"),
        ("PLTR", 78.0, 91.0, "target_hit", "Breakout / Buy"),
        ("CAT", 392.0, 405.0, "closed", "Trend / Hold"),
        ("LLY", 845.0, 902.0, "target_hit", "Trend / Buy"),
        ("BA", 178.0, 169.0, "stop_hit", "Reversal / Buy"),
        ("WMT", 96.0, 101.0, "target_hit", "Trend / Buy"),
        ("NEE", 71.0, 68.0, "closed", "Pullback / Buy"),
        ("FCX", 41.0, 45.0, "target_hit", "Momentum / Buy"),
    ]
    rows = []
    for i, (sym, entry, exit_, result, setup) in enumerate(base):
        pick = d0 - timedelta(days=20 - (i % 18))
        held = max(1, (i % 9) + 1)
        ret = round((exit_ - entry) / entry * 100, 2)
        rows.append({
            "symbol": sym,
            "pick_date": pick.isoformat(),
            "result": result,
            "outcome_label": result,
            "tracking_status": "resolved",
            "entry": entry,
            "exit": exit_,
            "return_pct": ret,
            "entry_date": pick.isoformat(),
            "days_held": held,
            "days_active": held,
            "resolved_date": (pick + timedelta(days=held)).isoformat(),
        })
    # Edge rows: NaN-ish return + a sparse record — robustness probes.
    rows.append({"symbol": "EDGE1", "pick_date": (d0 - timedelta(days=5)).isoformat(),
                 "result": "expired", "entry": 10.0, "exit": None, "return_pct": None,
                 "days_held": 3, "days_active": 3, "resolved_date": d0.isoformat()})
    rows.append({"symbol": "EDGE2", "pick_date": (d0 - timedelta(days=4)).isoformat(),
                 "result": "closed", "entry": 50.0})  # intentionally sparse
    return rows


def synth_verdicts(d0: date) -> list[dict]:
    """CC verdicts in the locked schema — covers every enum incl. close + a bracket edge."""
    return [
        {"symbol": "NVDA", "pick_date": (d0 - timedelta(days=20)).isoformat(),
         "verdict": "reaffirm", "thesis": "AI demand intact", "tony_reasoning": "AI demand intact"},
        {"symbol": "AMD", "pick_date": (d0 - timedelta(days=19)).isoformat(),
         "verdict": "adjust", "thesis": "tighten stop", "tony_reasoning": "tighten stop under 20DMA"},
        {"symbol": "TSLA", "pick_date": (d0 - timedelta(days=14)).isoformat(),
         "verdict": "override", "thesis": "skip; extended", "tony_reasoning": "too extended vs ATR"},
        {"symbol": "UNH", "pick_date": (d0 - timedelta(days=9)).isoformat(),
         "verdict": "pass", "thesis": "no edge", "tony_reasoning": "no catalyst"},
        # exit signal — must be detected by cc_exit_symbols (verdict scanned for tokens)
        {"symbol": "BA", "pick_date": (d0 - timedelta(days=11)).isoformat(),
         "verdict": "close", "thesis": "thesis broken", "tony_reasoning": "guidance cut"},
        # bracket-validity edge: target/stop invalid vs entry
        {"symbol": "COIN", "pick_date": (d0 - timedelta(days=7)).isoformat(),
         "verdict": "adjust", "thesis": "bracket edge", "tony_reasoning": "bracket edge",
         "entry": 295.0, "stop": 300.0, "target": 290.0},
    ]


def synth_record() -> dict:
    """CC record.json in the bot's reader contract (CommandCenterAgreement = 4 ints)."""
    curve = [round(100 + i * 0.3 - (i % 5), 2) for i in range(40)]
    return {
        "win_rate": 0.6,
        "avg_pl_per_trade": 1.85,
        "target_hits": 11,
        "stop_hits": 6,
        "equity_curve": curve,
        "agreement": {
            "agreed_right": 7, "agreed_wrong": 3,
            "cc_overrode_saved": 2, "cc_overrode_missed": 1,
        },
    }


def main() -> int:
    d0 = date.today()
    ds = d0.isoformat()
    print(f"== Full E2E + CC-sync test ({ds}) ==  quick={QUICK} live_llm={not NO_LIVE_LLM}")

    # ── Baseline: hash real sinks ─────────────────────────────────────────────
    baseline = {str(p): sha(p) for p in REAL_SINKS}
    real_bridge_before = sorted(p.name for p in REAL_CC_BRIDGE.glob("*")) if REAL_CC_BRIDGE.exists() else []
    real_vault_before = sum(1 for _ in REAL_VAULT.rglob("*")) if REAL_VAULT.exists() else 0

    sandbox = Path(tempfile.mkdtemp(prefix=f"e2e_sync_{d0:%Y%m%d}_"))
    print(f"Sandbox: {sandbox}")
    try:
        sb_reports = sandbox / "reports"; sb_reports.mkdir(parents=True)
        sb_vault = sandbox / "vault"; sb_vault.mkdir()
        sb_cc = sandbox / "CC"; sb_cc.mkdir()
        sb_data = sandbox / "data"; sb_data.mkdir()

        # ── Sandbox config (redirect all paths; recognize demo data) ──────────
        cfg = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        cfg["database_path"] = str(sb_data / "trading_bot.db")
        for k in ("allow_demo_snapshots", "allow_demo_in_learning",
                  "allow_demo_in_analytics", "allow_demo_fallback_in_watch"):
            cfg[k] = True
        cfg.setdefault("demo_snapshot_seed", {})["enabled"] = True  # let the seeder run in-sandbox
        v = cfg.setdefault("vault", {})
        v["enabled"] = True
        v["bridge_enabled"] = True
        v["vault_dir"] = str(sb_vault)
        v["command_center_dir"] = str(sb_cc)
        sb_config = sandbox / "config.yaml"
        sb_config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        cfg_arg = str(sb_config)

        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        env["TONY_OUTCOMES_FILE"] = str(sb_reports / "tony_stocks_outcomes.json")
        env["TONY_VERDICTS_FILE"] = str(sb_reports / "tony_stocks_verdicts.json")
        env["TONY_RECORD_FILE"] = str(sb_reports / "tony_stocks_record.json")
        env["TONY_TEACHING_FILE"] = str(sb_reports / "tony_teaching_log.json")
        env["VAULT_DIR"] = str(sb_vault)
        py = [sys.executable, "-m", "trading_bot.cli"]

        # ── Phase 1: full test suite ──────────────────────────────────────────
        if not QUICK:
            rc, out = run([sys.executable, "-m", "pytest", "-q"], env, "Phase 1 pytest suite")
            passed = ("failed" not in out.lower()) and rc == 0
            summary = next((l for l in reversed(out.splitlines()) if "passed" in l or "error" in l), "n/a")
            check("Phase1: full pytest suite green", passed, summary.strip())
        else:
            print("  (skipped pytest — --quick)")

        # ── Phase 2: seed snapshots + run the bot->CC producers ───────────────
        rc, _ = run(py + ["seed-demo-snapshots", "--config", cfg_arg], env, "Phase 2 seed-demo-snapshots")
        check("Phase2: seed-demo-snapshots ran", rc == 0, f"rc={rc}")
        check("Phase2: sandbox DB created", (sb_data / "trading_bot.db").exists())

        rc, _ = run(py + ["emit-outcomes", "--config", cfg_arg, "--date", ds], env, "Phase 3 emit-outcomes")
        of = sb_reports / "tony_stocks_outcomes.json"
        emit_rows = json.loads(of.read_text()) if of.exists() else []
        check("Phase3: emit-outcomes wrote to SANDBOX", of.exists(), f"{len(emit_rows)} rows")
        if emit_rows:
            r0 = emit_rows[0]
            check("Phase3: outcomes schema (symbol+pick_date, NO pick_id)",
                  "symbol" in r0 and "pick_date" in r0 and "pick_id" not in r0,
                  f"keys={sorted(r0)[:6]}…")

        rc, _ = run(py + ["export-to-vault", "--config", cfg_arg, "--date", ds], env, "Phase 4 export-to-vault")
        bridge = sb_cc / "bridge" / "tony-stocks" / f"{ds}.md"
        check("Phase4: EOD bridge is {date}.md (not T1600)", bridge.exists(), str(bridge.name))
        if bridge.exists():
            txt = bridge.read_text(encoding="utf-8")
            check("Phase4: bridge front-matter export_type=eod-bridge", "eod-bridge" in txt)
            check("Phase4: bridge strategy_version present", "strategy_version" in txt)

        # ── Phase 5: inject CC outputs (synthetic) + run CC->bot consumers ─────
        of.write_text(json.dumps(synth_outcomes(d0), indent=2), encoding="utf-8")
        (sb_reports / "tony_stocks_verdicts.json").write_text(
            json.dumps(synth_verdicts(d0), indent=2), encoding="utf-8")
        (sb_reports / "tony_stocks_record.json").write_text(
            json.dumps(synth_record(), indent=2), encoding="utf-8")

        rc, out = run(py + ["tony-divergence", "--config", cfg_arg], env, "Phase 5 tony-divergence")
        tlog = sb_reports / "tony_teaching_log.json"
        check("Phase5: teaching log written to SANDBOX (bot owns it)", tlog.exists())
        if tlog.exists():
            led = json.loads(tlog.read_text())
            agr = led.get("agreement") or led.get("tallies") or {}
            need = {"agreed_right", "agreed_wrong", "cc_overrode_saved", "cc_overrode_missed"}
            check("Phase5: teaching agreement has the 4 contract keys",
                  need.issubset(set(agr)), f"keys={sorted(agr)}")

        # CC->bot exit contract: verdict:'close' must be detected as an exit-flatten.
        sys.path.insert(0, str(REPO / "src"))
        from trading_bot.execution.cc_verdicts import cc_exit_symbols, load_cc_verdicts
        verds = load_cc_verdicts(str(sb_reports / "tony_stocks_verdicts.json"))
        exits = cc_exit_symbols(verds)
        check("Phase5: verdict 'close' detected as exit (BA)", "BA" in exits, f"exits={sorted(exits)}")

        # record.json shape the dashboard reader expects
        rec = json.loads((sb_reports / "tony_stocks_record.json").read_text())
        rec_ok = all(k in rec for k in ("win_rate", "avg_pl_per_trade", "target_hits", "stop_hits", "equity_curve"))
        ag_ok = isinstance(rec.get("agreement"), dict) and all(
            isinstance(rec["agreement"].get(k), int)
            for k in ("agreed_right", "agreed_wrong", "cc_overrode_saved", "cc_overrode_missed"))
        check("Phase5: record.json matches bot reader contract", rec_ok and ag_ok)

        # ── Phase 6: nightly learning (deterministic) + bridge brief ──────────
        learn = py + ["learn", "--config", cfg_arg, "--date", ds, "--min-sample", "1",
                      "--reports-dir", str(sb_reports), "--vault-dir", str(sb_vault),
                      "--command-center-dir", str(sb_cc), "--no-llm"]
        rc, out = run(learn, env, "Phase 6 learn (deterministic)")
        check("Phase6: learn ran", rc == 0, f"rc={rc}")
        lbrief = sb_cc / "bridge" / "tony-stocks" / "learning" / f"{ds}.md"
        check("Phase6: CC learning brief written to SANDBOX", lbrief.exists())
        if lbrief.exists():
            lt = lbrief.read_text(encoding="utf-8")
            check("Phase6: learning brief is research_only", "research_only: true" in lt)
        kf = sb_reports / "learning_knowledge.json"
        check("Phase6: learning knowledge json produced", kf.exists())

        # ── Phase 7: optional LIVE Gemini narration pass (pennies) ────────────
        if not NO_LIVE_LLM:
            d1 = (d0 + timedelta(days=1)).isoformat()
            live = py + ["learn", "--config", cfg_arg, "--date", d1, "--min-sample", "1",
                         "--reports-dir", str(sb_reports), "--vault-dir", str(sb_vault),
                         "--command-center-dir", str(sb_cc)]
            rc, out = run(live, env, "Phase 7 learn (LIVE Gemini)")
            check("Phase7: live LLM narration llm=on", "llm=on" in out.lower(),
                  next((l.strip() for l in out.splitlines() if "llm=" in l.lower()), "no llm line"))

    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
        print(f"\nSandbox deleted: {sandbox}")

    # ── Phase 8: SAFETY — real systems untouched ──────────────────────────────
    after = {str(p): sha(p) for p in [REPO / "data" / "trading_bot.db", *(REPO / "reports").glob("*.json")]}
    changed = [k for k, v in baseline.items() if after.get(k) != v]
    check("Phase8: real reports/ + DB byte-for-byte unchanged", not changed, f"changed={changed}")
    real_bridge_after = sorted(p.name for p in REAL_CC_BRIDGE.glob("*")) if REAL_CC_BRIDGE.exists() else []
    check("Phase8: real CC bridge dir unchanged", real_bridge_after == real_bridge_before,
          f"+{set(real_bridge_after) - set(real_bridge_before)}")
    real_vault_after = sum(1 for _ in REAL_VAULT.rglob("*")) if REAL_VAULT.exists() else 0
    check("Phase8: real vault file count unchanged", real_vault_after == real_vault_before,
          f"{real_vault_before}->{real_vault_after}")

    # ── Summary ───────────────────────────────────────────────────────────────
    fails = [r for r in RESULTS if not r[1]]
    print("\n" + "=" * 64)
    print(f"RESULT: {len(RESULTS) - len(fails)}/{len(RESULTS)} checks passed")
    if fails:
        print("FAILED:")
        for n, _, d in fails:
            print(f"  - {n} {('('+d+')') if d else ''}")
    print("=" * 64)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
