import os
import json
import requests
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import MACD

# ========================
# CONFIG
# ========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

OFFSET_FILE = "offset.txt"
COOLDOWN_FILE = "cooldown.json"
COOLDOWN_MINUTES = 60

# ========================
# TELEGRAM HELPERS
# ========================
def send_message(chat_id, text):
    requests.post(
        f"{API_URL}/sendMessage",
        data={"chat_id": chat_id, "text": text}
    )

def send_photo(chat_id, path):
    with open(path, "rb") as f:
        requests.post(
            f"{API_URL}/sendPhoto",
            files={"photo": f},
            data={"chat_id": chat_id}
        )

def get_updates(offset=None):
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    return requests.get(f"{API_URL}/getUpdates", params=params).json()

# ========================
# COOLDOWN LOGIC
# ========================
def load_cooldown():
    if os.path.exists(COOLDOWN_FILE):
        with open(COOLDOWN_FILE) as f:
            return json.load(f)
    return {}

def save_cooldown(data):
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(data, f)

def in_cooldown(symbol):
    cd = load_cooldown()
    if symbol in cd:
        last = datetime.fromisoformat(cd[symbol])
        return datetime.utcnow() - last < timedelta(minutes=COOLDOWN_MINUTES)
    return False

def update_cooldown(symbol):
    cd = load_cooldown()
    cd[symbol] = datetime.utcnow().isoformat()
    save_cooldown(cd)

# ========================
# FINANCE HELPERS
# ========================
def bn(x):
    return f"{x/1e9:.2f}" if isinstance(x, (int, float)) else "N/A"

def get_fundamentals(symbol):
    info = yf.Ticker(symbol).info
    return {
        "Price": info.get("regularMarketPrice"),
        "Day Low": info.get("dayLow"),
        "Day High": info.get("dayHigh"),
        "Last Close": info.get("previousClose"),
        "Market Cap (USD bn)": bn(info.get("marketCap")),
        "EBITDA (USD bn)": bn(info.get("ebitda")),
        "PE": info.get("trailingPE"),
        "PEG": info.get("pegRatio"),
        "Dividend Yield (%)": (
            f"{info.get('dividendYield')*100:.2f}"
            if info.get("dividendYield") else "N/A"
        ),
    }

def get_technicals(symbol):
    df = yf.download(symbol, period="3mo", progress=False)

    if df.empty or "Close" not in df:
        return None

    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = close.dropna()
    if len(close) < 30:
        return None

    rsi_val = RSIIndicator(close).rsi().iloc[-1]

    macd = MACD(close)
    macd_val = macd.macd().iloc[-1]
    signal_val = macd.macd_signal().iloc[-1]

    return {
        "RSI": f"{rsi_val:.2f}",
        "MACD": f"{macd_val:.4f}",
        "Signal": f"{signal_val:.4f}",
    }

def plot_1m(symbol):
    df = yf.download(symbol, period="1mo", progress=False)
    if df.empty:
        return None

    plt.figure(figsize=(8, 4))
    plt.plot(df.index, df["Close"])
    plt.title(f"{symbol} – Last 1 Month")
    plt.grid(True)

    path = f"{symbol}_1m.png"
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path

# ========================
# HANDLERS
# ========================
def handle_symbol(chat_id, symbol):
    symbol = symbol.upper()

    if in_cooldown(symbol):
        send_message(chat_id, f"⏳ {symbol} was queried recently. Try later.")
        return

    fundamentals = get_fundamentals(symbol)
    technicals = get_technicals(symbol)

    msg = f"📊 {symbol}\n\n"
    for k, v in fundamentals.items():
        msg += f"{k}: {v}\n"

    if technicals:
        msg += "\n📈 Technicals\n"
        for k, v in technicals.items():
            msg += f"{k}: {v}\n"

    send_message(chat_id, msg)

    chart = plot_1m(symbol)
    if chart:
        send_photo(chat_id, chart)

    update_cooldown(symbol)

def handle_compare(chat_id, s1, s2):
    f1 = get_fundamentals(s1)
    f2 = get_fundamentals(s2)

    msg = f"📊 COMPARE\n\n{s1} vs {s2}\n\n"
    for k in f1:
        msg += f"{k}: {f1[k]} | {f2[k]}\n"

    send_message(chat_id, msg)

# ====================
