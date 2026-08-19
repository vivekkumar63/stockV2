# backend/domains/data/index_universe.py
"""Sector index definitions and stock→index membership map."""

# yfinance symbols for each of the 7 NSE sector indices
INDEX_DEFINITIONS: dict[str, dict] = {
    "NIFTY BANK":   {"yf_symbol": "^NSEBANK",   "description": "Banking sector"},
    "NIFTY IT":     {"yf_symbol": "^CNXIT",     "description": "Information technology"},
    "NIFTY FMCG":   {"yf_symbol": "^CNXFMCG",   "description": "Fast-moving consumer goods"},
    "NIFTY AUTO":   {"yf_symbol": "^CNXAUTO",   "description": "Automobiles & components"},
    "NIFTY PHARMA": {"yf_symbol": "^CNXPHARMA", "description": "Pharmaceuticals"},
    "NIFTY METAL":  {"yf_symbol": "^CNXMETAL",  "description": "Metals & mining"},
    "NIFTY ENERGY": {"yf_symbol": "^CNXENERGY", "description": "Energy & utilities"},
}

# One primary parent index per stock.
# Stocks absent from this map receive a neutral alignment score (50/100).
STOCK_INDEX_MAP: dict[str, str] = {
    # ── NIFTY BANK ────────────────────────────────────────────────────────────
    "HDFCBANK": "NIFTY BANK",   "ICICIBANK": "NIFTY BANK",   "KOTAKBANK": "NIFTY BANK",
    "SBIN": "NIFTY BANK",       "AXISBANK": "NIFTY BANK",    "INDUSINDBK": "NIFTY BANK",
    "BANDHANBNK": "NIFTY BANK", "PNB": "NIFTY BANK",         "BANKBARODA": "NIFTY BANK",
    "FEDERALBNK": "NIFTY BANK", "IDFCFIRSTB": "NIFTY BANK",  "AUBANK": "NIFTY BANK",
    "CSBBANK": "NIFTY BANK",    "DCBBANK": "NIFTY BANK",     "RBLBANK": "NIFTY BANK",
    "YESBANK": "NIFTY BANK",    "KARURVYSYA": "NIFTY BANK",  "SOUTHBANK": "NIFTY BANK",
    "CANBK": "NIFTY BANK",      "UNIONBANK": "NIFTY BANK",   "EQUITAS": "NIFTY BANK",
    "UJJIVANSF": "NIFTY BANK",  "SBFC": "NIFTY BANK",        "VIJAYABANK": "NIFTY BANK",
    # ── NIFTY IT ──────────────────────────────────────────────────────────────
    "TCS": "NIFTY IT",          "INFY": "NIFTY IT",          "HCLTECH": "NIFTY IT",
    "WIPRO": "NIFTY IT",        "TECHM": "NIFTY IT",         "LTIM": "NIFTY IT",
    "MPHASIS": "NIFTY IT",      "COFORGE": "NIFTY IT",       "PERSISTENT": "NIFTY IT",
    "OFSS": "NIFTY IT",         "LTTS": "NIFTY IT",          "KPITTECH": "NIFTY IT",
    "TATAELXSI": "NIFTY IT",    "NIITLTD": "NIFTY IT",       "BSOFT": "NIFTY IT",
    "MASTEK": "NIFTY IT",       "HEXAWARE": "NIFTY IT",      "ZENSAR": "NIFTY IT",
    "CYIENT": "NIFTY IT",       "ECLERX": "NIFTY IT",        "TANLA": "NIFTY IT",
    "INTELLECT": "NIFTY IT",    "NEWGEN": "NIFTY IT",        "SAKSOFT": "NIFTY IT",
    "SONATSOFTW": "NIFTY IT",   "MINDTREE": "NIFTY IT",      "CIGNITI": "NIFTY IT",
    "QUICKHEAL": "NIFTY IT",    "NETSOL": "NIFTY IT",        "XCHANGING": "NIFTY IT",
    # ── NIFTY FMCG ────────────────────────────────────────────────────────────
    "HINDUNILVR": "NIFTY FMCG", "ITC": "NIFTY FMCG",        "NESTLEIND": "NIFTY FMCG",
    "BRITANNIA": "NIFTY FMCG",  "DABUR": "NIFTY FMCG",      "MARICO": "NIFTY FMCG",
    "GODREJCP": "NIFTY FMCG",   "TATACONSUM": "NIFTY FMCG",  "COLPAL": "NIFTY FMCG",
    "EMAMILTD": "NIFTY FMCG",   "RADICO": "NIFTY FMCG",     "VBL": "NIFTY FMCG",
    "JYOTHYLAB": "NIFTY FMCG",  "BIKAJI": "NIFTY FMCG",     "HATSUN": "NIFTY FMCG",
    "ZYDUSWELL": "NIFTY FMCG",  "BAJAJCON": "NIFTY FMCG",   "PGHH": "NIFTY FMCG",
    "TTKPRESTIG": "NIFTY FMCG", "HAWKINS": "NIFTY FMCG",
    # ── NIFTY AUTO ────────────────────────────────────────────────────────────
    "MARUTI": "NIFTY AUTO",     "TATAMOTORS": "NIFTY AUTO",  "M&M": "NIFTY AUTO",
    "BAJAJ-AUTO": "NIFTY AUTO", "EICHERMOT": "NIFTY AUTO",   "HEROMOTOCO": "NIFTY AUTO",
    "TVSMOTORS": "NIFTY AUTO",  "TVSMOTOR": "NIFTY AUTO",   "ASHOKLEY": "NIFTY AUTO",
    "BALKRISIND": "NIFTY AUTO", "MOTHERSON": "NIFTY AUTO",   "BOSCHLTD": "NIFTY AUTO",
    "EXIDEIND": "NIFTY AUTO",   "MRF": "NIFTY AUTO",         "APOLLOTYRE": "NIFTY AUTO",
    "CEATLTD": "NIFTY AUTO",    "AMARAJABAT": "NIFTY AUTO",  "JKTYRE": "NIFTY AUTO",
    "ESCORTS": "NIFTY AUTO",    "BHARATFORG": "NIFTY AUTO",  "SUNDRMFAST": "NIFTY AUTO",
    "WABCOINDIA": "NIFTY AUTO", "MAHINDCIE": "NIFTY AUTO",   "CRAFTSMAN": "NIFTY AUTO",
    "LUMAX": "NIFTY AUTO",      "SUPRAJIT": "NIFTY AUTO",    "MINDA": "NIFTY AUTO",
    "TIINDIA": "NIFTY AUTO",
    # ── NIFTY PHARMA ──────────────────────────────────────────────────────────
    "SUNPHARMA": "NIFTY PHARMA",  "DRREDDY": "NIFTY PHARMA",   "CIPLA": "NIFTY PHARMA",
    "DIVISLAB": "NIFTY PHARMA",   "BIOCON": "NIFTY PHARMA",    "AUROPHARMA": "NIFTY PHARMA",
    "LUPIN": "NIFTY PHARMA",      "ALKEM": "NIFTY PHARMA",     "TORNTPHARM": "NIFTY PHARMA",
    "ABBOTINDIA": "NIFTY PHARMA", "IPCALAB": "NIFTY PHARMA",   "AJANTPHARM": "NIFTY PHARMA",
    "LAURUSLABS": "NIFTY PHARMA", "GRANULES": "NIFTY PHARMA",  "GLENMARK": "NIFTY PHARMA",
    "NATCOPHARM": "NIFTY PHARMA", "JBCHEPHARM": "NIFTY PHARMA","SANOFI": "NIFTY PHARMA",
    "PFIZER": "NIFTY PHARMA",     "GLAXO": "NIFTY PHARMA",     "STRIDES": "NIFTY PHARMA",
    "MARKSANS": "NIFTY PHARMA",   "IOLCP": "NIFTY PHARMA",     "HIKAL": "NIFTY PHARMA",
    "WOCKPHARMA": "NIFTY PHARMA", "SOLARA": "NIFTY PHARMA",
    # ── NIFTY METAL ───────────────────────────────────────────────────────────
    "TATASTEEL": "NIFTY METAL",   "JSWSTEEL": "NIFTY METAL",   "HINDALCO": "NIFTY METAL",
    "VEDL": "NIFTY METAL",        "COALINDIA": "NIFTY METAL",  "NMDC": "NIFTY METAL",
    "SAIL": "NIFTY METAL",        "NATIONALUM": "NIFTY METAL", "WELSPUNLIVING": "NIFTY METAL",
    "RATNAMANI": "NIFTY METAL",   "JINDALSAW": "NIFTY METAL",  "APLAPOLLO": "NIFTY METAL",
    "HINDCOPPER": "NIFTY METAL",  "GPIL": "NIFTY METAL",       "JSPL": "NIFTY METAL",
    "WELCORP": "NIFTY METAL",     "HINDZINC": "NIFTY METAL",   "MOIL": "NIFTY METAL",
    "MAHSEAMLES": "NIFTY METAL",
    # ── NIFTY ENERGY ──────────────────────────────────────────────────────────
    "RELIANCE": "NIFTY ENERGY",   "ONGC": "NIFTY ENERGY",     "NTPC": "NIFTY ENERGY",
    "POWERGRID": "NIFTY ENERGY",  "BPCL": "NIFTY ENERGY",     "IOC": "NIFTY ENERGY",
    "GAIL": "NIFTY ENERGY",       "ADANIGREEN": "NIFTY ENERGY","TATAPOWER": "NIFTY ENERGY",
    "ADANIENT": "NIFTY ENERGY",   "CESC": "NIFTY ENERGY",     "TORNTPOWER": "NIFTY ENERGY",
    "IGL": "NIFTY ENERGY",        "MGL": "NIFTY ENERGY",      "PETRONET": "NIFTY ENERGY",
    "HINDPETRO": "NIFTY ENERGY",  "MRPL": "NIFTY ENERGY",     "JSWENERGY": "NIFTY ENERGY",
    "SUZLON": "NIFTY ENERGY",     "NHPC": "NIFTY ENERGY",     "SJVN": "NIFTY ENERGY",
    "ADANITRANS": "NIFTY ENERGY", "AEGASIND": "NIFTY ENERGY",
}
