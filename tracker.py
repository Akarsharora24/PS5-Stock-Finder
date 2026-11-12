import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, unquote

import requests

PRODUCT_URL = "https://www.zepto.com/pn/sony-ps5-console-fortnite-flowering-chaos-bundle/pvid/4b6849ad-2d7c-46af-8e34-c42ea585ffe8"
PVID = "4b6849ad-2d7c-46af-8e34-c42ea585ffe8"
TARGET_PRICE = 49999
STATE_FILE = Path("last_status.json")
WEB = "https://www.zepto.com"
BFF = "https://bff-gateway.zepto.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

# These are initial city-centre probes, NOT every Zepto store or every PIN code.
# Add more coordinates later as needed. Each probe resolves the Zepto store
# serving that coordinate and checks the product in that store.
LOCATIONS = [
    ("Delhi", 28.6139, 77.2090),
    ("Mumbai", 19.0760, 72.8777),
    ("Bengaluru", 12.9716, 77.5946),
    ("Hyderabad", 17.3850, 78.4867),
    ("Chennai", 13.0827, 80.2707),
    ("Kolkata", 22.5726, 88.3639),
    ("Pune", 18.5204, 73.8567),
    ("Ahmedabad", 23.0225, 72.5714),
    ("Jaipur", 26.9124, 75.7873),
    ("Lucknow", 26.8467, 80.9462),
    ("Gurugram", 28.4595, 77.0266),
    ("Noida", 28.5355, 77.3910),
    ("Chandigarh", 30.7333, 76.7794),
    ("Indore", 22.7196, 75.8577),
    ("Bhopal", 23.2599, 77.4126),
    ("Surat", 21.1702, 72.8311),
    ("Vadodara", 22.3072, 73.1812),
    ("Nagpur", 21.1458, 79.0882),
    ("Kochi", 9.9312, 76.2673),
    ("Coimbatore", 11.0168, 76.9558),
]

def telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram secrets are missing; cannot send notification.")
        return
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=20,
    )
    r.raise_for_status()
    print("Telegram notification sent.")

def parse_serviceability(set_cookies):
    for cookie in set_cookies:
        if cookie.startswith("serviceability="):
            raw = cookie.split(";", 1)[0].split("=", 1)[1]
            data = json.loads(unquote(raw))
            primary = data.get("primaryStore") or {}
            detail = data.get("storeDetailedInfo") or {}
            if primary.get("serviceable") and primary.get("storeId"):
                return {
                    "store_id": primary["storeId"],
                    "store_name": detail.get("name") or "",
                    "city": detail.get("city") or "",
                    "eta": primary.get("etaInMinutes"),
                }
            return None
    return None

def check_location(session, label, lat, lon):
    position = quote(json.dumps({"latitude": lat, "longitude": lon}, separators=(",", ":")), safe="")
    r = session.head(
        WEB + "/",
        headers={**HEADERS, "Accept": "text/html", "Cookie": f"user_position={position}"},
        timeout=25,
        allow_redirects=True,
    )
    r.raise_for_status()
    store = parse_serviceability(r.raw.headers.getlist("Set-Cookie"))
    if not store:
        return {"location": label, "status": "not_serviceable"}
    store_id = store["store_id"]
    h = {
        **HEADERS,
        "Accept": "application/json",
        "platform": "WEB",
        "tenant": "ZEPTO",
        "x-without-bearer": "true",
        "app_version": "16.2.11",
        "Origin": WEB,
        "Referer": WEB + "/",
        "storeId": store_id,
    }
    xsrf = session.cookies.get("XSRF-TOKEN")
    if xsrf:
        h["x-xsrf-token"] = unquote(xsrf)
    p = session.get(
        f"{BFF}/product-assortment-service/api/v2/product-detail",
        params={"storeId": store_id, "productVariantId": PVID},
        headers=h,
        timeout=25,
    )
    if p.status_code in (400, 404):
        return {"location": label, "status": "not_carried", "store": store.get("store_name")}
    p.raise_for_status()
    data = p.json()
    if (data.get("fallbackType") or "NONE") != "NONE":
        return {"location": label, "status": "not_carried", "store": store.get("store_name")}
    product = data.get("product") or {}
    items = product.get("storeProducts") or []
    if not items:
        return {"location": label, "status": "not_carried", "store": store.get("store_name")}
    item = items[0]
    price_paise = item.get("discountedSellingPrice") or item.get("superSaverSellingPrice")
    price = round(price_paise / 100, 2) if price_paise else None
    return {
        "location": label,
        "status": "in_stock" if not item.get("outOfStock") else "out_of_stock",
        "price": price,
        "mrp": round(item["mrp"] / 100, 2) if item.get("mrp") else None,
        "store": store.get("store_name"),
        "eta": store.get("eta"),
    }

def main():
    session = requests.Session()
    session.headers.update(HEADERS)
    home = session.get(WEB + "/", timeout=30)
    home.raise_for_status()
    results = []
    for label, lat, lon in LOCATIONS:
        try:
            result = check_location(session, label, lat, lon)
            print(json.dumps(result, ensure_ascii=False))
            results.append(result)
        except Exception as exc:
            print(f"{label}: ERROR: {type(exc).__name__}: {exc}")
            results.append({"location": label, "status": "error", "error": str(exc)})
        time.sleep(1.5)

    previous = {}
    if STATE_FILE.exists():
        try:
            previous = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    current = {x["location"]: x for x in results}
    alerts = []
    for name, result in current.items():
        old = previous.get(name, {})
        if result.get("status") == "in_stock":
            price = result.get("price")
            if old.get("status") != "in_stock" or old.get("price") != price:
                alerts.append(f"ð¢ PS5 IN STOCK: {name}\nPrice: â¹{price if price is not None else 'not shown'}\nStore: {result.get('store') or 'not shown'}")
            if price is not None and price <= TARGET_PRICE:
                alerts.append(f"ð¯ TARGET PRICE MET: {name}\nPrice: â¹{price}\n{PRODUCT_URL}")
        elif result.get("status") == "out_of_stock" and old.get("status") == "in_stock":
            alerts.append(f"ð´ PS5 went out of stock: {name}")

    STATE_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    if alerts:
        telegram("\n\n".join(alerts))
    elif not os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("No Telegram token configured.")
    print(f"Finished: {len(results)} city probes. This is not an exhaustive nationwide store sweep.")

if __name__ == "__main__":
    main()
