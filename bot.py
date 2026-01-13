import os
import requests
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from flask import Flask, request
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import MACD

# ========================
# CONFIG
# ========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

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

    rsi = RSIIndicator(close).rsi().iloc[-1]
    macd = MACD(close)
    macd_val = macd.macd().iloc[-1]
    signal_val = macd.macd_signal().iloc[-1]

    return {
        "RSI": f"{rsi:.2f}",
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
# COMMAND HANDLERS
# ========================
def handle_symbol(chat_id, symbol):
    symbol = symbol.upper()

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

def handle_compare(chat_id, s1, s2):
    f1 = get_fundamentals(s1)
    f2 = get_fundamentals(s2)

    msg = f"📊 COMPARE\n\n{s1} vs {s2}\n\n"
    for k in f1:
        msg += f"{k}: {f1[k]} | {f2[k]}\n"

    send_message(chat_id, msg)

# ========================
# TELEGRAM WEBHOOK
# ========================
@app.route("/", methods=["POST"])
def telegram_webhook():
    data = request.json
    message = data.get("message", {})
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if not chat_id or not text:
        return "ok"

    text = text.strip().upper()

    if text == "/HELP":
        send_message(
            chat_id,
            "Commands:\n"
            "/price AAPL\n"
            "/tech TSLA\n"
            "/compare AAPL MSFT\n"
            "or just send: AAPL"
        )

    elif text.startswith("/COMPARE"):
        parts = text.split()
        if len(parts) == 3:
            handle_compare(chat_id, parts[1], parts[2])
        else:
            send_message(chat_id, "Usage: /compare AAPL MSFT")

    elif text.startswith("/PRICE") or text.startswith("/TECH"):
        parts = text.split()
        if len(parts) == 2:
            handle_symbol(chat_id, parts[1])
        else:
            send_message(chat_id, "Usage: /price AAPL")

    else:
        handle_symbol(chat_id, text)

    return "ok"

# ========================
# START SERVER
# ========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

