"""
SeedMediaa Lead Scraper — OpenStreetMap / Overpass API Edition
No API key. No billing. No card required. 100% free.

Pulls businesses in Durban and Johannesburg from OpenStreetMap data via the
public Overpass API, across a configurable list of industries, and writes
them to a CSV in leads_output/ ready to import into your Google Sheet.

Usage:
    python seedmediaa_scraper.py --city durban --all --limit 30
    python seedmediaa_scraper.py --city johannesburg --all --limit 30
    python seedmediaa_scraper.py --city both --all --limit 30
"""

import argparse
import csv
import os
import time
import sys
from datetime import datetime

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bounding boxes (south, west, north, east) — roughly covers each metro area
CITY_BBOX = {
    "durban": (-29.95, 30.85, -29.65, 31.10),
    "johannesburg": (-26.35, 27.85, -26.00, 28.20),
}

# OSM tags that map to the kinds of SMB/industry targets you're after.
# Each entry: (osm_key, osm_value, friendly_industry_label)
INDUSTRIES = [
    ("office", "company", "General Business"),
    ("office", "lawyer", "Legal"),
    ("office", "estate_agent", "Real Estate"),
    ("office", "accountant", "Accounting"),
    ("office", "insurance", "Insurance"),
    ("office", "it", "IT / Tech"),
    ("office", "advertising_agency", "Marketing / Advertising"),
    ("shop", "car", "Automotive"),
    ("shop", "furniture", "Furniture / Retail"),
    ("craft", "builder", "Construction"),
    ("amenity", "dentist", "Dental"),
    ("amenity", "clinic", "Medical / Clinic"),
    ("amenity", "veterinary", "Veterinary"),
    ("amenity", "restaurant", "Hospitality / Restaurant"),
    ("tourism", "hotel", "Hospitality / Hotel"),
]

HEADERS = {"User-Agent": "SeedMediaaLeadScraper/1.0 (contact: seedmediaa.co.za)"}


def build_query(bbox, osm_key, osm_value, limit):
    south, west, north, east = bbox
    return f"""
    [out:json][timeout:60];
    (
      node["{osm_key}"="{osm_value}"]({south},{west},{north},{east});
      way["{osm_key}"="{osm_value}"]({south},{west},{north},{east});
    );
    out center {limit};
    """


def fetch_industry(city, bbox, osm_key, osm_value, label, limit):
    query = build_query(bbox, osm_key, osm_value, limit)
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=90)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [!] {label} in {city}: request failed ({e}) — skipping")
        return []

    try:
        elements = resp.json().get("elements", [])
    except ValueError:
        print(f"  [!] {label} in {city}: bad response — skipping")
        return []

    rows = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue  # skip unnamed entries, no point emailing "Unnamed Business"

        website = tags.get("website") or tags.get("contact:website", "")
        phone = tags.get("phone") or tags.get("contact:phone", "")
        email = tags.get("email") or tags.get("contact:email", "")

        addr_parts = [
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
            tags.get("addr:suburb", "") or tags.get("addr:city", ""),
        ]
        address = " ".join(p for p in addr_parts if p).strip()

        rows.append({
            "Company Name": name,
            "Industry": label,
            "City": city.title(),
            "Address": address,
            "Website": website,
            "Phone": phone,
            "Email": email,  # usually blank — OSM rarely has emails; fill via Hunter.io
            "CEO/Owner Name": "",  # fill manually via LinkedIn/website, as before
            "Status": "New",
            "Source": "OpenStreetMap",
        })

    print(f"  [OK] {label} in {city}: {len(rows)} businesses found")
    return rows


def scrape_city(city, limit, industries):
    bbox = CITY_BBOX[city]
    all_rows = []
    print(f"\nScraping {city.title()} ({len(industries)} industries)...")
    for osm_key, osm_value, label in industries:
        rows = fetch_industry(city, bbox, osm_key, osm_value, label, limit)
        all_rows.extend(rows)
        time.sleep(2)  # be polite to the free public Overpass server
    return all_rows


def dedupe(rows):
    seen = set()
    out = []
    for r in rows:
        key = (r["Company Name"].strip().lower(), r["City"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def write_csv(rows, out_dir="leads_output"):
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"seedmediaa_leads_{timestamp}.csv")

    fieldnames = ["Company Name", "Industry", "City", "Address", "Website",
                  "Phone", "Email", "CEO/Owner Name", "Status", "Source"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} leads -> {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="SeedMediaa free lead scraper (OpenStreetMap)")
    parser.add_argument("--city", choices=["durban", "johannesburg", "both"], default="both")
    parser.add_argument("--limit", type=int, default=30, help="Max results per industry per city")
    parser.add_argument("--all", action="store_true", help="Scrape all built-in industries")
    args = parser.parse_args()

    industries = INDUSTRIES  # --all is the only mode for now; kept flag for compatibility

    cities = ["durban", "johannesburg"] if args.city == "both" else [args.city]

    all_rows = []
    for city in cities:
        all_rows.extend(scrape_city(city, args.limit, industries))

    all_rows = dedupe(all_rows)

    if not all_rows:
        print("\nNo leads found. Overpass may be rate-limiting — try again in a few minutes.")
        sys.exit(0)

    write_csv(all_rows)


if __name__ == "__main__":
    main()
