import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Hilega-Milega ETF Scanner",
    page_icon="📊",
    layout="wide"
)

# ============================================================
# ETF LIST
# ============================================================

ETF_LIST = [
    "CPSEETF",
    "SETFGOLD",
    "GOLDBEES",
    "TATAGOLD",
    "HNGSNGBEES",
    "MAHKTECH",
    "MONQ50",
    "MON100",
    "NIF100IETF",
    "LOWVOLIETF",
    "MOM30IETF",
    "MOMOMENTUM",
    "NIFTYQLITY",
    "NIFTYIETF",
    "SETFNIF50",
    "NIFTYBEES",
    "SBINEQWETF",
    "ALPHA",
    "ALPL30IETF",
    "AUTOBEES",
    "BANKBEES",
    "SETFNIFBK",
    "BANKIETF",
    "DIVOPPBEES",
    "BFSI",
    "FMCGIETF",
    "HEALTHIETF",
    "HEALTHY",
    "CONSUMIETF",
    "CONSUMBEES",
    "TNIDETF",
    "MAKEINDIA",
    "IT",
    "ITIETF",
    "ITBEES",
    "MOM100",
    "MIDCAPIETF",
    "MID150BEES",
    "HDFCMID150",
    "MIDCAPETF",
    "UTINEXT50",
    "NEXT50IETF",
    "JUNIORBEES",
    "PHARMABEES",
    "PVTBANIETF",
    "PSUBANKADD",
    "PSUBNKBEES",
    "PSUBNKIETF",
    "HDFCSML250",
    "ESG",
    "NV20BEES",
    "NV20IETF",
    "MAFANG",
    "MASPTOP50",
    "BSE500IETF",
    "MIDSELIETF",
    "SILVERIETF",
    "SILVERBEES",
    "HDFCSILVER",
]

TICKERS = [f"{symbol}.NS" for symbol in ETF_LIST]

# ============================================================
# HILEGA-MILEGA SETTINGS
# ============================================================

RSI_LENGTH = 9
EMA_LENGTH = 3
WMA_LENGTH = 21

OVERBOUGHT = 60
OVERSOLD = 40

# ============================================================
# INDICATOR FUNCTIONS
# ============================================================

def calculate_rsi(series, length=9):
    """
    TradingView ta.rsi() style Wilder RSI.
    """

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_wma(series, length=21):
    """
    TradingView ta.wma() equivalent.
    """

    weights = np.arange(1, length + 1)
    weight_sum = weights.sum()

    return series.rolling(length).apply(
        lambda x: np.dot(x, weights) / weight_sum,
        raw=True
    )


def calculate_hilega_milega(df):
    """
    Hilega-Milega:

    RSI = RSI(9)
    EMA = EMA(RSI, 3)
    WMA = WMA(RSI, 21)

    BUY:
        RSI > WMA
        AND
        EMA > WMA

    EXIT:
        RSI <= WMA
        OR
        EMA <= WMA

    Signals are generated only when the condition changes.
    """

    df = df.copy()

    df["RSI"] = calculate_rsi(
        df["Close"],
        RSI_LENGTH
    )

    df["EMA"] = df["RSI"].ewm(
        span=EMA_LENGTH,
        adjust=False
    ).mean()

    df["WMA"] = calculate_wma(
        df["RSI"],
        WMA_LENGTH
    )

    # ========================================================
    # MAIN CONDITION
    # ========================================================

    df["Bullish"] = (
        (df["RSI"] > df["WMA"]) &
        (df["EMA"] > df["WMA"])
    )

    previous_bullish = (
        df["Bullish"]
        .shift(1)
        .fillna(False)
        .astype(bool)
    )

    # ========================================================
    # BUY ONLY WHEN CONDITION CHANGES FALSE -> TRUE
    # ========================================================

    df["BUY"] = (
        df["Bullish"] &
        ~previous_bullish
    )

    # ========================================================
    # EXIT ONLY WHEN CONDITION CHANGES TRUE -> FALSE
    # ========================================================

    df["EXIT"] = (
        previous_bullish &
        ~df["Bullish"]
    )

    return df


# ============================================================
# DOWNLOAD 6 MONTHS DATA
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def download_historical_data():

    data = yf.download(
        tickers=TICKERS,
        period="6mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False
    )

    return data


# ============================================================
# GET CURRENT LTP
# ============================================================

@st.cache_data(ttl=60, show_spinner=False)
def get_current_prices():

    try:

        data = yf.download(
            tickers=TICKERS,
            period="1d",
            interval="1m",
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False
        )

        prices = {}

        for symbol in ETF_LIST:

            ticker = f"{symbol}.NS"

            try:

                if ticker not in data.columns.get_level_values(0):
                    prices[symbol] = np.nan
                    continue

                temp = data[ticker].copy()

                temp = temp.dropna(subset=["Close"])

                if len(temp) > 0:
                    prices[symbol] = float(temp["Close"].iloc[-1])
                else:
                    prices[symbol] = np.nan

            except Exception:
                prices[symbol] = np.nan

        return prices

    except Exception:

        return {symbol: np.nan for symbol in ETF_LIST}


# ============================================================
# EXTRACT SINGLE ETF DATA
# ============================================================

def get_etf_data(all_data, symbol):

    ticker = f"{symbol}.NS"

    try:

        # Multi-ticker download
        if isinstance(all_data.columns, pd.MultiIndex):

            if ticker not in all_data.columns.get_level_values(0):
                return None

            df = all_data[ticker].copy()

        else:

            df = all_data.copy()

        required = ["Open", "High", "Low", "Close", "Volume"]

        for col in required:
            if col not in df.columns:
                return None

        df = df[required].copy()

        df = df.dropna(subset=["Close"])

        if df.empty:
            return None

        return df

    except Exception:

        return None


# ============================================================
# BUILD SCANNER
# ============================================================

def build_scanner(all_data, current_prices):

    results = []

    processed_data = {}

    for symbol in ETF_LIST:

        df = get_etf_data(
            all_data,
            symbol
        )

        if df is None or len(df) < WMA_LENGTH + 5:
            continue

        df = calculate_hilega_milega(df)

        processed_data[symbol] = df

        last = df.iloc[-1]

        previous = (
            df.iloc[-2]
            if len(df) >= 2
            else None
        )

        rsi = last["RSI"]
        ema = last["EMA"]
        wma = last["WMA"]

        bullish = bool(last["Bullish"])

        if bullish:

            status = "HOLD"

        else:

            status = "EXIT"

        # ----------------------------------------------------
        # Last signal
        # ----------------------------------------------------

        signal_rows = df[
            df["BUY"] | df["EXIT"]
        ]

        if not signal_rows.empty:

            last_signal_row = signal_rows.iloc[-1]
            last_signal_date = signal_rows.index[-1]

            if bool(last_signal_row["BUY"]):
                last_signal = "BUY"
            else:
                last_signal = "EXIT"

        else:

            last_signal = "-"
            last_signal_date = None

        # ----------------------------------------------------
        # Today's new signal
        # ----------------------------------------------------

        if bool(last["BUY"]):

            today_signal = "BUY"

        elif bool(last["EXIT"]):

            today_signal = "EXIT"

        else:

            today_signal = "-"

        # ----------------------------------------------------
        # Current price
        # ----------------------------------------------------

        current_price = current_prices.get(
            symbol,
            np.nan
        )

        results.append({

            "ETF": symbol,

            "LTP": (
                round(current_price, 2)
                if pd.notna(current_price)
                else round(float(last["Close"]), 2)
            ),

            "Daily Close": round(
                float(last["Close"]),
                2
            ),

            "RSI(9)": round(
                float(rsi),
                2
            ) if pd.notna(rsi) else np.nan,

            "EMA(3)": round(
                float(ema),
                2
            ) if pd.notna(ema) else np.nan,

            "WMA(21)": round(
                float(wma),
                2
            ) if pd.notna(wma) else np.nan,

            "RSI > WMA": (
                "YES"
                if pd.notna(rsi)
                and pd.notna(wma)
                and rsi > wma
                else "NO"
            ),

            "EMA > WMA": (
                "YES"
                if pd.notna(ema)
                and pd.notna(wma)
                and ema > wma
                else "NO"
            ),

            "Signal": today_signal,

            "Status": status,

            "Last Signal": last_signal,

            "Last Signal Date": (
                last_signal_date.strftime("%Y-%m-%d")
                if last_signal_date is not None
                else "-"
            )
        })

    return (
        pd.DataFrame(results),
        processed_data
    )


# ============================================================
# STREAMLIT UI
# ============================================================

st.title("📊 Hilega-Milega ETF Scanner")

st.caption(
    "Hilega-Milega by NK Sir (DalRoti) | "
    "Daily timeframe | 6 months historical data"
)

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("Settings")

    st.write(
        f"RSI Length: **{RSI_LENGTH}**"
    )

    st.write(
        f"EMA Length: **{EMA_LENGTH}**"
    )

    st.write(
        f"WMA Length: **{WMA_LENGTH}**"
    )

    st.write(
        f"Overbought: **{OVERBOUGHT}**"
    )

    st.write(
        f"Oversold: **{OVERSOLD}**"
    )

    st.divider()

    st.write(
        f"ETFs: **{len(ETF_LIST)}**"
    )

    st.write(
        "Historical: **6 months**"
    )

    st.write(
        "Timeframe: **Daily**"
    )

    st.divider()

    refresh = st.button(
        "🔄 Refresh Data",
        use_container_width=True
    )

    if refresh:

        st.cache_data.clear()

        st.rerun()


# ============================================================
# DOWNLOAD DATA
# ============================================================

with st.spinner(
    "Fetching 6 months daily data from Yahoo Finance..."
):

    historical_data = download_historical_data()


if historical_data is None or historical_data.empty:

    st.error(
        "Yahoo Finance se historical data nahi mila."
    )

    st.stop()


# ============================================================
# CURRENT LTP
# ============================================================

with st.spinner(
    "Fetching current LTP..."
):

    current_prices = get_current_prices()


# ============================================================
# BUILD RESULTS
# ============================================================

scanner_df, processed_data = build_scanner(
    historical_data,
    current_prices
)


if scanner_df.empty:

    st.error(
        "Kisi ETF ka valid data nahi mila."
    )

    st.stop()


# ============================================================
# SUMMARY
# ============================================================

buy_count = int(
    (scanner_df["Signal"] == "BUY").sum()
)

exit_count = int(
    (scanner_df["Signal"] == "EXIT").sum()
)

hold_count = int(
    (scanner_df["Status"] == "HOLD").sum()
)

exit_status_count = int(
    (scanner_df["Status"] == "EXIT").sum()
)


c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Total ETFs",
    len(scanner_df)
)

c2.metric(
    "🟢 New BUY",
    buy_count
)

c3.metric(
    "🟡 HOLD",
    hold_count
)

c4.metric(
    "🔴 EXIT",
    exit_status_count
)


# ============================================================
# NEW BUY SECTION
# ============================================================

st.subheader("🟢 Today's BUY Signals")

buy_df = scanner_df[
    scanner_df["Signal"] == "BUY"
].copy()

if buy_df.empty:

    st.info(
        "Aaj koi naya BUY signal nahi hai."
    )

else:

    st.dataframe(
        buy_df[
            [
                "ETF",
                "LTP",
                "Daily Close",
                "RSI(9)",
                "EMA(3)",
                "WMA(21)",
                "RSI > WMA",
                "EMA > WMA",
                "Signal"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# EXIT SECTION
# ============================================================

st.subheader("🔴 Today's EXIT Signals")

exit_df = scanner_df[
    scanner_df["Signal"] == "EXIT"
].copy()

if exit_df.empty:

    st.info(
        "Aaj koi naya EXIT signal nahi hai."
    )

else:

    st.dataframe(
        exit_df[
            [
                "ETF",
                "LTP",
                "Daily Close",
                "RSI(9)",
                "EMA(3)",
                "WMA(21)",
                "RSI > WMA",
                "EMA > WMA",
                "Signal"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# CURRENT HOLD
# ============================================================

st.subheader("🟡 Currently HOLD")

hold_df = scanner_df[
    scanner_df["Status"] == "HOLD"
].copy()

if hold_df.empty:

    st.info(
        "Currently koi ETF HOLD condition mein nahi hai."
    )

else:

    st.dataframe(
        hold_df[
            [
                "ETF",
                "LTP",
                "Daily Close",
                "RSI(9)",
                "EMA(3)",
                "WMA(21)",
                "RSI > WMA",
                "EMA > WMA",
                "Status",
                "Last Signal",
                "Last Signal Date"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# ALL ETF SCANNER
# ============================================================

st.subheader("📋 All ETFs")

display_df = scanner_df.copy()

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# ETF DETAIL
# ============================================================

st.divider()

st.subheader("🔎 ETF Detail")

selected_symbol = st.selectbox(
    "Select ETF",
    ETF_LIST
)


if selected_symbol in processed_data:

    df = processed_data[selected_symbol].copy()

    # --------------------------------------------------------
    # Latest values
    # --------------------------------------------------------

    latest = df.iloc[-1]

    rsi = latest["RSI"]
    ema = latest["EMA"]
    wma = latest["WMA"]

    bullish = bool(latest["Bullish"])

    if bullish:
        detail_status = "🟢 HOLD / BULLISH"
    else:
        detail_status = "🔴 EXIT / NOT BULLISH"

    st.markdown(
        f"### {selected_symbol} — {detail_status}"
    )

    d1, d2, d3, d4 = st.columns(4)

    d1.metric(
        "LTP",
        (
            f"₹{current_prices.get(selected_symbol, np.nan):.2f}"
            if pd.notna(
                current_prices.get(
                    selected_symbol,
                    np.nan
                )
            )
            else "N/A"
        )
    )

    d2.metric(
        "RSI(9)",
        f"{rsi:.2f}"
        if pd.notna(rsi)
        else "N/A"
    )

    d3.metric(
        "EMA(3)",
        f"{ema:.2f}"
        if pd.notna(ema)
        else "N/A"
    )

    d4.metric(
        "WMA(21)",
        f"{wma:.2f}"
        if pd.notna(wma)
        else "N/A"
    )

    # --------------------------------------------------------
    # Conditions
    # --------------------------------------------------------

    st.markdown("### Conditions")

    cond1, cond2 = st.columns(2)

    if pd.notna(rsi) and pd.notna(wma):

        if rsi > wma:
            cond1.success(
                f"✅ RSI(9) > WMA(21)  |  "
                f"{rsi:.2f} > {wma:.2f}"
            )
        else:
            cond1.error(
                f"❌ RSI(9) <= WMA(21)  |  "
                f"{rsi:.2f} <= {wma:.2f}"
            )

    if pd.notna(ema) and pd.notna(wma):

        if ema > wma:
            cond2.success(
                f"✅ EMA(3) > WMA(21)  |  "
                f"{ema:.2f} > {wma:.2f}"
            )
        else:
            cond2.error(
                f"❌ EMA(3) <= WMA(21)  |  "
                f"{ema:.2f} <= {wma:.2f}"
            )

    # --------------------------------------------------------
    # PRICE CHART
    # --------------------------------------------------------

    st.markdown("### Daily Price")

    price_fig = go.Figure()

    price_fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price"
        )
    )

    # BUY markers

    buy_points = df[df["BUY"]]

    if not buy_points.empty:

        price_fig.add_trace(
            go.Scatter(
                x=buy_points.index,
                y=buy_points["Low"] * 0.995,
                mode="markers",
                name="BUY",
                marker=dict(
                    symbol="triangle-up",
                    size=12
                )
            )
        )

    # EXIT markers

    exit_points = df[df["EXIT"]]

    if not exit_points.empty:

        price_fig.add_trace(
            go.Scatter(
                x=exit_points.index,
                y=exit_points["High"] * 1.005,
                mode="markers",
                name="EXIT",
                marker=dict(
                    symbol="triangle-down",
                    size=12
                )
            )
        )

    price_fig.update_layout(
        height=500,
        xaxis_rangeslider_visible=False,
        hovermode="x unified"
    )

    st.plotly_chart(
        price_fig,
        use_container_width=True
    )

    # --------------------------------------------------------
    # HILEGA-MILEGA CHART
    # --------------------------------------------------------

    st.markdown(
        "### Hilega-Milega Indicator"
    )

    indicator_fig = go.Figure()

    # 60

    indicator_fig.add_trace(
        go.Scatter(
            x=df.index,
            y=[OVERBOUGHT] * len(df),
            mode="lines",
            name="60"
        )
    )

    # 50

    indicator_fig.add_trace(
        go.Scatter(
            x=df.index,
            y=[50] * len(df),
            mode="lines",
            name="50"
        )
    )

    # 40

    indicator_fig.add_trace(
        go.Scatter(
            x=df.index,
            y=[OVERSOLD] * len(df),
            mode="lines",
            name="40"
        )
    )

    # RSI

    indicator_fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["RSI"],
            mode="lines",
            name="RSI(9)"
        )
    )

    # EMA

    indicator_fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["EMA"],
            mode="lines",
            name="EMA(3)"
        )
    )

    # WMA

    indicator_fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["WMA"],
            mode="lines",
            name="WMA(21)"
        )
    )

    # BUY markers

    if not buy_points.empty:

        indicator_fig.add_trace(
            go.Scatter(
                x=buy_points.index,
                y=buy_points["WMA"],
                mode="markers",
                name="BUY",
                marker=dict(
                    symbol="triangle-up",
                    size=12
                )
            )
        )

    # EXIT markers

    if not exit_points.empty:

        indicator_fig.add_trace(
            go.Scatter(
                x=exit_points.index,
                y=exit_points["WMA"],
                mode="markers",
                name="EXIT",
                marker=dict(
                    symbol="triangle-down",
                    size=12
                )
            )
        )

    indicator_fig.update_layout(
        height=500,
        yaxis=dict(
            range=[0, 100],
            title="RSI"
        ),
        hovermode="x unified"
    )

    st.plotly_chart(
        indicator_fig,
        use_container_width=True
    )

    # --------------------------------------------------------
    # RECENT SIGNALS
    # --------------------------------------------------------

    st.markdown("### Recent BUY / EXIT Signals")

    signal_df = df[
        df["BUY"] | df["EXIT"]
    ].copy()

    if signal_df.empty:

        st.info(
            "No BUY/EXIT signals found in 6 months."
        )

    else:

        signal_display = pd.DataFrame({

            "Date": signal_df.index.strftime(
                "%Y-%m-%d"
            ),

            "Signal": np.where(
                signal_df["BUY"],
                "BUY",
                "EXIT"
            ),

            "Close": signal_df["Close"].round(2),

            "RSI(9)": signal_df["RSI"].round(2),

            "EMA(3)": signal_df["EMA"].round(2),

            "WMA(21)": signal_df["WMA"].round(2)

        })

        signal_display = signal_display.iloc[::-1]

        st.dataframe(
            signal_display.head(20),
            use_container_width=True,
            hide_index=True
        )

else:

    st.error(
        f"{selected_symbol} ka data available nahi hai."
    )


# ============================================================
# LOGIC EXPLANATION
# ============================================================

st.divider()

st.markdown("### 📌 Trading Logic")

st.markdown(
    """
**BUY**

- RSI(9) > WMA(21)
- AND EMA(3) > WMA(21)
- Dono condition FALSE → TRUE hone par **sirf ek BUY**

**HOLD**

- RSI(9) > WMA(21)
- AND EMA(3) > WMA(21)
- Condition true rehne tak **HOLD**

**EXIT**

- RSI(9) <= WMA(21)
- OR EMA(3) <= WMA(21)
- Condition TRUE → FALSE hone par **sirf ek EXIT**

**Historical data:** 6 months daily candles  
**Current LTP:** Yahoo Finance latest intraday price  
**Auto refresh:** OFF
"""
)
