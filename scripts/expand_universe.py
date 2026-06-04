"""One-off: stage-grow the swing/day-trade research universe (~349 -> ~500).

Appends curated, high-liquidity US names to config/universe_swing_research_config.yaml
as primary_candidate / speculative_candidate rows (no watchlist_core tag, so they
feed the rotating *discovery* pool rather than the forced-core set). Idempotent:
re-running skips any symbol already present, so it never creates duplicates.

Research/scanning only — NOT recommendations. Metadata (sector/style) is approximate.
Run: python scripts/expand_universe.py
"""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path("config/universe_swing_research_config.yaml")

# kind -> (universe_role, demo_profile, base_tags). demo_profile values are drawn
# from the set already valid in the file; kind only affects demo-mode synthesis.
KIND = {
    "core":  ("primary_candidate", "steady_mega_cap_trend", ["large_cap"]),
    "swing": ("primary_candidate", "base_building", ["mid_cap"]),
    "spec":  ("speculative_candidate", "high_volatility_whipsaw", ["high_beta", "speculative"]),
}

# (symbol, name, sector, kind). Curated for liquidity + sector breadth. Any symbol
# already in the file is skipped automatically, so harmless overlaps are fine.
NEW: list[tuple[str, str, str, str]] = [
    # ── Technology / semis / hardware ────────────────────────────────────────
    ("NXPI", "NXP Semiconductors", "technology", "core"),
    ("MCHP", "Microchip Technology", "technology", "swing"),
    ("MPWR", "Monolithic Power Systems", "technology", "core"),
    ("SWKS", "Skyworks Solutions", "technology", "swing"),
    ("QRVO", "Qorvo", "technology", "swing"),
    ("TER", "Teradyne", "technology", "swing"),
    ("ENTG", "Entegris", "technology", "swing"),
    ("GFS", "GlobalFoundries", "technology", "swing"),
    ("GLW", "Corning", "technology", "core"),
    ("KEYS", "Keysight Technologies", "technology", "core"),
    ("TDY", "Teledyne Technologies", "technology", "core"),
    ("ZBRA", "Zebra Technologies", "technology", "swing"),
    ("TRMB", "Trimble", "technology", "swing"),
    ("NTAP", "NetApp", "technology", "swing"),
    ("WDC", "Western Digital", "technology", "spec"),
    ("STX", "Seagate Technology", "technology", "swing"),
    ("HPQ", "HP Inc", "technology", "core"),
    ("HPE", "Hewlett Packard Enterprise", "technology", "swing"),
    ("DELL", "Dell Technologies", "technology", "swing"),
    ("JNPR", "Juniper Networks", "technology", "swing"),
    ("FFIV", "F5", "technology", "swing"),
    ("JBL", "Jabil", "technology", "swing"),
    ("CRDO", "Credo Technology", "technology", "spec"),
    ("ALAB", "Astera Labs", "technology", "spec"),
    ("COHR", "Coherent", "technology", "spec"),
    ("AMKR", "Amkor Technology", "technology", "swing"),
    ("FORM", "FormFactor", "technology", "spec"),
    # ── Software / internet ──────────────────────────────────────────────────
    ("WDAY", "Workday", "technology", "swing"),
    ("TEAM", "Atlassian", "technology", "swing"),
    ("ADSK", "Autodesk", "technology", "core"),
    ("ANSS", "Ansys", "technology", "core"),
    ("PTC", "PTC", "technology", "swing"),
    ("FICO", "Fair Isaac", "technology", "core"),
    ("TYL", "Tyler Technologies", "technology", "core"),
    ("PAYC", "Paycom Software", "technology", "swing"),
    ("DT", "Dynatrace", "technology", "swing"),
    ("GWRE", "Guidewire Software", "technology", "swing"),
    ("MNDY", "monday.com", "technology", "spec"),
    ("ZM", "Zoom Communications", "technology", "swing"),
    ("TWLO", "Twilio", "technology", "spec"),
    ("DOCU", "Docusign", "technology", "swing"),
    ("NCNO", "nCino", "technology", "spec"),
    ("SPOT", "Spotify", "communication", "swing"),
    # ── Financials ───────────────────────────────────────────────────────────
    ("MET", "MetLife", "financials", "core"),
    ("PRU", "Prudential Financial", "financials", "core"),
    ("ALL", "Allstate", "financials", "core"),
    ("TRV", "Travelers", "financials", "core"),
    ("AIG", "American International Group", "financials", "swing"),
    ("AON", "Aon", "financials", "core"),
    ("MMC", "Marsh & McLennan", "financials", "core"),
    ("FI", "Fiserv", "financials", "core"),
    ("GPN", "Global Payments", "financials", "swing"),
    ("SYF", "Synchrony Financial", "financials", "swing"),
    ("DFS", "Discover Financial", "financials", "swing"),
    ("AMP", "Ameriprise Financial", "financials", "core"),
    ("TROW", "T. Rowe Price", "financials", "swing"),
    ("STT", "State Street", "financials", "swing"),
    ("NTRS", "Northern Trust", "financials", "swing"),
    ("FITB", "Fifth Third Bancorp", "financials", "swing"),
    ("HBAN", "Huntington Bancshares", "financials", "swing"),
    ("RF", "Regions Financial", "financials", "swing"),
    ("KEY", "KeyCorp", "financials", "spec"),
    ("CFG", "Citizens Financial", "financials", "swing"),
    ("MTB", "M&T Bank", "financials", "swing"),
    ("FOUR", "Shift4 Payments", "financials", "spec"),
    ("FLYW", "Flywire", "financials", "spec"),
    # ── Healthcare / biotech ─────────────────────────────────────────────────
    ("UNH", "UnitedHealth Group", "healthcare", "core"),
    ("PFE", "Pfizer", "healthcare", "core"),
    ("MRK", "Merck", "healthcare", "core"),
    ("CNC", "Centene", "healthcare", "swing"),
    ("HCA", "HCA Healthcare", "healthcare", "core"),
    ("RMD", "ResMed", "healthcare", "core"),
    ("IDXX", "IDEXX Laboratories", "healthcare", "core"),
    ("IQV", "IQVIA", "healthcare", "swing"),
    ("A", "Agilent Technologies", "healthcare", "core"),
    ("WAT", "Waters", "healthcare", "swing"),
    ("MTD", "Mettler-Toledo", "healthcare", "core"),
    ("BIIB", "Biogen", "healthcare", "swing"),
    ("HOLX", "Hologic", "healthcare", "swing"),
    ("ALGN", "Align Technology", "healthcare", "spec"),
    ("ZTS", "Zoetis", "healthcare", "core"),
    ("NBIX", "Neurocrine Biosciences", "healthcare", "swing"),
    ("EXAS", "Exact Sciences", "healthcare", "spec"),
    ("NTRA", "Natera", "healthcare", "spec"),
    ("HALO", "Halozyme Therapeutics", "healthcare", "swing"),
    ("VKTX", "Viking Therapeutics", "healthcare", "spec"),
    ("CYTK", "Cytokinetics", "healthcare", "spec"),
    ("ARWR", "Arrowhead Pharmaceuticals", "healthcare", "spec"),
    ("SRPT", "Sarepta Therapeutics", "healthcare", "spec"),
    ("BMRN", "BioMarin Pharmaceutical", "healthcare", "swing"),
    ("ALNY", "Alnylam Pharmaceuticals", "healthcare", "swing"),
    ("INSM", "Insmed", "healthcare", "spec"),
    ("MDGL", "Madrigal Pharmaceuticals", "healthcare", "spec"),
    # ── Industrials ──────────────────────────────────────────────────────────
    ("BA", "Boeing", "industrials", "swing"),
    ("GD", "General Dynamics", "industrials", "core"),
    ("LHX", "L3Harris Technologies", "industrials", "core"),
    ("HWM", "Howmet Aerospace", "industrials", "core"),
    ("TDG", "TransDigm Group", "industrials", "core"),
    ("MMM", "3M", "industrials", "core"),
    ("CARR", "Carrier Global", "industrials", "swing"),
    ("OTIS", "Otis Worldwide", "industrials", "core"),
    ("AME", "Ametek", "industrials", "core"),
    ("DOV", "Dover", "industrials", "swing"),
    ("ROP", "Roper Technologies", "industrials", "core"),
    ("FTV", "Fortive", "industrials", "swing"),
    ("XYL", "Xylem", "industrials", "swing"),
    ("WAB", "Westinghouse Air Brake", "industrials", "core"),
    ("ODFL", "Old Dominion Freight Line", "industrials", "swing"),
    ("JBHT", "J.B. Hunt Transport", "industrials", "swing"),
    ("RSG", "Republic Services", "industrials", "core"),
    ("GWW", "W.W. Grainger", "industrials", "core"),
    ("CTAS", "Cintas", "industrials", "core"),
    ("PWR", "Quanta Services", "industrials", "swing"),
    ("VRSK", "Verisk Analytics", "industrials", "core"),
    ("AAL", "American Airlines", "industrials", "spec"),
    ("LUV", "Southwest Airlines", "industrials", "swing"),
    # ── Consumer staples ─────────────────────────────────────────────────────
    ("KO", "Coca-Cola", "consumer", "core"),
    ("PEP", "PepsiCo", "consumer", "core"),
    ("PG", "Procter & Gamble", "consumer", "core"),
    ("COST", "Costco Wholesale", "consumer", "core"),
    ("MDLZ", "Mondelez International", "consumer", "core"),
    ("MO", "Altria Group", "consumer", "core"),
    ("PM", "Philip Morris International", "consumer", "core"),
    ("CL", "Colgate-Palmolive", "consumer", "core"),
    ("KMB", "Kimberly-Clark", "consumer", "core"),
    ("GIS", "General Mills", "consumer", "swing"),
    ("HSY", "Hershey", "consumer", "swing"),
    ("STZ", "Constellation Brands", "consumer", "swing"),
    ("KDP", "Keurig Dr Pepper", "consumer", "core"),
    ("KHC", "Kraft Heinz", "consumer", "swing"),
    ("MNST", "Monster Beverage", "consumer", "swing"),
    # ── Consumer discretionary ───────────────────────────────────────────────
    ("HD", "Home Depot", "consumer", "core"),
    ("F", "Ford Motor", "consumer", "spec"),
    ("GM", "General Motors", "consumer", "swing"),
    ("ULTA", "Ulta Beauty", "consumer", "swing"),
    ("KMX", "CarMax", "consumer", "swing"),
    ("DPZ", "Domino's Pizza", "consumer", "swing"),
    ("DRI", "Darden Restaurants", "consumer", "core"),
    ("WING", "Wingstop", "consumer", "spec"),
    ("TXRH", "Texas Roadhouse", "consumer", "swing"),
    ("DECK", "Deckers Outdoor", "consumer", "swing"),
    ("RL", "Ralph Lauren", "consumer", "swing"),
    ("TPR", "Tapestry", "consumer", "swing"),
    ("BURL", "Burlington Stores", "consumer", "swing"),
    ("DKS", "Dick's Sporting Goods", "consumer", "swing"),
    ("RH", "RH", "consumer", "spec"),
    ("LVS", "Las Vegas Sands", "consumer", "swing"),
    ("WYNN", "Wynn Resorts", "consumer", "spec"),
    ("MGM", "MGM Resorts", "consumer", "swing"),
    ("CZR", "Caesars Entertainment", "consumer", "spec"),
    ("DHI", "D.R. Horton", "consumer", "swing"),
    ("LEN", "Lennar", "consumer", "swing"),
    ("PHM", "PulteGroup", "consumer", "swing"),
    ("BLDR", "Builders FirstSource", "consumer", "spec"),
    # ── Energy ───────────────────────────────────────────────────────────────
    ("FANG", "Diamondback Energy", "energy", "swing"),
    ("CTRA", "Coterra Energy", "energy", "swing"),
    ("APA", "APA Corporation", "energy", "spec"),
    ("OVV", "Ovintiv", "energy", "spec"),
    ("PR", "Permian Resources", "energy", "spec"),
    ("MTDR", "Matador Resources", "energy", "spec"),
    ("RRC", "Range Resources", "energy", "spec"),
    ("NOV", "NOV Inc", "energy", "swing"),
    ("HP", "Helmerich & Payne", "energy", "spec"),
    ("LBRT", "Liberty Energy", "energy", "spec"),
    # ── Materials ────────────────────────────────────────────────────────────
    ("SCCO", "Southern Copper", "materials", "swing"),
    ("AA", "Alcoa", "materials", "spec"),
    ("CLF", "Cleveland-Cliffs", "materials", "spec"),
    ("X", "United States Steel", "materials", "spec"),
    ("RS", "Reliance", "materials", "swing"),
    ("VMC", "Vulcan Materials", "materials", "core"),
    ("MLM", "Martin Marietta Materials", "materials", "core"),
    ("SHW", "Sherwin-Williams", "materials", "core"),
    ("PPG", "PPG Industries", "materials", "swing"),
    ("ECL", "Ecolab", "materials", "core"),
    ("LIN", "Linde", "materials", "core"),
    ("APD", "Air Products and Chemicals", "materials", "core"),
    ("DOW", "Dow Inc", "materials", "swing"),
    ("DD", "DuPont de Nemours", "materials", "swing"),
    ("LYB", "LyondellBasell", "materials", "swing"),
    # ── Communication / media ────────────────────────────────────────────────
    ("LYV", "Live Nation Entertainment", "communication", "swing"),
    ("MTCH", "Match Group", "communication", "spec"),
    ("OMC", "Omnicom Group", "communication", "swing"),
    ("TTGT", "TechTarget", "communication", "spec"),
    # ── Utilities ────────────────────────────────────────────────────────────
    ("SRE", "Sempra", "utilities", "core"),
    ("AEE", "Ameren", "utilities", "core"),
    ("ED", "Consolidated Edison", "utilities", "core"),
    ("PEG", "Public Service Enterprise", "utilities", "core"),
    ("WEC", "WEC Energy Group", "utilities", "core"),
    ("EIX", "Edison International", "utilities", "swing"),
    ("ETR", "Entergy", "utilities", "core"),
    ("PPL", "PPL Corporation", "utilities", "swing"),
    # ── China ADRs (liquid; higher headline risk) ────────────────────────────
    ("BABA", "Alibaba Group", "consumer", "spec"),
    ("PDD", "PDD Holdings", "consumer", "spec"),
    ("JD", "JD.com", "consumer", "spec"),
    ("BIDU", "Baidu", "communication", "spec"),
    # ── Crypto-adjacent miners (high beta) ───────────────────────────────────
    ("WULF", "TeraWulf", "technology", "spec"),
    ("CIFR", "Cipher Mining", "technology", "spec"),
    ("HUT", "Hut 8", "technology", "spec"),
    ("BTBT", "Bit Digital", "technology", "spec"),
]


def build_block(sym: str, name: str, sector: str, kind: str) -> str:
    role, profile, base_tags = KIND[kind]
    tags = base_tags + [sector]
    tag_str = "[" + ", ".join(tags) + "]"
    return (
        f"  - symbol: {sym}\n"
        f"    name: {name}\n"
        f"    tags: {tag_str}\n"
        f"    sector: {sector}\n"
        f"    universe_role: {role}\n"
        f"    demo_profile: {profile}\n"
    )


def main() -> None:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert "symbols" in data, f"no symbols key; top-level={list(data.keys())}"
    existing = {x["symbol"] for x in data["symbols"]}
    before = len(existing)

    blocks: list[str] = []
    added: list[str] = []
    seen: set[str] = set()
    for sym, name, sector, kind in NEW:
        if sym in existing or sym in seen:
            continue
        seen.add(sym)
        added.append(sym)
        blocks.append(build_block(sym, name, sector, kind))

    if not blocks:
        print("Nothing to add — all candidates already present.")
        return

    # The file has top-level keys after `symbols` (csv_path, filters). Insert the
    # new rows at the END of the symbols list — i.e. right before the first
    # top-level key that follows it (a line at column 0 that isn't `symbols:`).
    lines = CONFIG.read_text(encoding="utf-8").splitlines(keepends=True)
    seen_symbols = False
    insert_at = len(lines)
    for i, ln in enumerate(lines):
        if ln.startswith("symbols:"):
            seen_symbols = True
            continue
        if seen_symbols and ln[:1] not in (" ", "\t", "#", "\n", "\r") and ln.strip():
            insert_at = i
            break
    header = (
        "  # ── Staged expansion (2026-06-03/04): liquidity + sector breadth for the\n"
        "  #    rotating discovery pool. primary_candidate / speculative_candidate only\n"
        "  #    (no watchlist_core). Research/scanning only — not recommendations.\n"
    )
    new_lines = lines[:insert_at] + [header] + blocks + ["\n"] + lines[insert_at:]
    CONFIG.write_text("".join(new_lines), encoding="utf-8")

    # Validate: reload + assert no duplicates and YAML integrity.
    reloaded = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    syms = [x["symbol"] for x in reloaded["symbols"]]
    dupes = {s for s in syms if syms.count(s) > 1}
    assert not dupes, f"duplicate symbols introduced: {dupes}"
    for x in reloaded["symbols"][-len(added):]:
        assert set(x.keys()) >= {"symbol", "name", "tags", "sector", "universe_role", "demo_profile"}

    print(f"Added {len(added)} symbols: {before} -> {len(syms)}")
    print("New:", ", ".join(added))


if __name__ == "__main__":
    main()
