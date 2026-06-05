"""Stage 3: grow the swing/day-trade research universe (~744 -> ~1000).

Third staged batch on top of expand_universe.py / expand_universe_2.py. Deeper liquid
mid/small-caps (regional banks, biotech, REITs, semis, transports, energy E&P,
specialty industrials/materials, China ADRs, quantum/AI specs) for the rotating
discovery pool — primary_candidate / speculative_candidate only (no watchlist_core).

Idempotent + every symbol QUOTED (YAML-1.1 boolean tickers stay strings).
Research/scanning only — NOT recommendations. Metadata (sector/style) approximate.
Run: python scripts/expand_universe_3.py
"""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path("config/universe_swing_research_config.yaml")

KIND = {
    "core":  ("primary_candidate", "steady_mega_cap_trend", ["large_cap"]),
    "swing": ("primary_candidate", "base_building", ["mid_cap"]),
    "spec":  ("speculative_candidate", "high_volatility_whipsaw", ["high_beta", "speculative"]),
}

NEW: list[tuple[str, str, str, str]] = [
    # ── Software / internet (deeper) ─────────────────────────────────────────
    ("PEGA", "Pegasystems", "technology", "swing"),
    ("MANH", "Manhattan Associates", "technology", "swing"),
    ("DSGX", "Descartes Systems", "technology", "swing"),
    ("ALTR", "Altair Engineering", "technology", "swing"),
    ("BL", "BlackLine", "technology", "swing"),
    ("ALRM", "Alarm.com", "technology", "swing"),
    ("NTNX", "Nutanix", "technology", "swing"),
    ("PSTG", "Pure Storage", "technology", "swing"),
    ("QTWO", "Q2 Holdings", "technology", "spec"),
    ("SPSC", "SPS Commerce", "technology", "swing"),
    ("INTA", "Intapp", "technology", "spec"),
    ("AMPL", "Amplitude", "technology", "spec"),
    ("DV", "DoubleVerify", "technology", "spec"),
    ("PUBM", "PubMatic", "technology", "spec"),
    ("RNG", "RingCentral", "technology", "spec"),
    ("PRO", "PROS Holdings", "technology", "spec"),
    ("YOU", "Clear Secure", "technology", "swing"),
    ("AVPT", "AvePoint", "technology", "spec"),
    ("GDYN", "Grid Dynamics", "technology", "spec"),
    ("DAVA", "Endava", "technology", "spec"),
    ("CXM", "Sprinklr", "technology", "spec"),
    ("SMCI", "Super Micro Computer", "technology", "spec"),
    ("INFA", "Informatica", "technology", "swing"),
    ("WK", "Workiva", "technology", "swing"),
    ("FRSH", "Freshworks", "technology", "spec"),
    ("SUMO", "Sumo Logic", "technology", "spec"),
    ("AMBA", "Ambarella", "technology", "spec"),
    # ── Quantum / AI / speculative tech ──────────────────────────────────────
    ("IONQ", "IonQ", "technology", "spec"),
    ("RGTI", "Rigetti Computing", "technology", "spec"),
    ("QBTS", "D-Wave Quantum", "technology", "spec"),
    ("QUBT", "Quantum Computing", "technology", "spec"),
    ("LAES", "SEALSQ", "technology", "spec"),
    ("BBAI", "BigBear.ai", "technology", "spec"),
    ("SOUN", "SoundHound AI", "technology", "spec"),
    ("AUR", "Aurora Innovation", "technology", "spec"),
    ("KSCP", "Knightscope", "technology", "spec"),
    # ── Semis / hardware (deeper) ────────────────────────────────────────────
    ("SITM", "SiTime", "technology", "spec"),
    ("MTSI", "MACOM Technology", "technology", "swing"),
    ("SYNA", "Synaptics", "technology", "swing"),
    ("MXL", "MaxLinear", "technology", "spec"),
    ("CRUS", "Cirrus Logic", "technology", "swing"),
    ("AOSL", "Alpha and Omega Semiconductor", "technology", "spec"),
    ("HIMX", "Himax Technologies", "technology", "spec"),
    ("NVTS", "Navitas Semiconductor", "technology", "spec"),
    ("SGH", "SMART Global Holdings", "technology", "spec"),
    ("PLXS", "Plexus", "technology", "swing"),
    ("BHE", "Benchmark Electronics", "technology", "spec"),
    ("FN", "Fabrinet", "technology", "swing"),
    # ── Regional banks ───────────────────────────────────────────────────────
    ("ZION", "Zions Bancorporation", "financials", "swing"),
    ("CMA", "Comerica", "financials", "swing"),
    ("WAL", "Western Alliance Bancorporation", "financials", "swing"),
    ("EWBC", "East West Bancorp", "financials", "swing"),
    ("PB", "Prosperity Bancshares", "financials", "swing"),
    ("CFR", "Cullen/Frost Bankers", "financials", "swing"),
    ("SNV", "Synovus Financial", "financials", "swing"),
    ("WBS", "Webster Financial", "financials", "swing"),
    ("CADE", "Cadence Bank", "financials", "swing"),
    ("FNB", "F.N.B. Corporation", "financials", "swing"),
    ("ONB", "Old National Bancorp", "financials", "swing"),
    ("COLB", "Columbia Banking System", "financials", "swing"),
    ("BOKF", "BOK Financial", "financials", "swing"),
    ("PNFP", "Pinnacle Financial Partners", "financials", "swing"),
    ("UMBF", "UMB Financial", "financials", "swing"),
    ("WTFC", "Wintrust Financial", "financials", "swing"),
    ("FHN", "First Horizon", "financials", "swing"),
    ("VLY", "Valley National Bancorp", "financials", "spec"),
    ("OZK", "Bank OZK", "financials", "swing"),
    ("SSB", "SouthState", "financials", "swing"),
    ("HWC", "Hancock Whitney", "financials", "swing"),
    ("FFIN", "First Financial Bankshares", "financials", "swing"),
    ("TCBI", "Texas Capital Bancshares", "financials", "spec"),
    ("GBCI", "Glacier Bancorp", "financials", "swing"),
    # ── Asset management / insurance ─────────────────────────────────────────
    ("AMG", "Affiliated Managers Group", "financials", "swing"),
    ("JHG", "Janus Henderson", "financials", "swing"),
    ("SEIC", "SEI Investments", "financials", "swing"),
    ("VOYA", "Voya Financial", "financials", "swing"),
    ("PFG", "Principal Financial Group", "financials", "swing"),
    ("GL", "Globe Life", "financials", "swing"),
    ("AIZ", "Assurant", "financials", "swing"),
    ("RGA", "Reinsurance Group of America", "financials", "swing"),
    ("RNR", "RenaissanceRe", "financials", "swing"),
    ("AFG", "American Financial Group", "financials", "swing"),
    ("MKL", "Markel Group", "financials", "core"),
    ("WRB", "W. R. Berkley", "financials", "swing"),
    ("KNSL", "Kinsale Capital Group", "financials", "swing"),
    ("RLI", "RLI", "financials", "swing"),
    ("SIGI", "Selective Insurance", "financials", "swing"),
    ("AXS", "AXIS Capital Holdings", "financials", "swing"),
    ("ORI", "Old Republic International", "financials", "swing"),
    # ── Fintech / payments (deeper) ──────────────────────────────────────────
    ("XYZ", "Block", "financials", "swing"),
    ("FIS", "Fidelity National Information", "financials", "swing"),
    ("JKHY", "Jack Henry & Associates", "financials", "swing"),
    ("WEX", "WEX", "financials", "swing"),
    ("EEFT", "Euronet Worldwide", "financials", "swing"),
    ("PAYO", "Payoneer Global", "financials", "spec"),
    ("DLO", "DLocal", "financials", "spec"),
    ("STNE", "StoneCo", "financials", "spec"),
    ("NU", "Nu Holdings", "financials", "swing"),
    # ── Healthcare services / devices (deeper) ───────────────────────────────
    ("CNC", "Centene", "healthcare", "swing"),
    ("THC", "Tenet Healthcare", "healthcare", "swing"),
    ("UHS", "Universal Health Services", "healthcare", "swing"),
    ("DVA", "DaVita", "healthcare", "swing"),
    ("CHE", "Chemed", "healthcare", "swing"),
    ("EHC", "Encompass Health", "healthcare", "swing"),
    ("ENSG", "Ensign Group", "healthcare", "swing"),
    ("HQY", "HealthEquity", "healthcare", "swing"),
    ("DOCS", "Doximity", "healthcare", "spec"),
    ("HIMS", "Hims & Hers Health", "healthcare", "spec"),
    ("OSCR", "Oscar Health", "healthcare", "spec"),
    ("ALHC", "Alignment Healthcare", "healthcare", "spec"),
    ("PRVA", "Privia Health", "healthcare", "spec"),
    ("MEDP", "Medpace Holdings", "healthcare", "swing"),
    ("CRL", "Charles River Laboratories", "healthcare", "swing"),
    ("RVTY", "Revvity", "healthcare", "swing"),
    ("TECH", "Bio-Techne", "healthcare", "swing"),
    ("QGEN", "Qiagen", "healthcare", "swing"),
    ("BRKR", "Bruker", "healthcare", "swing"),
    ("NVCR", "NovoCure", "healthcare", "spec"),
    ("INSP", "Inspire Medical Systems", "healthcare", "swing"),
    ("LNTH", "Lantheus Holdings", "healthcare", "swing"),
    ("ICUI", "ICU Medical", "healthcare", "swing"),
    ("ATEC", "Alphatec Holdings", "healthcare", "spec"),
    ("PACB", "Pacific Biosciences", "healthcare", "spec"),
    ("TWST", "Twist Bioscience", "healthcare", "spec"),
    ("CDNA", "CareDx", "healthcare", "spec"),
    # ── Biotech (deeper specs) ───────────────────────────────────────────────
    ("SMMT", "Summit Therapeutics", "healthcare", "spec"),
    ("VERA", "Vera Therapeutics", "healthcare", "spec"),
    ("RXRX", "Recursion Pharmaceuticals", "healthcare", "spec"),
    ("DNLI", "Denali Therapeutics", "healthcare", "spec"),
    ("ARVN", "Arvinas", "healthcare", "spec"),
    ("BPMC", "Blueprint Medicines", "healthcare", "swing"),
    ("RYTM", "Rhythm Pharmaceuticals", "healthcare", "spec"),
    ("AKRO", "Akero Therapeutics", "healthcare", "spec"),
    ("IMVT", "Immunovant", "healthcare", "spec"),
    ("PTCT", "PTC Therapeutics", "healthcare", "spec"),
    ("ACLX", "Arcellx", "healthcare", "spec"),
    ("KYMR", "Kymera Therapeutics", "healthcare", "spec"),
    ("RCKT", "Rocket Pharmaceuticals", "healthcare", "spec"),
    ("RNA", "Avidity Biosciences", "healthcare", "spec"),
    ("NUVL", "Nuvalent", "healthcare", "spec"),
    ("MRUS", "Merus", "healthcare", "spec"),
    # ── Aerospace / defense / industrials (deeper) ───────────────────────────
    ("GNRC", "Generac Holdings", "industrials", "swing"),
    ("AYI", "Acuity", "industrials", "swing"),
    ("ALLE", "Allegion", "industrials", "swing"),
    ("MAS", "Masco", "industrials", "swing"),
    ("LII", "Lennox International", "industrials", "core"),
    ("WSO", "Watsco", "industrials", "swing"),
    ("SSD", "Simpson Manufacturing", "industrials", "swing"),
    ("WTS", "Watts Water Technologies", "industrials", "swing"),
    ("CR", "Crane", "industrials", "swing"),
    ("FLS", "Flowserve", "industrials", "swing"),
    ("DCI", "Donaldson", "industrials", "swing"),
    ("MIDD", "Middleby", "industrials", "swing"),
    ("OSK", "Oshkosh", "industrials", "swing"),
    ("TXT", "Textron", "industrials", "swing"),
    ("CW", "Curtiss-Wright", "industrials", "swing"),
    ("HEI", "Heico", "industrials", "core"),
    ("HII", "Huntington Ingalls Industries", "industrials", "swing"),
    ("AVAV", "AeroVironment", "industrials", "spec"),
    ("BWXT", "BWX Technologies", "industrials", "swing"),
    ("DRS", "Leonardo DRS", "industrials", "swing"),
    ("CACI", "CACI International", "industrials", "swing"),
    ("SAIC", "Science Applications International", "industrials", "swing"),
    ("LDOS", "Leidos Holdings", "industrials", "core"),
    ("BAH", "Booz Allen Hamilton", "industrials", "swing"),
    ("AGCO", "AGCO", "industrials", "swing"),
    ("TTC", "Toro", "industrials", "swing"),
    ("LECO", "Lincoln Electric", "industrials", "swing"),
    ("MTZ", "MasTec", "industrials", "swing"),
    ("STRL", "Sterling Infrastructure", "industrials", "spec"),
    ("PRIM", "Primoris Services", "industrials", "spec"),
    ("DY", "Dycom Industries", "industrials", "spec"),
    ("ACA", "Arcosa", "industrials", "swing"),
    ("EXP", "Eagle Materials", "industrials", "swing"),
    # ── Transports (deeper) ──────────────────────────────────────────────────
    ("KNX", "Knight-Swift Transportation", "industrials", "swing"),
    ("WERN", "Werner Enterprises", "industrials", "spec"),
    ("SNDR", "Schneider National", "industrials", "swing"),
    ("HUBG", "Hub Group", "industrials", "swing"),
    ("MATX", "Matson", "industrials", "swing"),
    ("ALK", "Alaska Air Group", "industrials", "swing"),
    ("ZIM", "ZIM Integrated Shipping", "industrials", "spec"),
    # ── Consumer discretionary (deeper) ──────────────────────────────────────
    ("GME", "GameStop", "consumer", "spec"),
    ("BBY", "Best Buy", "consumer", "swing"),
    ("TSCO", "Tractor Supply", "consumer", "core"),
    ("WSM", "Williams-Sonoma", "consumer", "swing"),
    ("FIVE", "Five Below", "consumer", "swing"),
    ("BJ", "BJ's Wholesale Club", "consumer", "swing"),
    ("OLLI", "Ollie's Bargain Outlet", "consumer", "swing"),
    ("ASO", "Academy Sports and Outdoors", "consumer", "swing"),
    ("SFM", "Sprouts Farmers Market", "consumer", "swing"),
    ("PFGC", "Performance Food Group", "consumer", "swing"),
    ("USFD", "US Foods Holding", "consumer", "swing"),
    ("CART", "Maplebear (Instacart)", "consumer", "spec"),
    ("CAKE", "Cheesecake Factory", "consumer", "swing"),
    ("EAT", "Brinker International", "consumer", "swing"),
    ("SHAK", "Shake Shack", "consumer", "spec"),
    ("PLAY", "Dave & Buster's Entertainment", "consumer", "spec"),
    ("WEN", "Wendy's", "consumer", "swing"),
    ("CPRI", "Capri Holdings", "consumer", "spec"),
    ("PVH", "PVH", "consumer", "swing"),
    ("LEVI", "Levi Strauss", "consumer", "swing"),
    ("COLM", "Columbia Sportswear", "consumer", "swing"),
    ("KTB", "Kontoor Brands", "consumer", "swing"),
    ("BOOT", "Boot Barn Holdings", "consumer", "swing"),
    ("AEO", "American Eagle Outfitters", "consumer", "spec"),
    ("FIGS", "FIGS", "consumer", "spec"),
    # ── EV / solar / clean energy ────────────────────────────────────────────
    ("QS", "QuantumScape", "consumer", "spec"),
    ("CHPT", "ChargePoint Holdings", "technology", "spec"),
    ("EVGO", "EVgo", "technology", "spec"),
    ("SEDG", "SolarEdge Technologies", "technology", "spec"),
    ("NXT", "Nextracker", "technology", "swing"),
    ("ARRY", "Array Technologies", "technology", "spec"),
    ("SHLS", "Shoals Technologies", "technology", "spec"),
    ("FLNC", "Fluence Energy", "technology", "spec"),
    ("STEM", "Stem", "technology", "spec"),
    # ── Energy (deeper E&P / oilfield / midstream) ───────────────────────────
    ("MUR", "Murphy Oil", "energy", "spec"),
    ("CIVI", "Civitas Resources", "energy", "spec"),
    ("CHRD", "Chord Energy", "energy", "spec"),
    ("MGY", "Magnolia Oil & Gas", "energy", "spec"),
    ("CRGY", "Crescent Energy", "energy", "spec"),
    ("RIG", "Transocean", "energy", "spec"),
    ("VAL", "Valaris", "energy", "spec"),
    ("WFRD", "Weatherford International", "energy", "spec"),
    ("PTEN", "Patterson-UTI Energy", "energy", "spec"),
    ("CHX", "ChampionX", "energy", "swing"),
    ("FTI", "TechnipFMC", "energy", "swing"),
    ("ET", "Energy Transfer", "energy", "swing"),
    ("EPD", "Enterprise Products Partners", "energy", "core"),
    ("MPLX", "MPLX", "energy", "swing"),
    ("WES", "Western Midstream Partners", "energy", "swing"),
    ("DTM", "DT Midstream", "energy", "swing"),
    ("DINO", "HF Sinclair", "energy", "swing"),
    # ── Materials (deeper chemicals / metals) ────────────────────────────────
    ("RPM", "RPM International", "materials", "swing"),
    ("AXTA", "Axalta Coating Systems", "materials", "swing"),
    ("OLN", "Olin", "materials", "spec"),
    ("CC", "Chemours", "materials", "spec"),
    ("HUN", "Huntsman", "materials", "spec"),
    ("WLK", "Westlake", "materials", "swing"),
    ("CBT", "Cabot", "materials", "swing"),
    ("AVY", "Avery Dennison", "materials", "swing"),
    ("SEE", "Sealed Air", "materials", "swing"),
    ("GPK", "Graphic Packaging Holding", "materials", "swing"),
    ("SON", "Sonoco Products", "materials", "swing"),
    ("ATR", "AptarGroup", "materials", "swing"),
    ("MTRN", "Materion", "materials", "spec"),
    # ── Gold / precious metals miners ────────────────────────────────────────
    ("AEM", "Agnico Eagle Mines", "materials", "swing"),
    ("KGC", "Kinross Gold", "materials", "spec"),
    ("WPM", "Wheaton Precious Metals", "materials", "swing"),
    ("FNV", "Franco-Nevada", "materials", "swing"),
    ("RGLD", "Royal Gold", "materials", "swing"),
    ("HL", "Hecla Mining", "materials", "spec"),
    ("CDE", "Coeur Mining", "materials", "spec"),
    ("AG", "First Majestic Silver", "materials", "spec"),
    ("PAAS", "Pan American Silver", "materials", "spec"),
    ("BTG", "B2Gold", "materials", "spec"),
    ("EGO", "Eldorado Gold", "materials", "spec"),
    # ── Communication / media (deeper) ───────────────────────────────────────
    ("NXST", "Nexstar Media Group", "communication", "swing"),
    ("WMG", "Warner Music Group", "communication", "swing"),
    ("FUBO", "FuboTV", "communication", "spec"),
    ("BILI", "Bilibili", "communication", "spec"),
    ("CRTO", "Criteo", "communication", "spec"),
    ("TRIP", "Tripadvisor", "communication", "spec"),
    ("ZD", "Ziff Davis", "communication", "swing"),
    ("CCOI", "Cogent Communications", "communication", "spec"),
    ("IRDM", "Iridium Communications", "communication", "swing"),
    ("LUMN", "Lumen Technologies", "communication", "spec"),
    # ── REITs (deeper) ───────────────────────────────────────────────────────
    ("SUI", "Sun Communities", "real_estate", "swing"),
    ("AMH", "American Homes 4 Rent", "real_estate", "swing"),
    ("MAA", "Mid-America Apartment", "real_estate", "swing"),
    ("UDR", "UDR", "real_estate", "swing"),
    ("CPT", "Camden Property Trust", "real_estate", "swing"),
    ("ESS", "Essex Property Trust", "real_estate", "swing"),
    ("ELS", "Equity LifeStyle Properties", "real_estate", "swing"),
    ("REG", "Regency Centers", "real_estate", "swing"),
    ("KIM", "Kimco Realty", "real_estate", "swing"),
    ("FRT", "Federal Realty Investment Trust", "real_estate", "swing"),
    ("BXP", "BXP", "real_estate", "swing"),
    ("ARE", "Alexandria Real Estate Equities", "real_estate", "swing"),
    ("VTR", "Ventas", "real_estate", "swing"),
    ("DOC", "Healthpeak Properties", "real_estate", "swing"),
    ("OHI", "Omega Healthcare Investors", "real_estate", "swing"),
    ("COLD", "Americold Realty Trust", "real_estate", "spec"),
    ("REXR", "Rexford Industrial Realty", "real_estate", "swing"),
    ("STAG", "STAG Industrial", "real_estate", "swing"),
    ("CUBE", "CubeSmart", "real_estate", "swing"),
    ("GLPI", "Gaming and Leisure Properties", "real_estate", "swing"),
    ("HST", "Host Hotels & Resorts", "real_estate", "swing"),
    ("ADC", "Agree Realty", "real_estate", "swing"),
    ("NNN", "NNN REIT", "real_estate", "swing"),
    ("STWD", "Starwood Property Trust", "real_estate", "swing"),
    ("NLY", "Annaly Capital Management", "real_estate", "spec"),
    ("AGNC", "AGNC Investment", "real_estate", "spec"),
    # ── China / international ADRs (liquid, high beta) ────────────────────────
    ("NIO", "NIO", "consumer", "spec"),
    ("LI", "Li Auto", "consumer", "spec"),
    ("XPEV", "XPeng", "consumer", "spec"),
    ("BEKE", "KE Holdings", "real_estate", "spec"),
    ("TCOM", "Trip.com Group", "consumer", "spec"),
    ("NTES", "NetEase", "communication", "swing"),
    ("TME", "Tencent Music Entertainment", "communication", "spec"),
    ("YUMC", "Yum China Holdings", "consumer", "swing"),
    ("FUTU", "Futu Holdings", "financials", "spec"),
    ("BZ", "Kanzhun", "communication", "spec"),
    ("GDS", "GDS Holdings", "technology", "spec"),
    ("VIPS", "Vipshop Holdings", "consumer", "spec"),
    ("ZTO", "ZTO Express", "industrials", "swing"),
]


def build_block(sym: str, name: str, sector: str, kind: str) -> str:
    role, profile, base_tags = KIND[kind]
    tags = base_tags + [sector]
    tag_str = "[" + ", ".join(tags) + "]"
    return (
        f'  - symbol: "{sym}"\n'
        f"    name: {name}\n"
        f"    tags: {tag_str}\n"
        f"    sector: {sector}\n"
        f"    universe_role: {role}\n"
        f"    demo_profile: {profile}\n"
    )


def main() -> None:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert "symbols" in data, f"no symbols key; top-level={list(data.keys())}"
    existing = {str(x["symbol"]) for x in data["symbols"]}
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
        "  # ── Staged expansion 3 (2026-06-04): deeper liquid mid/small-caps —\n"
        "  #    regional banks, biotech, REITs, semis, transports, energy E&P,\n"
        "  #    miners, ADRs. primary/speculative only. Symbols quoted. Research only.\n"
    )
    new_lines = lines[:insert_at] + [header] + blocks + ["\n"] + lines[insert_at:]
    CONFIG.write_text("".join(new_lines), encoding="utf-8")

    reloaded = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    syms = [x["symbol"] for x in reloaded["symbols"]]
    non_str = [s for s in syms if not isinstance(s, str)]
    assert not non_str, f"non-string symbols introduced: {non_str}"
    dupes = {s for s in syms if syms.count(s) > 1}
    assert not dupes, f"duplicate symbols introduced: {dupes}"

    print(f"Added {len(added)} symbols: {before} -> {len(syms)}")
    print("New:", ", ".join(added))


if __name__ == "__main__":
    main()
