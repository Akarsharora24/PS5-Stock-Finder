import os
import re
import json
import hashlib
import requests

PRODUCT_URL = (
    "https://www.zepto.com/pn/sony-ps5-console-fortnite-flowering-chaos-bundle/"
    "pvid/4b6849ad-2d7c-46af-8e34-c42ea585ffe8"
)

TARGET_PRICE = 49999

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

STATE_FILE = "last_status.txt"


def telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": message},
        timeout=20
    ).raise_for_status()


def check_zepto():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1"
        )
    }

    response = requests.get(
        PRODUCT_URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()
    html = response.text

    prices = []

    for pattern in [
        r'"price"\s*:\s*"?(\d+(?:\.\d{1,2})?)"?',
        r'"sellingPrice"\s*:\s*"?(\d+(?:\.\d{1,2})?)"?'
    ]:
        prices.extend(
            float(x) for x in re.findall(pattern, html, re.I)
        )

    prices = [p for p in prices if 1000 <= p <= 200000]

    price = min(prices) if prices else None

    in_stock = bool(
        re.search(r'"availability"\s*:\s*"[^"]*InStock', html, re.I)
        or re.search(r'"isAvailable"\s*:\s*true', html, re.I)
    )

    out_of_stock = bool(
        re.search(r'"availability"\s*:\s*"[^"]*OutOfStock', html, re.I)
        or re.search(r'"isAvailable"\s*:\s*false', html, re.I)
    )

    if in_stock:
        status = "IN STOCK"
    elif out_of_stock:
        status = "OUT OF STOCK"
    else:
        status = "UNKNOWN"

    print("Price:", price)
    print("Stock:", status)

    if status == "UNKNOWN":
        print("Zepto did not expose reliable stock information.")
        return

    current = f"{status}|{price}"

    previous = ""

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            previous = f.read().strip()

    if current != previous:
        message = (
            "🎮 PS5 STOCK UPDATE\n\n"
            f"Status: {status}\n"
            f"Price: ₹{price if price else 'Not detected'}\n"
            f"Target: ₹{TARGET_PRICE:,}\n\n"
            f"Product: {PRODUCT_URL}"
        )

        if status == "IN STOCK" and price and price <= TARGET_PRICE:
            message = "🔥 PS5 AVAILABLE AT TARGET PRICE!\n\n" + message

        telegram(message)

        with open(STATE_FILE, "w") as f:
            f.write(current)


if __name__ == "__main__":
    check_zepto()
