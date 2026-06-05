"""Stage 2: grow the swing/day-trade research universe (~548 -> ~1000).

Second staged batch on top of `expand_universe.py`. Appends curated, high-liquidity
US names (S&P 500 remainder + liquid S&P MidCap 400 names + popular high-volume
tickers) as primary_candidate / speculative_candidate rows — no watchlist_core tag,
so they feed the rotating *discovery* pool, not the forced-core set.

Idempotent: re-running skips any symbol already present, so it never creates
duplicates and is safe to run repeatedly. Every emitted `symbol` is QUOTED so that
YAML-1.1 boolean tickers (ON, NO, OFF, YES, Y, N, TRUE, FALSE) stay strings.

Research/scanning only — NOT recommendations. Metadata (sector/style) is approximate.
Run: python scripts/expand_universe_2.py
"""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path("config/universe_swing_research_config.yaml")

# kind -> (universe_role, demo_profile, base_tags). Mirrors expand_universe.py.
KIND = {
    "core":  ("primary_candidate", "steady_mega_cap_trend", ["large_cap"]),
    "swing": ("primary_candidate", "base_building", ["mid_cap"]),
    "spec":  ("speculative_candidate", "high_volatility_whipsaw", ["high_beta", "speculative"]),
}

# (symbol, name, sector, kind). Curated for liquidity + sector breadth. Any symbol
# already in the file is skipped automatically, so harmless overlaps are fine.
NEW: list[tuple[str, str, str, str]] = [
    # ── Technology: software / internet ──────────────────────────────────────
    ("INTU", "Intuit", "technology", "core"),
    ("ADP", "Automatic Data Processing", "technology", "core"),
    ("PAYX", "Paychex", "technology", "core"),
    ("CTSH", "Cognizant Technology", "technology", "swing"),
    ("IT", "Gartner", "technology", "core"),
    ("AKAM", "Akamai Technologies", "technology", "swing"),
    ("EPAM", "EPAM Systems", "technology", "swing"),
    ("CDW", "CDW Corporation", "technology", "swing"),
    ("SNPS", "Synopsys", "technology", "core"),
    ("CDNS", "Cadence Design Systems", "technology", "core"),
    ("PCTY", "Paylocity", "technology", "spec"),
    ("PCOR", "Procore Technologies", "technology", "spec"),
    ("BSY", "Bentley Systems", "technology", "swing"),
    ("APPN", "Appian", "technology", "spec"),
    ("FROG", "JFrog", "technology", "spec"),
    ("ESTC", "Elastic", "technology", "spec"),
    ("CFLT", "Confluent", "technology", "spec"),
    ("S", "SentinelOne", "technology", "spec"),
    ("TENB", "Tenable", "technology", "spec"),
    ("RPD", "Rapid7", "technology", "spec"),
    ("QLYS", "Qualys", "technology", "swing"),
    ("VRNS", "Varonis Systems", "technology", "spec"),
    ("ZS", "Zscaler", "technology", "swing"),
    ("OKTA", "Okta", "technology", "swing"),
    ("HUBS", "HubSpot", "technology", "swing"),
    ("TTAN", "ServiceTitan", "technology", "spec"),
    ("KVYO", "Klaviyo", "technology", "spec"),
    ("BRZE", "Braze", "technology", "spec"),
    ("ASAN", "Asana", "technology", "spec"),
    ("BOX", "Box", "technology", "swing"),
    ("DBX", "Dropbox", "technology", "swing"),
    ("PD", "PagerDuty", "technology", "spec"),
    ("FSLY", "Fastly", "technology", "spec"),
    ("NET", "Cloudflare", "technology", "swing"),
    ("DOCN", "DigitalOcean", "technology", "spec"),
    ("GTLB", "GitLab", "technology", "spec"),
    ("AI", "C3.ai", "technology", "spec"),
    ("PLTR", "Palantir Technologies", "technology", "swing"),
    ("U", "Unity Software", "technology", "spec"),
    ("RBLX", "Roblox", "technology", "swing"),
    ("DUOL", "Duolingo", "technology", "swing"),
    ("APP", "AppLovin", "technology", "spec"),
    ("BMBL", "Bumble", "communication", "spec"),
    ("YELP", "Yelp", "communication", "swing"),
    ("PINS", "Pinterest", "communication", "swing"),
    ("SNAP", "Snap", "communication", "spec"),
    ("RDDT", "Reddit", "communication", "spec"),
    ("ZG", "Zillow Group", "communication", "swing"),
    ("CARG", "CarGurus", "communication", "swing"),
    ("CVNA", "Carvana", "consumer", "spec"),
    # ── Technology: semis / hardware ─────────────────────────────────────────
    ("ADI", "Analog Devices", "technology", "core"),
    ("ON", "ON Semiconductor", "technology", "swing"),  # quoted on emit
    ("LSCC", "Lattice Semiconductor", "technology", "spec"),
    ("RMBS", "Rambus", "technology", "swing"),
    ("SMTC", "Semtech", "technology", "spec"),
    ("POWI", "Power Integrations", "technology", "swing"),
    ("SLAB", "Silicon Laboratories", "technology", "swing"),
    ("DIOD", "Diodes Incorporated", "technology", "spec"),
    ("OLED", "Universal Display", "technology", "swing"),
    ("ACLS", "Axcelis Technologies", "technology", "spec"),
    ("UCTT", "Ultra Clean Holdings", "technology", "spec"),
    ("ICHR", "Ichor Holdings", "technology", "spec"),
    ("KLIC", "Kulicke and Soffa", "technology", "spec"),
    ("PI", "Impinj", "technology", "spec"),
    ("NVMI", "Nova", "technology", "spec"),
    ("CAMT", "Camtek", "technology", "spec"),
    ("AEIS", "Advanced Energy Industries", "technology", "swing"),
    ("VSH", "Vishay Intertechnology", "technology", "swing"),
    ("SANM", "Sanmina", "technology", "swing"),
    ("FLEX", "Flex", "technology", "swing"),
    ("CIEN", "Ciena", "technology", "swing"),
    ("LITE", "Lumentum Holdings", "technology", "spec"),
    ("VIAV", "Viavi Solutions", "technology", "spec"),
    ("EXTR", "Extreme Networks", "technology", "spec"),
    ("AAOI", "Applied Optoelectronics", "technology", "spec"),
    ("INFN", "Infinera", "technology", "spec"),
    ("DGII", "Digi International", "technology", "spec"),
    ("WOLF", "Wolfspeed", "technology", "spec"),
    ("INDI", "indie Semiconductor", "technology", "spec"),
    # ── Financials ───────────────────────────────────────────────────────────
    ("V", "Visa", "financials", "core"),
    ("MA", "Mastercard", "financials", "core"),
    ("AXP", "American Express", "financials", "core"),
    ("PYPL", "PayPal Holdings", "financials", "swing"),
    ("SCHW", "Charles Schwab", "financials", "core"),
    ("BLK", "BlackRock", "financials", "core"),
    ("BX", "Blackstone", "financials", "core"),
    ("KKR", "KKR & Co", "financials", "swing"),
    ("APO", "Apollo Global Management", "financials", "swing"),
    ("ARES", "Ares Management", "financials", "swing"),
    ("CG", "Carlyle Group", "financials", "swing"),
    ("OWL", "Blue Owl Capital", "financials", "swing"),
    ("MSCI", "MSCI", "financials", "core"),
    ("SPGI", "S&P Global", "financials", "core"),
    ("MCO", "Moody's", "financials", "core"),
    ("ICE", "Intercontinental Exchange", "financials", "core"),
    ("CME", "CME Group", "financials", "core"),
    ("NDAQ", "Nasdaq", "financials", "swing"),
    ("CBOE", "Cboe Global Markets", "financials", "swing"),
    ("COF", "Capital One Financial", "financials", "swing"),
    ("USB", "U.S. Bancorp", "financials", "swing"),
    ("PNC", "PNC Financial Services", "financials", "swing"),
    ("TFC", "Truist Financial", "financials", "swing"),
    ("BK", "Bank of New York Mellon", "financials", "swing"),
    ("WFC", "Wells Fargo", "financials", "core"),
    ("MS", "Morgan Stanley", "financials", "core"),
    ("JPM", "JPMorgan Chase", "financials", "core"),
    ("WTW", "Willis Towers Watson", "financials", "swing"),
    ("BRO", "Brown & Brown", "financials", "core"),
    ("ACGL", "Arch Capital Group", "financials", "swing"),
    ("CB", "Chubb", "financials", "core"),
    ("PGR", "Progressive", "financials", "core"),
    ("HIG", "Hartford Financial", "financials", "swing"),
    ("CINF", "Cincinnati Financial", "financials", "swing"),
    ("L", "Loews", "financials", "swing"),
    ("EG", "Everest Group", "financials", "swing"),
    ("RJF", "Raymond James Financial", "financials", "swing"),
    ("BEN", "Franklin Resources", "financials", "swing"),
    ("IVZ", "Invesco", "financials", "spec"),
    ("HOOD", "Robinhood Markets", "financials", "spec"),
    ("COIN", "Coinbase Global", "financials", "spec"),
    ("SOFI", "SoFi Technologies", "financials", "spec"),
    ("AFRM", "Affirm Holdings", "financials", "spec"),
    ("UPST", "Upstart Holdings", "financials", "spec"),
    ("LMND", "Lemonade", "financials", "spec"),
    ("TOST", "Toast", "financials", "spec"),
    ("BILL", "BILL Holdings", "financials", "spec"),
    # ── Healthcare / biotech ─────────────────────────────────────────────────
    ("JNJ", "Johnson & Johnson", "healthcare", "core"),
    ("ABBV", "AbbVie", "healthcare", "core"),
    ("LLY", "Eli Lilly", "healthcare", "core"),
    ("TMO", "Thermo Fisher Scientific", "healthcare", "core"),
    ("ABT", "Abbott Laboratories", "healthcare", "core"),
    ("DHR", "Danaher", "healthcare", "core"),
    ("BSX", "Boston Scientific", "healthcare", "core"),
    ("MDT", "Medtronic", "healthcare", "core"),
    ("SYK", "Stryker", "healthcare", "core"),
    ("BDX", "Becton Dickinson", "healthcare", "core"),
    ("EW", "Edwards Lifesciences", "healthcare", "swing"),
    ("CI", "Cigna Group", "healthcare", "core"),
    ("ELV", "Elevance Health", "healthcare", "core"),
    ("HUM", "Humana", "healthcare", "swing"),
    ("MOH", "Molina Healthcare", "healthcare", "swing"),
    ("MCK", "McKesson", "healthcare", "core"),
    ("COR", "Cencora", "healthcare", "core"),
    ("CAH", "Cardinal Health", "healthcare", "swing"),
    ("GEHC", "GE HealthCare", "healthcare", "swing"),
    ("STE", "STERIS", "healthcare", "core"),
    ("DGX", "Quest Diagnostics", "healthcare", "swing"),
    ("LH", "Labcorp", "healthcare", "swing"),
    ("BAX", "Baxter International", "healthcare", "swing"),
    ("TFX", "Teleflex", "healthcare", "swing"),
    ("PEN", "Penumbra", "healthcare", "spec"),
    ("MASI", "Masimo", "healthcare", "swing"),
    ("GKOS", "Glaukos", "healthcare", "spec"),
    ("TNDM", "Tandem Diabetes Care", "healthcare", "spec"),
    ("SHC", "Sotera Health", "healthcare", "spec"),
    ("AMGN", "Amgen", "healthcare", "core"),
    ("GILD", "Gilead Sciences", "healthcare", "core"),
    ("REGN", "Regeneron Pharmaceuticals", "healthcare", "core"),
    ("VRTX", "Vertex Pharmaceuticals", "healthcare", "core"),
    ("MRNA", "Moderna", "healthcare", "spec"),
    ("BNTX", "BioNTech", "healthcare", "spec"),
    ("RPRX", "Royalty Pharma", "healthcare", "swing"),
    ("CORT", "Corcept Therapeutics", "healthcare", "spec"),
    ("UTHR", "United Therapeutics", "healthcare", "swing"),
    ("EXEL", "Exelixis", "healthcare", "swing"),
    ("JAZZ", "Jazz Pharmaceuticals", "healthcare", "swing"),
    ("RVMD", "Revolution Medicines", "healthcare", "spec"),
    ("KRYS", "Krystal Biotech", "healthcare", "spec"),
    ("RARE", "Ultragenyx Pharmaceutical", "healthcare", "spec"),
    ("IONS", "Ionis Pharmaceuticals", "healthcare", "spec"),
    ("ITCI", "Intra-Cellular Therapies", "healthcare", "spec"),
    ("AXSM", "Axsome Therapeutics", "healthcare", "spec"),
    ("CRNX", "Crinetics Pharmaceuticals", "healthcare", "spec"),
    ("TGTX", "TG Therapeutics", "healthcare", "spec"),
    ("DVAX", "Dynavax Technologies", "healthcare", "spec"),
    # ── Industrials ──────────────────────────────────────────────────────────
    ("HON", "Honeywell International", "industrials", "core"),
    ("CAT", "Caterpillar", "industrials", "core"),
    ("DE", "Deere & Co", "industrials", "core"),
    ("UNP", "Union Pacific", "industrials", "core"),
    ("UPS", "United Parcel Service", "industrials", "core"),
    ("FDX", "FedEx", "industrials", "swing"),
    ("ETN", "Eaton", "industrials", "core"),
    ("EMR", "Emerson Electric", "industrials", "core"),
    ("ITW", "Illinois Tool Works", "industrials", "core"),
    ("PH", "Parker-Hannifin", "industrials", "core"),
    ("CMI", "Cummins", "industrials", "swing"),
    ("PCAR", "PACCAR", "industrials", "swing"),
    ("NSC", "Norfolk Southern", "industrials", "swing"),
    ("CSX", "CSX", "industrials", "swing"),
    ("LMT", "Lockheed Martin", "industrials", "core"),
    ("NOC", "Northrop Grumman", "industrials", "core"),
    ("RTX", "RTX Corporation", "industrials", "core"),
    ("AXON", "Axon Enterprise", "industrials", "swing"),
    ("GEV", "GE Vernova", "industrials", "swing"),
    ("PNR", "Pentair", "industrials", "swing"),
    ("AOS", "A.O. Smith", "industrials", "swing"),
    ("IEX", "IDEX", "industrials", "swing"),
    ("NDSN", "Nordson", "industrials", "swing"),
    ("GGG", "Graco", "industrials", "swing"),
    ("ITT", "ITT", "industrials", "swing"),
    ("CSL", "Carlisle Companies", "industrials", "swing"),
    ("URI", "United Rentals", "industrials", "swing"),
    ("FAST", "Fastenal", "industrials", "core"),
    ("WM", "Waste Management", "industrials", "core"),
    ("EME", "EMCOR Group", "industrials", "swing"),
    ("ACM", "AECOM", "industrials", "swing"),
    ("J", "Jacobs Solutions", "industrials", "swing"),
    ("FIX", "Comfort Systems USA", "industrials", "spec"),
    ("HUBB", "Hubbell", "industrials", "swing"),
    ("ROK", "Rockwell Automation", "industrials", "swing"),
    ("DAL", "Delta Air Lines", "industrials", "swing"),
    ("UAL", "United Airlines", "industrials", "spec"),
    ("CHRW", "C.H. Robinson Worldwide", "industrials", "swing"),
    ("EXPD", "Expeditors International", "industrials", "swing"),
    ("XPO", "XPO", "industrials", "spec"),
    ("SAIA", "Saia", "industrials", "spec"),
    ("GXO", "GXO Logistics", "industrials", "spec"),
    ("R", "Ryder System", "industrials", "swing"),
    # ── Consumer discretionary ───────────────────────────────────────────────
    ("MCD", "McDonald's", "consumer", "core"),
    ("SBUX", "Starbucks", "consumer", "core"),
    ("NKE", "Nike", "consumer", "core"),
    ("LOW", "Lowe's", "consumer", "core"),
    ("TJX", "TJX Companies", "consumer", "core"),
    ("BKNG", "Booking Holdings", "consumer", "core"),
    ("MAR", "Marriott International", "consumer", "core"),
    ("HLT", "Hilton Worldwide", "consumer", "core"),
    ("CMG", "Chipotle Mexican Grill", "consumer", "swing"),
    ("ORLY", "O'Reilly Automotive", "consumer", "core"),
    ("AZO", "AutoZone", "consumer", "core"),
    ("ROST", "Ross Stores", "consumer", "swing"),
    ("YUM", "Yum! Brands", "consumer", "core"),
    ("QSR", "Restaurant Brands International", "consumer", "swing"),
    ("EXPE", "Expedia Group", "consumer", "swing"),
    ("ABNB", "Airbnb", "consumer", "swing"),
    ("RCL", "Royal Caribbean Cruises", "consumer", "swing"),
    ("CCL", "Carnival", "consumer", "spec"),
    ("NCLH", "Norwegian Cruise Line", "consumer", "spec"),
    ("LULU", "Lululemon Athletica", "consumer", "swing"),
    ("ELF", "e.l.f. Beauty", "consumer", "spec"),
    ("CROX", "Crocs", "consumer", "spec"),
    ("ONON", "On Holding", "consumer", "spec"),
    ("BIRK", "Birkenstock Holding", "consumer", "swing"),
    ("SKX", "Skechers U.S.A.", "consumer", "swing"),
    ("VFC", "VF Corporation", "consumer", "spec"),
    ("GPS", "Gap", "consumer", "spec"),
    ("ANF", "Abercrombie & Fitch", "consumer", "spec"),
    ("URBN", "Urban Outfitters", "consumer", "swing"),
    ("FL", "Foot Locker", "consumer", "spec"),
    ("W", "Wayfair", "consumer", "spec"),
    ("CHWY", "Chewy", "consumer", "swing"),
    ("ETSY", "Etsy", "consumer", "spec"),
    ("EBAY", "eBay", "consumer", "swing"),
    ("POOL", "Pool Corporation", "consumer", "swing"),
    ("GRMN", "Garmin", "consumer", "swing"),
    ("WHR", "Whirlpool", "consumer", "spec"),
    ("LKQ", "LKQ", "consumer", "swing"),
    ("APTV", "Aptiv", "consumer", "swing"),
    ("LEA", "Lear", "consumer", "swing"),
    ("BWA", "BorgWarner", "consumer", "swing"),
    ("RIVN", "Rivian Automotive", "consumer", "spec"),
    ("LCID", "Lucid Group", "consumer", "spec"),
    ("HOG", "Harley-Davidson", "consumer", "spec"),
    ("TPX", "Tempur Sealy", "consumer", "swing"),
    ("MHK", "Mohawk Industries", "consumer", "swing"),
    ("TOL", "Toll Brothers", "consumer", "swing"),
    ("NVR", "NVR", "consumer", "core"),
    # ── Consumer staples ─────────────────────────────────────────────────────
    ("WMT", "Walmart", "consumer", "core"),
    ("TGT", "Target", "consumer", "swing"),
    ("DG", "Dollar General", "consumer", "swing"),
    ("DLTR", "Dollar Tree", "consumer", "swing"),
    ("KR", "Kroger", "consumer", "swing"),
    ("SYY", "Sysco", "consumer", "core"),
    ("ADM", "Archer-Daniels-Midland", "consumer", "swing"),
    ("BG", "Bunge Global", "consumer", "swing"),
    ("TSN", "Tyson Foods", "consumer", "swing"),
    ("HRL", "Hormel Foods", "consumer", "swing"),
    ("K", "Kellanova", "consumer", "swing"),
    ("CAG", "Conagra Brands", "consumer", "swing"),
    ("CPB", "Campbell's", "consumer", "swing"),
    ("SJM", "J.M. Smucker", "consumer", "swing"),
    ("MKC", "McCormick & Company", "consumer", "core"),
    ("CLX", "Clorox", "consumer", "swing"),
    ("CHD", "Church & Dwight", "consumer", "core"),
    ("EL", "Estee Lauder", "consumer", "swing"),
    ("TAP", "Molson Coors Beverage", "consumer", "swing"),
    ("CASY", "Casey's General Stores", "consumer", "swing"),
    ("DKNG", "DraftKings", "consumer", "spec"),
    ("FND", "Floor & Decor Holdings", "consumer", "swing"),
    # ── Energy ───────────────────────────────────────────────────────────────
    ("XOM", "Exxon Mobil", "energy", "core"),
    ("CVX", "Chevron", "energy", "core"),
    ("COP", "ConocoPhillips", "energy", "core"),
    ("EOG", "EOG Resources", "energy", "swing"),
    ("SLB", "Schlumberger", "energy", "swing"),
    ("PSX", "Phillips 66", "energy", "swing"),
    ("MPC", "Marathon Petroleum", "energy", "swing"),
    ("VLO", "Valero Energy", "energy", "swing"),
    ("WMB", "Williams Companies", "energy", "core"),
    ("OKE", "ONEOK", "energy", "swing"),
    ("KMI", "Kinder Morgan", "energy", "swing"),
    ("LNG", "Cheniere Energy", "energy", "swing"),
    ("TRGP", "Targa Resources", "energy", "swing"),
    ("HES", "Hess", "energy", "swing"),
    ("BKR", "Baker Hughes", "energy", "swing"),
    ("HAL", "Halliburton", "energy", "swing"),
    ("DVN", "Devon Energy", "energy", "spec"),
    ("EQT", "EQT", "energy", "spec"),
    ("AR", "Antero Resources", "energy", "spec"),
    ("CHK", "Expand Energy", "energy", "spec"),
    ("SM", "SM Energy", "energy", "spec"),
    ("CNX", "CNX Resources", "energy", "spec"),
    ("TPL", "Texas Pacific Land", "energy", "swing"),
    # ── Materials ────────────────────────────────────────────────────────────
    ("NUE", "Nucor", "materials", "swing"),
    ("STLD", "Steel Dynamics", "materials", "swing"),
    ("FCX", "Freeport-McMoRan", "materials", "swing"),
    ("NEM", "Newmont", "materials", "swing"),
    ("CTVA", "Corteva", "materials", "core"),
    ("CF", "CF Industries Holdings", "materials", "swing"),
    ("MOS", "Mosaic", "materials", "spec"),
    ("NTR", "Nutrien", "materials", "swing"),
    ("ALB", "Albemarle", "materials", "spec"),
    ("FMC", "FMC Corporation", "materials", "spec"),
    ("IFF", "International Flavors & Fragrances", "materials", "swing"),
    ("CE", "Celanese", "materials", "spec"),
    ("EMN", "Eastman Chemical", "materials", "swing"),
    ("AVTR", "Avantor", "materials", "spec"),
    ("PKG", "Packaging Corporation of America", "materials", "swing"),
    ("IP", "International Paper", "materials", "swing"),
    ("BALL", "Ball Corporation", "materials", "swing"),
    ("AMCR", "Amcor", "materials", "swing"),
    ("CRS", "Carpenter Technology", "materials", "spec"),
    ("ATI", "ATI", "materials", "spec"),
    # ── Communication / media ────────────────────────────────────────────────
    ("GOOGL", "Alphabet Class A", "communication", "core"),
    ("META", "Meta Platforms", "communication", "core"),
    ("NFLX", "Netflix", "communication", "core"),
    ("DIS", "Walt Disney", "communication", "core"),
    ("CMCSA", "Comcast", "communication", "swing"),
    ("T", "AT&T", "communication", "core"),
    ("VZ", "Verizon Communications", "communication", "core"),
    ("TMUS", "T-Mobile US", "communication", "core"),
    ("CHTR", "Charter Communications", "communication", "swing"),
    ("WBD", "Warner Bros. Discovery", "communication", "spec"),
    ("FOXA", "Fox Class A", "communication", "swing"),
    ("PARA", "Paramount Global", "communication", "spec"),
    ("EA", "Electronic Arts", "communication", "swing"),
    ("TTWO", "Take-Two Interactive", "communication", "swing"),
    ("NWSA", "News Corp Class A", "communication", "swing"),
    ("TKO", "TKO Group Holdings", "communication", "swing"),
    ("WBA", "Walgreens Boots Alliance", "consumer", "spec"),
    ("IPG", "Interpublic Group", "communication", "swing"),
    # ── Utilities ────────────────────────────────────────────────────────────
    ("NEE", "NextEra Energy", "utilities", "core"),
    ("DUK", "Duke Energy", "utilities", "core"),
    ("SO", "Southern Company", "utilities", "core"),
    ("D", "Dominion Energy", "utilities", "core"),
    ("AEP", "American Electric Power", "utilities", "core"),
    ("EXC", "Exelon", "utilities", "core"),
    ("XEL", "Xcel Energy", "utilities", "core"),
    ("PCG", "PG&E", "utilities", "swing"),
    ("CEG", "Constellation Energy", "utilities", "swing"),
    ("VST", "Vistra", "utilities", "swing"),
    ("NRG", "NRG Energy", "utilities", "swing"),
    ("FE", "FirstEnergy", "utilities", "swing"),
    ("ES", "Eversource Energy", "utilities", "swing"),
    ("DTE", "DTE Energy", "utilities", "core"),
    ("AEE", "Ameren", "utilities", "core"),
    ("CMS", "CMS Energy", "utilities", "swing"),
    ("CNP", "CenterPoint Energy", "utilities", "swing"),
    ("ATO", "Atmos Energy", "utilities", "swing"),
    ("LNT", "Alliant Energy", "utilities", "swing"),
    ("AWK", "American Water Works", "utilities", "core"),
    # ── Real estate (REITs) ──────────────────────────────────────────────────
    ("PLD", "Prologis", "real_estate", "core"),
    ("AMT", "American Tower", "real_estate", "core"),
    ("EQIX", "Equinix", "real_estate", "core"),
    ("WELL", "Welltower", "real_estate", "core"),
    ("SPG", "Simon Property Group", "real_estate", "swing"),
    ("PSA", "Public Storage", "real_estate", "core"),
    ("O", "Realty Income", "real_estate", "swing"),
    ("CCI", "Crown Castle", "real_estate", "swing"),
    ("DLR", "Digital Realty Trust", "real_estate", "swing"),
    ("EXR", "Extra Space Storage", "real_estate", "swing"),
    ("AVB", "AvalonBay Communities", "real_estate", "swing"),
    ("EQR", "Equity Residential", "real_estate", "swing"),
    ("VICI", "VICI Properties", "real_estate", "swing"),
    ("IRM", "Iron Mountain", "real_estate", "swing"),
    ("SBAC", "SBA Communications", "real_estate", "swing"),
    ("WPC", "W. P. Carey", "real_estate", "swing"),
    ("INVH", "Invitation Homes", "real_estate", "swing"),
    ("CBRE", "CBRE Group", "real_estate", "swing"),
    # ── Crypto / blockchain (high beta) ──────────────────────────────────────
    ("MSTR", "MicroStrategy", "technology", "spec"),
    ("MARA", "MARA Holdings", "technology", "spec"),
    ("RIOT", "Riot Platforms", "technology", "spec"),
    ("CLSK", "CleanSpark", "technology", "spec"),
    ("BITF", "Bitfarms", "technology", "spec"),
    ("CORZ", "Core Scientific", "technology", "spec"),
    ("IREN", "IREN", "technology", "spec"),
    ("BMNR", "Bitmine Immersion", "technology", "spec"),
    ("GLXY", "Galaxy Digital", "financials", "spec"),
    ("CRCL", "Circle Internet Group", "financials", "spec"),
]


def build_block(sym: str, name: str, sector: str, kind: str) -> str:
    role, profile, base_tags = KIND[kind]
    tags = base_tags + [sector]
    tag_str = "[" + ", ".join(tags) + "]"
    # Quote the symbol so YAML-1.1 boolean tickers (ON/NO/OFF/YES/Y/N/TRUE/FALSE)
    # and any all-caps lookalikes stay strings.
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

    # Insert new rows at the END of the symbols list — right before the first
    # top-level key (column-0, non-comment) that follows `symbols:`.
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
        "  # ── Staged expansion 2 (2026-06-04): S&P 500 remainder + liquid mid-caps\n"
        "  #    + REITs for the rotating discovery pool. primary/speculative only\n"
        "  #    (no watchlist_core). Symbols quoted. Research/scanning only.\n"
    )
    new_lines = lines[:insert_at] + [header] + blocks + ["\n"] + lines[insert_at:]
    CONFIG.write_text("".join(new_lines), encoding="utf-8")

    # Validate: reload + assert no duplicates, no boolean symbols, schema intact.
    reloaded = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    syms = [x["symbol"] for x in reloaded["symbols"]]
    non_str = [s for s in syms if not isinstance(s, str)]
    assert not non_str, f"non-string symbols introduced: {non_str}"
    dupes = {s for s in syms if syms.count(s) > 1}
    assert not dupes, f"duplicate symbols introduced: {dupes}"
    for x in reloaded["symbols"][-len(added):]:
        assert set(x.keys()) >= {"symbol", "name", "tags", "sector", "universe_role", "demo_profile"}

    print(f"Added {len(added)} symbols: {before} -> {len(syms)}")
    print("New:", ", ".join(added))


if __name__ == "__main__":
    main()
