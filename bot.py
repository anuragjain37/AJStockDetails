import os
import json
import requests
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import MACD

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

OFFSET_FILE = "offset.txt"
COOLDOWN_FILE = "cooldown.json"
COOLDOWN_MINUTES = 60

# ========================
# Telegram helpers
# ========================
def send_message(text):
    requests.post(
        f"{API_URL}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text}
    )

def send_photo(path):
    with open(path, "rb") as f:
        requests.post(
            f"{API_URL}/sendPhoto",
            files={"photo": f},
            data={"chat_id": CHAT_ID}
        )

def get_updates(offset=None):
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    return requests.get(f"{API_URL}/getUpdates", params=params).json()

# ========================
# Cooldown logic
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
# Finance helpers
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
    if df.empty:
        return None

    rsi = RSIIndicator(df["Close"]).rsi().iloc[-1]
    macd = MACD(df["Close"])
    macd_val = macd.macd().iloc[-1]
    signal = macd.macd_signal().iloc[-1]

    return {
        "RSI": f"{rsi:.2f}",
        "MACD": f"{macd_val:.4f}",
        "Signal": f"{signal:.4f}",
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
# Command handlers
# ========================
def handle_symbol(symbol):
    if in_cooldown(symbol):
        send_message(f"⏳ {symbol} queried recently. Please wait.")
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

    send_message(msg)

    chart = plot_1m(symbol)
    if chart:
        send_photo(chart)

    update_cooldown(symbol)

def handle_compare(sym1, sym2):
    f1 = get_fundamentals(sym1)
    f2 = get_fundamentals(sym2)

    msg = f"📊 COMPARE\n\n{sym1} vs {sym2}\n\n"
    for k in f1:
        msg += f"{k}: {f1[k]} | {f2[k]}\n"

    send_message(msg)

# ========================
# Main loop
# ========================
def main():
    offset = None
    if os.path.exists(OFFSET_FILE):
        offset = int(open(OFFSET_FILE).read().strip())

    updates = get_updates(offset)

    for update in updates.get("result", []):
        offset = update["update_id"] + 1
        msg = update.get("message", {}).get("text", "").strip()

        if not msg:
            continue

        msg = msg.upper()

        if msg == "/HELP":
            send_message(
                "/price AAPL\n"
                "/tech AAPL\n"
                "/compare AAPL MSFT\n"
                "or just send: AAPL"
            )

        elif msg.startswith("/PRICE") or msg.startswith("/TECH"):
            symbol = msg.split()[-1]
            handle_symbol(symbol)

        elif msg.startswith("/COMPARE"):
            _, s1, s2 = msg.split()
            handle_compare(s1, s2)

        else:
            handle_symbol(msg)

    if offset:
        with open(OFFSET_FILE, "w") as f:
            f.write(str(offset))

if __name__ == "__main__":
    main()
