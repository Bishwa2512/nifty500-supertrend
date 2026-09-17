import os
import io
import gzip
import json
import sqlite3
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go

# ============================================================
# NIFTY 500 WEEKLY HEIKIN ASHI + SUPERTREND (7,3) SCANNER
# Single-file Streamlit application
#
# Requirements:
#   pip install streamlit pandas numpy requests plotly
#
# Put ind_nifty500list.csv in the same folder as this file.
#
# Set your NEW Upstox token as:
#   Linux/VPS:
#       export UPSTOX_ACCESS_TOKEN="YOUR_NEW_TOKEN"
#
#   Windows PowerShell:
#       $env:UPSTOX_ACCESS_TOKEN="YOUR_NEW_TOKEN"
#
#   Streamlit Cloud secrets:
#       UPSTOX_ACCESS_TOKEN = "YOUR_NEW_TOKEN"
#
# Never hard-code your token in this file.
# ============================================================

APP_TITLE = "NIFTY 500 Weekly Supertrend Scanner"
NIFTY500_FILE = "ind_nifty500list.csv"
DATABASE_FILE = "scanner.db"

ATR_PERIOD = 7
SUPERTREND_MULTIPLIER = 3
HISTORY_WEEKS = 60
REFRESH_HOURS = 4

UPSTOX_HISTORY_URL = "https://api.upstox.com/v3/historical-candle"
UPSTOX_LTP_URL = "https://api.upstox.com/v2/market-quote/ltp"
UPSTOX_INSTRUMENT_URL = (
    "https://assets.upstox.com/market-quote/"
    "instruments/exchange/complete.json.gz"
)

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📊",
    layout="wide"
)

st.title("📊 NIFTY 500 Weekly Heikin Ashi Supertrend")
st.caption(
    "Weekly • Heikin Ashi • Supertrend (7,3) • Upstox • "
    "4-hour scanner • Friday manual check"
)


# ============================================================
# AUTHENTICATION
# ============================================================

def get_token():
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if token:
        return token.strip()

    try:
        token = st.secrets["UPSTOX_ACCESS_TOKEN"]
        if token:
            return str(token).strip()
    except Exception:
        pass

    return None


TOKEN = get_token()

if not TOKEN:
    st.error("UPSTOX_ACCESS_TOKEN is not configured.")
    st.markdown("""
### Configure the token

**Linux / VPS**
```bash
export UPSTOX_ACCESS_TOKEN="YOUR_NEW_TOKEN"
```

**Windows PowerShell**
```powershell
$env:UPSTOX_ACCESS_TOKEN="YOUR_NEW_TOKEN"
```

**Streamlit Cloud**

Add this under App → Settings → Secrets:

```toml
UPSTOX_ACCESS_TOKEN = "YOUR_NEW_TOKEN"
```

Do not put the token in the CSV or this Python file.
""")
    st.stop()

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {TOKEN}",
}


# ============================================================
# DATABASE
# ============================================================

@st.cache_resource
def get_connection():
    return sqlite3.connect(
        DATABASE_FILE,
        check_same_thread=False
    )

conn = get_connection()


def initialize_database():
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            company TEXT,
            instrument_key TEXT,
            signal_week TEXT,
            signal_date TEXT,
            previous_direction TEXT,
            current_direction TEXT,
            ha_close REAL,
            supertrend REAL,
            status TEXT DEFAULT 'ACTIVE',
            created_at TEXT,
            closed_at TEXT,
            UNIQUE(symbol, signal_week)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scanner_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT,
            total_stocks INTEGER,
            successful INTEGER,
            failed INTEGER,
            new_signals INTEGER
        )
    """)

    conn.commit()


initialize_database()


# ============================================================
# NIFTY 500
# ============================================================

# ============================================================
# HARD-CODED NIFTY 500 SYMBOLS
# ============================================================

NIFTY500_SYMBOLS = ['360ONE', '3MINDIA', 'ABB', 'ACC', 'ACMESOLAR', 'AIAENG', 'APLAPOLLO', 'AUBANK', 'AWL', 'AADHARHFC', 'AARTIIND', 'AAVAS', 'ABBOTINDIA', 'ACE', 'ACUTAAS', 'ADANIENSOL', 'ADANIENT', 'ADANIGREEN', 'ADANIPORTS', 'ADANIPOWER', 'ATGL', 'ABCAPITAL', 'ABFRL', 'ABLBL', 'ABREL', 'ABSLAMC', 'CPPLUS', 'AEGISLOG', 'AEGISVOPAK', 'AFCONS', 'AFFLE', 'AJANTPHARM', 'ALKEM', 'ABDL', 'ARE&M', 'AMBER', 'AMBUJACEM', 'ANANDRATHI', 'ANANTRAJ', 'ANGELONE', 'ANTHEM', 'ANURAS', 'APARINDS', 'APOLLOHOSP', 'APOLLOTYRE', 'APTUS', 'ASAHIINDIA', 'ASHOKLEY', 'ASIANPAINT', 'ASTERDM', 'ASTRAL', 'ATHERENERG', 'ATUL', 'AUROPHARMA', 'AIIL', 'DMART', 'AXISBANK', 'BEML', 'BLS', 'BSE', 'BAJAJ-AUTO', 'BAJFINANCE', 'BAJAJFINSV', 'BAJAJHLDNG', 'BAJAJHFL', 'BALKRISIND', 'BALRAMCHIN', 'BANDHANBNK', 'BANKBARODA', 'BANKINDIA', 'MAHABANK', 'BATAINDIA', 'BAYERCROP', 'BELRISE', 'BERGEPAINT', 'BDL', 'BEL', 'BHARATFORG', 'BHEL', 'BPCL', 'BHARTIARTL', 'BHARTIHEXA', 'BIKAJI', 'GROWW', 'BIOCON', 'BSOFT', 'BLUEDART', 'BLUEJET', 'BLUESTARCO', 'BBTC', 'BOSCHLTD', 'FIRSTCRY', 'BRIGADE', 'BRITANNIA', 'MAPMYINDIA', 'CCL', 'CESC', 'CGPOWER', 'CIEINDIA', 'CRISIL', 'CANFINHOME', 'CANBK', 'CANHLIFE', 'CAPLIPOINT', 'CGCL', 'CARBORUNIV', 'CARTRADE', 'CASTROLIND', 'CEATLTD', 'CEMPRO', 'CENTRALBK', 'CDSL', 'CHALET', 'CHAMBLFERT', 'CHENNPETRO', 'CHOICEIN', 'CHOLAHLDNG', 'CHOLAFIN', 'CIPLA', 'CUB', 'CLEAN', 'COALINDIA', 'COCHINSHIP', 'COFORGE', 'COHANCE', 'COLPAL', 'CAMS', 'CONCORDBIO', 'CONCOR', 'COROMANDEL', 'CRAFTSMAN', 'CREDITACC', 'CROMPTON', 'CUMMINSIND', 'CYIENT', 'DCMSHRIRAM', 'DLF', 'DOMS', 'DABUR', 'DALBHARAT', 'DATAPATTNS', 'DEEPAKFERT', 'DEEPAKNTR', 'DELHIVERY', 'DEVYANI', 'DIVISLAB', 'DIXON', 'LALPATHLAB', 'DRREDDY', 'DUMMYHEG', 'EIDPARRY', 'EIHOTEL', 'EICHERMOT', 'ELECON', 'ELGIEQUIP', 'EMAMILTD', 'EMCURE', 'EMMVEE', 'ENDURANCE', 'ENGINERSIN', 'ERIS', 'ESCORTS', 'ETERNAL', 'EXIDEIND', 'NYKAA', 'FEDERALBNK', 'FACT', 'FINCABLES', 'FSL', 'FIVESTAR', 'FORCEMOT', 'FORTIS', 'GAIL', 'GVT&D', 'GMRAIRPORT', 'GABRIEL', 'GALLANTT', 'GRSE', 'GICRE', 'GILLETTE', 'GLAND', 'GLAXO', 'GLENMARK', 'MEDANTA', 'GODIGIT', 'GPIL', 'GODFRYPHLP', 'GODREJCP', 'GODREJIND', 'GODREJPROP', 'GRANULES', 'GRAPHITE', 'GRASIM', 'GRAVITA', 'GESHIP', 'FLUOROCHEM', 'GMDCLTD', 'HBLENGINE', 'HCLTECH', 'HDBFS', 'HDFCAMC', 'HDFCBANK', 'HDFCLIFE', 'HEG', 'HFCL', 'HAVELLS', 'HEROMOTOCO', 'HEXT', 'HSCL', 'HINDALCO', 'HAL', 'HINDCOPPER', 'HINDPETRO', 'HINDUNILVR', 'HINDZINC', 'POWERINDIA', 'HOMEFIRST', 'HONASA', 'HONAUT', 'HUDCO', 'HYUNDAI', 'ICICIBANK', 'ICICIGI', 'ICICIAMC', 'ICICIPRULI', 'IDBI', 'IDFCFIRSTB', 'IFCI', 'IIFL', 'IRB', 'IRCON', 'ITCHOTELS', 'ITC', 'ITI', 'INDGN', 'INDIACEM', 'INDIAMART', 'INDIANB', 'IEX', 'INDHOTEL', 'IOC', 'IOB', 'IRCTC', 'IRFC', 'IREDA', 'IGL', 'INDUSTOWER', 'INDUSINDBK', 'NAUKRI', 'INFY', 'INOXWIND', 'INTELLECT', 'INDIGO', 'IGIL', 'IKS', 'IPCALAB', 'JKCEMENT', 'JBMA', 'JKTYRE', 'JMFINANCIL', 'JSWCEMENT', 'JSWDULUX', 'JSWENERGY', 'JSWINFRA', 'JSWSTEEL', 'JAINREC', 'JPPOWER', 'J&KBANK', 'JINDALSAW', 'JSL', 'JINDALSTEL', 'JIOFIN', 'JUBLFOOD', 'JUBLINGREA', 'JUBLPHARMA', 'JWL', 'JYOTICNC', 'KPRMILL', 'KEI', 'KPITTECH', 'KAJARIACER', 'KPIL', 'KALYANKJIL', 'KARURVYSYA', 'KAYNES', 'KEC', 'KFINTECH', 'KIRLOSENG', 'KOTAKBANK', 'KIMS', 'LTF', 'LTTS', 'LGEINDIA', 'LICHSGFIN', 'LTFOODS', 'LTM', 'LT', 'LATENTVIEW', 'LAURUSLABS', 'THELEELA', 'LEMONTREE', 'LENSKART', 'LICI', 'LINDEINDIA', 'LLOYDSME', 'LODHA', 'LUPIN', 'MMTC', 'MRF', 'MGL', 'M&MFIN', 'M&M', 'MANAPPURAM', 'MRPL', 'MANKIND', 'MARICO', 'MARUTI', 'MFSL', 'MAXHEALTH', 'MAZDOCK', 'MEESHO', 'MINDACORP', 'MSUMI', 'MOTILALOFS', 'MPHASIS', 'MCX', 'MUTHOOTFIN', 'NATCOPHARM', 'NBCC', 'NCC', 'NHPC', 'NLCINDIA', 'NMDC', 'NSLNISP', 'NTPCGREEN', 'NTPC', 'NH', 'NATIONALUM', 'NAVA', 'NAVINFLUOR', 'NESTLEIND', 'NETWEB', 'NEULANDLAB', 'NEWGEN', 'NAM-INDIA', 'NIVABUPA', 'NUVAMA', 'NUVOCO', 'OBEROIRLTY', 'ONGC', 'OIL', 'OLAELEC', 'OLECTRA', 'PAYTM', 'ONESOURCE', 'OFSS', 'POLICYBZR', 'PCBL', 'PGEL', 'PIIND', 'PNBHOUSING', 'PTCIL', 'PVRINOX', 'PAGEIND', 'PARADEEP', 'PATANJALI', 'PERSISTENT', 'PETRONET', 'PFIZER', 'PHOENIXLTD', 'PWL', 'PIDILITIND', 'PINELABS', 'PIRAMALFIN', 'PPLPHARMA', 'POLYMED', 'POLYCAB', 'POONAWALLA', 'PFC', 'POWERGRID', 'PREMIERENE', 'PRESTIGE', 'PFOCUS', 'PNB', 'RRKABEL', 'RBLBANK', 'RECLTD', 'RHIM', 'RITES', 'RADICO', 'RVNL', 'RAILTEL', 'RAINBOW', 'RKFORGE', 'REDINGTON', 'RELIANCE', 'RPOWER', 'SBFC', 'SBICARD', 'SBILIFE', 'SJVN', 'SRF', 'SAGILITY', 'SAILIFE', 'SAMMAANCAP', 'MOTHERSON', 'SAPPHIRE', 'SARDAEN', 'SAREGAMA', 'SCHAEFFLER', 'SCHNEIDER', 'SCI', 'SHREECEM', 'SHRIRAMFIN', 'SHYAMMETL', 'ENRIN', 'SIEMENS', 'SIGNATURE', 'SOBHA', 'SOLARINDS', 'SONACOMS', 'SONATSOFTW', 'STARHEALTH', 'SBIN', 'SAIL', 'SUMICHEM', 'SUNPHARMA', 'SUNTV', 'SUNDARMFIN', 'SUPREMEIND', 'SPLPETRO', 'SUZLON', 'SWANCORP', 'SWIGGY', 'SYNGENE', 'SYRMA', 'TBOTEK', 'TVSMOTOR', 'TATACAP', 'TATACHEM', 'TATACOMM', 'TCS', 'TATACONSUM', 'TATAELXSI', 'TATAINVEST', 'TMCV', 'TMPV', 'TATAPOWER', 'TATASTEEL', 'TATATECH', 'TTML', 'TECHM', 'TECHNOE', 'TEGA', 'TEJASNET', 'TENNIND', 'NIACL', 'RAMCOCEM', 'THERMAX', 'TIMKEN', 'TITAGARH', 'TITAN', 'TORNTPHARM', 'TORNTPOWER', 'TARIL', 'TRAVELFOOD', 'TRENT', 'TRIDENT', 'TRITURBINE', 'TIINDIA', 'UCOBANK', 'UNOMINDA', 'UPL', 'UTIAMC', 'ULTRACEMCO', 'UNIONBANK', 'UBL', 'UNITDSPR', 'URBANCO', 'USHAMART', 'VTL', 'VBL', 'VEDL', 'VIJAYA', 'VMM', 'IDEA', 'VOLTAS', 'WAAREEENER', 'WELCORP', 'WELSPUNLIV', 'WHIRLPOOL', 'WIPRO', 'WOCKPHARMA', 'YESBANK', 'ZFCVINDIA', 'ZEEL', 'ZENTEC', 'ZENSARTECH', 'ZYDUSLIFE', 'ZYDUSWELL', 'ECLERX']


def load_nifty500():
    # NIFTY 500 symbols are hard-coded below.
    # No NIFTY 500 CSV is required at runtime.
    return pd.DataFrame({
        "Symbol": NIFTY500_SYMBOLS,
        "Company Name": NIFTY500_SYMBOLS
    })


# ============================================================
# UPSTOX INSTRUMENT MASTER
# ============================================================

@st.cache_data(ttl=86400)
def load_upstox_instruments():
    response = requests.get(
        UPSTOX_INSTRUMENT_URL,
        timeout=90
    )
    response.raise_for_status()

    raw = gzip.decompress(response.content)
    data = json.loads(raw.decode("utf-8"))

    rows = []

    for item in data:
        if item.get("segment") != "NSE_EQ":
            continue

        if item.get("instrument_type") != "EQ":
            continue

        symbol = item.get("trading_symbol")
        instrument_key = item.get("instrument_key")

        if not symbol or not instrument_key:
            continue

        rows.append({
            "Symbol": str(symbol).upper(),
            "instrument_key": instrument_key,
            "Upstox Name": item.get("name", "")
        })

    result = pd.DataFrame(rows)

    if result.empty:
        raise RuntimeError(
            "Upstox instrument master returned no NSE_EQ instruments."
        )

    return result.drop_duplicates(
        subset=["Symbol"]
    )


@st.cache_data(ttl=86400)
def build_universe():
    nifty = load_nifty500()
    instruments = load_upstox_instruments()

    universe = nifty.merge(
        instruments,
        on="Symbol",
        how="left"
    )

    return universe


# ============================================================
# UPSTOX WEEKLY DATA
# ============================================================

def get_weekly_candles(instrument_key):
    today = datetime.now().date()

    from_date = (
        today -
        timedelta(days=HISTORY_WEEKS * 8)
    )

    encoded_key = requests.utils.quote(
        str(instrument_key),
        safe=""
    )

    url = (
        f"{UPSTOX_HISTORY_URL}/"
        f"{encoded_key}/weeks/1/"
        f"{today.isoformat()}/"
        f"{from_date.isoformat()}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    payload = response.json()

    candles = (
        payload
        .get("data", {})
        .get("candles", [])
    )

    if not candles:
        raise RuntimeError(
            "No weekly candles returned."
        )

    rows = []

    for candle in candles:
        if len(candle) < 5:
            continue

        rows.append({
            "timestamp": candle[0],
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "volume": (
                float(candle[5])
                if len(candle) > 5
                else 0
            )
        })

    df = pd.DataFrame(rows)

    if df.empty:
        raise RuntimeError(
            "No usable weekly candles."
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    df = (
        df.sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )

    return df


# ============================================================
# HEIKIN ASHI
# ============================================================

def calculate_heikin_ashi(df):
    df = df.copy()

    df["ha_close"] = (
        df["open"]
        + df["high"]
        + df["low"]
        + df["close"]
    ) / 4.0

    ha_open = []

    for i in range(len(df)):
        if i == 0:
            value = (
                df.loc[i, "open"]
                + df.loc[i, "close"]
            ) / 2.0
        else:
            value = (
                ha_open[i - 1]
                + df.loc[i - 1, "ha_close"]
            ) / 2.0

        ha_open.append(value)

    df["ha_open"] = ha_open

    df["ha_high"] = df[
        ["high", "ha_open", "ha_close"]
    ].max(axis=1)

    df["ha_low"] = df[
        ["low", "ha_open", "ha_close"]
    ].min(axis=1)

    return df


# ============================================================
# ATR
# ============================================================

def calculate_atr(df, period=7):
    high = df["ha_high"]
    low = df["ha_low"]
    previous_close = df["ha_close"].shift(1)

    tr1 = high - low
    tr2 = (high - previous_close).abs()
    tr3 = (low - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    # Wilder-style ATR
    atr = true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    return atr


# ============================================================
# SUPERTREND
# ============================================================

def calculate_supertrend(
    df,
    period=7,
    multiplier=3
):
    df = df.copy()

    df["atr"] = calculate_atr(
        df,
        period
    )

    hl2 = (
        df["ha_high"]
        + df["ha_low"]
    ) / 2.0

    df["basic_upper"] = (
        hl2
        + multiplier * df["atr"]
    )

    df["basic_lower"] = (
        hl2
        - multiplier * df["atr"]
    )

    n = len(df)

    final_upper = np.full(
        n,
        np.nan
    )

    final_lower = np.full(
        n,
        np.nan
    )

    supertrend = np.full(
        n,
        np.nan
    )

    direction = [
        None
    ] * n

    for i in range(n):

        if pd.isna(
            df["atr"].iloc[i]
        ):
            continue

        if i == 0:
            final_upper[i] = (
                df["basic_upper"].iloc[i]
            )
            final_lower[i] = (
                df["basic_lower"].iloc[i]
            )
            continue

        if pd.isna(
            final_upper[i - 1]
        ):
            final_upper[i] = (
                df["basic_upper"].iloc[i]
            )
            final_lower[i] = (
                df["basic_lower"].iloc[i]
            )
            continue

        previous_close = (
            df["ha_close"].iloc[i - 1]
        )

        basic_upper = (
            df["basic_upper"].iloc[i]
        )

        basic_lower = (
            df["basic_lower"].iloc[i]
        )

        if (
            basic_upper < final_upper[i - 1]
            or previous_close > final_upper[i - 1]
        ):
            final_upper[i] = basic_upper
        else:
            final_upper[i] = final_upper[i - 1]

        if (
            basic_lower > final_lower[i - 1]
            or previous_close < final_lower[i - 1]
        ):
            final_lower[i] = basic_lower
        else:
            final_lower[i] = final_lower[i - 1]

        if i == 1 or pd.isna(
            supertrend[i - 1]
        ):
            supertrend[i] = final_lower[i]
            direction[i] = "GREEN"
            continue

        previous_st = supertrend[i - 1]

        if previous_st == final_upper[i - 1]:

            if (
                df["ha_close"].iloc[i]
                <= final_upper[i]
            ):
                supertrend[i] = final_upper[i]
            else:
                supertrend[i] = final_lower[i]

        else:

            if (
                df["ha_close"].iloc[i]
                >= final_lower[i]
            ):
                supertrend[i] = final_lower[i]
            else:
                supertrend[i] = final_upper[i]

        if (
            supertrend[i]
            == final_lower[i]
        ):
            direction[i] = "GREEN"
        else:
            direction[i] = "RED"

    df["final_upper"] = final_upper
    df["final_lower"] = final_lower
    df["supertrend"] = supertrend
    df["direction"] = direction

    return df


# ============================================================
# WEEK IDENTIFICATION
# ============================================================

def add_week_flags(df):
    df = df.copy()

    if df["timestamp"].dt.tz is None:
        df["timestamp"] = (
            df["timestamp"]
            .dt.tz_localize("Asia/Kolkata")
        )
    else:
        df["timestamp"] = (
            df["timestamp"]
            .dt.tz_convert("Asia/Kolkata")
        )

    now = pd.Timestamp.now(
        tz="Asia/Kolkata"
    )

    iso = df[
        "timestamp"
    ].dt.isocalendar()

    current_iso = now.isocalendar()

    df["iso_year"] = iso.year
    df["iso_week"] = iso.week

    df["is_current_week"] = (
        (df["iso_year"] == current_iso.year)
        &
        (df["iso_week"] == current_iso.week)
    )

    return df


# ============================================================
# PROCESS ONE STOCK
# ============================================================

def process_stock(
    symbol,
    company,
    instrument_key
):

    df = get_weekly_candles(
        instrument_key
    )

    df = add_week_flags(df)

    df = calculate_heikin_ashi(df)

    df = calculate_supertrend(
        df,
        ATR_PERIOD,
        SUPERTREND_MULTIPLIER
    )

    # Remove rows where ST cannot yet be calculated
    df_valid = df[
        df["direction"].notna()
    ].copy()

    if len(df_valid) < 5:
        raise RuntimeError(
            "Insufficient valid weekly Supertrend data."
        )

    completed = df_valid[
        ~df_valid["is_current_week"]
    ].copy()

    if len(completed) < 2:
        raise RuntimeError(
            "Insufficient completed weekly candles."
        )

    previous = completed.iloc[-2]
    latest_completed = completed.iloc[-1]

    previous_direction = (
        previous["direction"]
    )

    completed_direction = (
        latest_completed["direction"]
    )

    confirmed_signal = (
        previous_direction == "RED"
        and completed_direction == "GREEN"
    )

    # Current/live week
    live_row = df_valid.iloc[-1]

    if live_row["is_current_week"]:
        live_direction = live_row["direction"]

        live_pending = (
            previous_direction == "RED"
            and live_direction == "GREEN"
        )

    else:
        live_row = latest_completed
        live_direction = completed_direction
        live_pending = False

    return {
        "Symbol": symbol,
        "Company": company,
        "Instrument Key": instrument_key,

        "Previous ST": previous_direction,
        "Completed ST": completed_direction,
        "Live ST": live_direction,

        "Confirmed Signal": confirmed_signal,
        "Live Pending": live_pending,

        "Signal Week": str(
            latest_completed["timestamp"].date()
        ),

        "HA Close": float(
            latest_completed["ha_close"]
        ),

        "Supertrend": float(
            latest_completed["supertrend"]
        ),

        "Live HA Close": float(
            live_row["ha_close"]
        ),

        "Live Price": float(
            live_row["close"]
        ),

        "Data": df
    }


# ============================================================
# SAVE SIGNAL
# ============================================================

def save_signal(result):

    if not result["Confirmed Signal"]:
        return False

    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR IGNORE INTO watchlist
        (
            symbol,
            company,
            instrument_key,
            signal_week,
            signal_date,
            previous_direction,
            current_direction,
            ha_close,
            supertrend,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
        """,
        (
            result["Symbol"],
            result["Company"],
            result["Instrument Key"],
            result["Signal Week"],
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            result["Previous ST"],
            result["Completed ST"],
            result["HA Close"],
            result["Supertrend"],
            datetime.now().isoformat()
        )
    )

    conn.commit()

    return cur.rowcount > 0


# ============================================================
# WATCHLIST STATUS
# ============================================================

def update_watchlist_status(results):

    cur = conn.cursor()

    for result in results:

        # Close an active watchlist entry only when the
        # COMPLETED weekly candle is RED.
        if result["Completed ST"] == "RED":

            cur.execute(
                """
                UPDATE watchlist
                SET
                    status='INACTIVE',
                    closed_at=?
                WHERE
                    symbol=?
                    AND status='ACTIVE'
                """,
                (
                    datetime.now().isoformat(),
                    result["Symbol"]
                )
            )

    conn.commit()


# ============================================================
# FULL SCAN
# ============================================================

def run_full_scan():

    universe = build_universe()

    total = len(universe)

    results = []
    failures = []
    new_signals = 0

    progress = st.progress(0)
    status_box = st.empty()

    for index, row in universe.iterrows():

        symbol = str(row["Symbol"])

        company = (
            str(row["Company Name"])
            if "Company Name" in row
            else symbol
        )

        instrument_key = row[
            "instrument_key"
        ]

        status_box.write(
            f"Scanning {index + 1}/{total}: "
            f"**{symbol}**"
        )

        if (
            pd.isna(instrument_key)
            or not str(instrument_key).strip()
        ):

            failures.append({
                "Symbol": symbol,
                "Company": company,
                "Error": "No Upstox instrument key"
            })

            progress.progress(
                (index + 1) / total
            )
            continue

        try:

            result = process_stock(
                symbol,
                company,
                str(instrument_key)
            )

            results.append(result)

            if save_signal(result):
                new_signals += 1

        except Exception as exc:

            failures.append({
                "Symbol": symbol,
                "Company": company,
                "Error": str(exc)
            })

        progress.progress(
            (index + 1) / total
        )

        # Small delay between requests
        time.sleep(0.05)

    update_watchlist_status(
        results
    )

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO scanner_runs
        (
            run_time,
            total_stocks,
            successful,
            failed,
            new_signals
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(),
            total,
            len(results),
            len(failures),
            new_signals
        )
    )

    conn.commit()

    status_box.success(
        f"Scan complete — "
        f"{len(results)}/{total} successful | "
        f"{len(failures)} failed | "
        f"{new_signals} new confirmed signals"
    )

    return results, failures


# ============================================================
# AUTO-SCAN TIMER
# ============================================================

def should_scan():

    cur = conn.cursor()

    cur.execute(
        """
        SELECT run_time
        FROM scanner_runs
        ORDER BY id DESC
        LIMIT 1
        """
    )

    row = cur.fetchone()

    if not row:
        return True

    try:
        last_run = datetime.fromisoformat(
            row[0]
        )
    except Exception:
        return True

    return (
        datetime.now() - last_run
    ) >= timedelta(
        hours=REFRESH_HOURS
    )


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "Scanner Controls"
)

st.sidebar.write(
    f"Universe: **NIFTY 500**"
)

st.sidebar.write(
    f"Timeframe: **Weekly**"
)

st.sidebar.write(
    f"Candle: **Heikin Ashi**"
)

st.sidebar.write(
    f"Supertrend: **({ATR_PERIOD}, {SUPERTREND_MULTIPLIER})**"
)

st.sidebar.write(
    f"Automatic scan: **Every {REFRESH_HOURS} hours**"
)

manual_scan = st.sidebar.button(
    "🔄 RUN SCANNER NOW",
    use_container_width=True
)

if st.sidebar.button(
    "🧹 CLEAR ACTIVE WATCHLIST",
    use_container_width=True
):

    conn.execute(
        """
        UPDATE watchlist
        SET
            status='INACTIVE',
            closed_at=?
        WHERE status='ACTIVE'
        """,
        (
            datetime.now().isoformat(),
        )
    )

    conn.commit()

    st.success(
        "Active watchlist cleared."
    )

    st.rerun()


# ============================================================
# RUN SCANNER
# ============================================================

if manual_scan or should_scan():

    with st.spinner(
        "Scanning NIFTY 500..."
    ):

        scan_results, scan_failures = (
            run_full_scan()
        )

else:

    scan_results = []
    scan_failures = []


# ============================================================
# LOAD WATCHLIST
# ============================================================

watchlist_df = pd.read_sql_query(
    """
    SELECT
        symbol AS Symbol,
        company AS Company,
        signal_date AS "Signal Date",
        signal_week AS "Signal Week",
        ha_close AS "HA Close",
        previous_direction AS "Previous ST",
        current_direction AS "Signal ST",
        supertrend AS Supertrend,
        status AS Status
    FROM watchlist
    ORDER BY signal_date DESC
    """,
    conn
)


# ============================================================
# LATEST SCAN DATA
# ============================================================

if scan_results:

    latest_df = pd.DataFrame(
        [
            {
                "Symbol": x["Symbol"],
                "Company": x["Company"],
                "Previous ST": x["Previous ST"],
                "Completed ST": x["Completed ST"],
                "Live ST": x["Live ST"],

                "Signal": (
                    "🟢 CONFIRMED"
                    if x["Confirmed Signal"]
                    else (
                        "🟡 LIVE / PENDING"
                        if x["Live Pending"]
                        else ""
                    )
                ),

                "HA Close": round(
                    x["HA Close"],
                    2
                ),

                "Live HA Close": round(
                    x["Live HA Close"],
                    2
                ),

                "Live Price": round(
                    x["Live Price"],
                    2
                ),

                "Signal Week": x[
                    "Signal Week"
                ]
            }
            for x in scan_results
        ]
    )

else:

    latest_df = pd.DataFrame()


# ============================================================
# TABS
# ============================================================

(
    tab_confirmed,
    tab_live,
    tab_watchlist,
    tab_all,
    tab_chart,
    tab_status
) = st.tabs(
    [
        "🔥 CONFIRMED",
        "🟡 LIVE / FRIDAY",
        "👀 WATCHLIST",
        "📊 NIFTY 500",
        "📈 CHART",
        "⚙️ STATUS"
    ]
)


# ============================================================
# CONFIRMED SIGNALS
# ============================================================

with tab_confirmed:

    st.subheader(
        "🔥 Confirmed RED → GREEN"
    )

    st.write(
        "Previous completed weekly candle = RED "
        "and latest completed weekly candle = GREEN."
    )

    if latest_df.empty:

        st.info(
            "No scan data yet. Run the scanner."
        )

    else:

        confirmed = latest_df[
            latest_df["Signal"]
            == "🟢 CONFIRMED"
        ].copy()

        if confirmed.empty:

            st.info(
                "No new confirmed signals."
            )

        else:

            st.success(
                f"{len(confirmed)} confirmed signal(s)"
            )

            st.dataframe(
                confirmed,
                use_container_width=True,
                hide_index=True
            )


# ============================================================
# LIVE / FRIDAY
# ============================================================

with tab_live:

    st.subheader(
        "🟡 Live Weekly RED → GREEN Candidates"
    )

    st.warning(
        "These are developing signals only. "
        "The current weekly candle is still incomplete."
    )

    st.write(
        "Use this tab during the last hour Friday "
        "for your manual check."
    )

    if latest_df.empty:

        st.info(
            "No scan data yet."
        )

    else:

        pending = latest_df[
            latest_df["Signal"]
            == "🟡 LIVE / PENDING"
        ].copy()

        if pending.empty:

            st.info(
                "No live RED → GREEN candidates."
            )

        else:

            st.dataframe(
                pending,
                use_container_width=True,
                hide_index=True
            )


# ============================================================
# WATCHLIST
# ============================================================

with tab_watchlist:

    st.subheader(
        "👀 Persistent Watchlist"
    )

    active = watchlist_df[
        watchlist_df["Status"]
        == "ACTIVE"
    ].copy()

    c1, c2 = st.columns(2)

    c1.metric(
        "Active Stocks",
        len(active)
    )

    c2.metric(
        "Total Signal Records",
        len(watchlist_df)
    )

    if active.empty:

        st.info(
            "No active watchlist stocks."
        )

    else:

        st.dataframe(
            active,
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    st.subheader(
        "Watchlist History"
    )

    if watchlist_df.empty:

        st.info(
            "No watchlist history."
        )

    else:

        st.dataframe(
            watchlist_df,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# ALL NIFTY 500
# ============================================================

with tab_all:

    st.subheader(
        "📊 All NIFTY 500 Stocks"
    )

    if latest_df.empty:

        st.info(
            "No scan data yet."
        )

    else:

        search = st.text_input(
            "Search Symbol or Company",
            key="search_symbol"
        )

        filtered = latest_df.copy()

        if search:

            q = search.upper().strip()

            filtered = filtered[
                filtered["Symbol"]
                .str.upper()
                .str.contains(
                    q,
                    na=False
                )
                |
                filtered["Company"]
                .str.upper()
                .str.contains(
                    q,
                    na=False
                )
            ]

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# CHART
# ============================================================

with tab_chart:

    st.subheader(
        "📈 Weekly Heikin Ashi + Supertrend"
    )

    if not scan_results:

        st.info(
            "Run the scanner first."
        )

    else:

        symbols = sorted(
            [
                x["Symbol"]
                for x in scan_results
            ]
        )

        selected = st.selectbox(
            "Select Stock",
            symbols
        )

        result = next(
            (
                x
                for x in scan_results
                if x["Symbol"] == selected
            ),
            None
        )

        if result:

            data = result["Data"].tail(
                40
            ).copy()

            fig = go.Figure()

            # Heikin Ashi candles
            fig.add_trace(
                go.Candlestick(
                    x=data["timestamp"],
                    open=data["ha_open"],
                    high=data["ha_high"],
                    low=data["ha_low"],
                    close=data["ha_close"],
                    name="Heikin Ashi"
                )
            )

            # Supertrend
            fig.add_trace(
                go.Scatter(
                    x=data["timestamp"],
                    y=data["supertrend"],
                    mode="lines",
                    name="Supertrend (7,3)"
                )
            )

            fig.update_layout(
                title=(
                    f"{selected} — Weekly "
                    "Heikin Ashi + Supertrend (7,3)"
                ),
                xaxis_title="Week",
                yaxis_title="Price",
                height=650,
                xaxis_rangeslider_visible=False
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "Previous ST",
                result["Previous ST"]
            )

            c2.metric(
                "Completed ST",
                result["Completed ST"]
            )

            c3.metric(
                "Live ST",
                result["Live ST"]
            )

            c4.metric(
                "Live Price",
                f"₹{result['Live Price']:,.2f}"
            )


# ============================================================
# STATUS
# ============================================================

with tab_status:

    st.subheader(
        "⚙️ Scanner Status"
    )

    universe = build_universe()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "NIFTY 500 CSV",
        len(universe)
    )

    c2.metric(
        "Instrument Keys",
        int(
            universe["instrument_key"]
            .notna()
            .sum()
        )
    )

    c3.metric(
        "Refresh",
        "4 Hours"
    )

    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            run_time,
            total_stocks,
            successful,
            failed,
            new_signals
        FROM scanner_runs
        ORDER BY id DESC
        LIMIT 1
        """
    )

    last_run = cur.fetchone()

    if last_run:

        run_time = last_run[0]
        total = last_run[1]
        successful = last_run[2]
        failed = last_run[3]
        new_signals = last_run[4]

        st.write(
            f"**Last scan:** {run_time}"
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Scanned",
            total
        )

        c2.metric(
            "Successful",
            successful
        )

        c3.metric(
            "Failed",
            failed
        )

        c4.metric(
            "New Signals",
            new_signals
        )

    else:

        st.warning(
            "No scan has been completed yet."
        )

    if scan_failures:

        st.divider()

        st.subheader(
            "❌ Errors From Current Scan"
        )

        st.dataframe(
            pd.DataFrame(scan_failures),
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    st.markdown(
        """
### Signal rules

**Universe**
- NIFTY 500 from `ind_nifty500list.csv`

**Candle**
- Heikin Ashi

**Timeframe**
- Weekly

**Supertrend**
- ATR period = 7
- Multiplier = 3

**CONFIRMED**
- Previous completed week = RED
- Latest completed week = GREEN

**LIVE / FRIDAY**
- Previous completed week = RED
- Current incomplete weekly candle = GREEN

**Watchlist**
- Confirmed RED → GREEN signals are saved.
- When the completed weekly Supertrend becomes RED,
  the active watchlist entry becomes INACTIVE.

**Refresh**
- Scanner runs automatically after 4 hours have elapsed
  when the Streamlit application is loaded/refreshed.
"""
    )


# ============================================================
# LAST UPDATE / AUTO PAGE REFRESH
# ============================================================

cur = conn.cursor()

cur.execute(
    """
    SELECT run_time
    FROM scanner_runs
    ORDER BY id DESC
    LIMIT 1
    """
)

last = cur.fetchone()

if last:
    st.caption(
        f"Last scanner run: {last[0]} | "
        f"Automatic interval: {REFRESH_HOURS} hours"
    )

# Browser refresh every 4 hours.
# This ensures the Streamlit page itself comes back and
# triggers the should_scan() check.
st.markdown(
    f"""
<script>
setTimeout(function() {{
    window.location.reload();
}}, {REFRESH_HOURS * 60 * 60 * 1000});
</script>
""",
    unsafe_allow_html=True
)

st.caption(
    "For personal use. Market data and signals should be independently verified."
)
