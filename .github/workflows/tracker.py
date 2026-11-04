import json
import os
import re
import sys
from html import unescape
from urllib.request import Request, urlopen

URL = "https://www.zepto.com/pn/sony-ps5-console-fortnite-flowering-chaos-bundle/pvid/4b6849ad-2d7c-46af-8e34-c42ea585ffe8"
TARGET = 49999
PINCODE = os.getenv("DELIVERY_PINCODE", "335001")

def fetch():
    req = Request(URL, headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    })
    with urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", "replace")

def walk_json(obj, found):
    if isinstance(obj, dict):
        typ = obj.get("@type")
        if typ == "Product" or (isinstance(typ, list) and "Product" in typ):
            offers = obj.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = offers.get("price") or offers.get("lowPrice")
            availability = offers.get("availability", "")
            if price:
                try:
                    found["price"] = float(str(price).replace(",", ""))
                except ValueError:
                    pass
            if availability:
                found["availability"] = str(availability)
            if obj.get("name"):
                found["name"] = obj["name"]
        for v in obj.values():
            walk_json(v, found)
    elif isinstance(obj, list):
        for v in obj:
            walk_json(v, found)

def main():
    print("Checking Zepto PS5 listing")
    print("Delivery PIN:", PINCODE)

    try:
        html = fetch()
    except Exception as e:
        print("RESULT=UNKNOWN")
        print("Could not fetch Zepto page:", repr(e))
        sys.exit(0)

    found = {}
    pattern = r"<script[^>]+type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>"

    for match in re.findall(pattern, html, re.I | re.S):
        try:
            walk_json(json.loads(unescape(match)), found)
        except Exception:
            pass

    if "price" not in found:
        page_text = unescape(re.sub(r"<[^>]+>", " ", html))
        candidates = re.findall(r'(?:₹|Rs\.?\s*)([0-9][0-9,]{3,})', page_text, re.I)
        for candidate in candidates:
            try:
                value = float(candidate.replace(",", ""))
                if 10000 <= value <= 150000:
                    found["price"] = value
                    break
            except ValueError:
                pass

    print("Product:", found.get("name", "Sony PS5 Fortnite Flowering Chaos Bundle"))
    print("Price:", found.get("price", "UNKNOWN"))
    print("Availability metadata:", found.get("availability", "UNKNOWN"))

    if "price" in found and found["price"] <= TARGET:
        print("TARGET_PRICE_REACHED=YES")
    else:
        print("TARGET_PRICE_REACHED=NO_OR_UNKNOWN")

    availability = str(found.get("availability", "")).lower()

    if "instock" in availability:
        print("STOCK=IN_STOCK")
    elif "outofstock" in availability or "soldout" in availability:
        print("STOCK=OUT_OF_STOCK")
    else:
        print("STOCK=UNKNOWN")

if __name__ == "__main__":
    main()
