"""
SeedMediaa Lead Scraper — OpenStreetMap / Overpass API Edition
No API key. No billing. No card required. 100% free.

Pulls businesses in Durban and Johannesburg from OpenStreetMap data via the
public Overpass API, across a configurable list of industries, then visits
each business's website (when listed) to try to find a public contact email,
and writes everything to a CSV in leads_output/ ready to import into your
Google Sheet.

Usage:
    python seedmediaa_scraper.py --city durban --all --limit 50
    python seedmediaa_scraper.py --city johannesburg --all --limit 50
    python seedmediaa_scraper.py --city both --all --limit 50
    python seedmediaa_scraper.py --city both --all --limit 50 --no-email-lookup

Email Status column values:
    "Found on listing" — OSM itself had the email tagged directly
    "Found on site"     — found by crawling the business's own website
    "Guessed - Verify"  — no email found; guessed info@domain as a fallback,
                          NOT verified, always sanity-check before sending
"""

import argparse
import csv
import os
import re
import time
import sys
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Generic addresses we deprioritize but still keep as a fallback — a real
# named contact is better, but info@ is still usable for outreach.
GENERIC_PREFIXES = ("noreply", "no-reply", "donotreply", "webmaster",
                     "postmaster", "example", "test", "sales@wixpress",
                     "yourname", "name@")

# Pages likely to list a contact email, tried in order after the homepage.
CONTACT_PATHS = ("/contact", "/contact-us", "/contactus", "/about",
                  "/about-us", "/get-in-touch")

EMAIL_LOOKUP_TIMEOUT = 8
EMAIL_LOOKUP_DELAY = 1.5  # be polite between site visits

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
    ("office", "consulting", "Consulting"),
    ("office", "financial", "Financial Services"),
    ("office", "architect", "Architecture"),
    ("office", "employment_agency", "Recruitment / HR"),
    ("shop", "car", "Automotive"),
    ("shop", "car_repair", "Automotive / Repair"),
    ("shop", "furniture", "Furniture / Retail"),
    ("shop", "clothes", "Retail / Fashion"),
    ("shop", "electronics", "Retail / Electronics"),
    ("shop", "supermarket", "Retail / Grocery"),
    ("shop", "hardware", "Retail / Hardware"),
    ("craft", "builder", "Construction"),
    ("craft", "electrician", "Construction / Electrical"),
    ("craft", "plumber", "Construction / Plumbing"),
    ("amenity", "dentist", "Dental"),
    ("amenity", "clinic", "Medical / Clinic"),
    ("amenity", "pharmacy", "Medical / Pharmacy"),
    ("amenity", "veterinary", "Veterinary"),
    ("amenity", "restaurant", "Hospitality / Restaurant"),
    ("amenity", "cafe", "Hospitality / Cafe"),
    ("amenity", "college", "Education"),
    ("amenity", "driving_school", "Education / Driving School"),
    ("tourism", "hotel", "Hospitality / Hotel"),
    ("tourism", "guest_house", "Hospitality / Guest House"),
]

HEADERS = {"User-Agent": "SeedMediaaLeadScraper/1.0 (contact: seedmediaa.co.za)"}


def build_combined_query(bbox, industries, limit_per_industry):
    """
    Build ONE Overpass query covering every industry for a city, instead of
    firing one request per industry. This is dramatically more reliable —
    the free public Overpass server rate-limits/rejects (406) clients that
    fire many requests in quick succession, which is what a per-industry
    loop does with 30+ industries.
    """
    south, west, north, east = bbox
    clauses = []
    for osm_key, osm_value, _label in industries:
        clauses.append(f'  node["{osm_key}"="{osm_value}"]({south},{west},{north},{east});')
        clauses.append(f'  way["{osm_key}"="{osm_value}"]({south},{west},{north},{east});')

    body = "\n".join(clauses)
    # out center with no hard cap here — we cap per-industry in Python after
    # grouping results by which tag matched, so one big union query still
    # respects --limit per industry.
    return f"""
    [out:json][timeout:180];
    (
{body}
    );
    out center;
    """


def classify_industry(tags, industries):
    """Given an element's tags, find which (osm_key, osm_value) it matched
    and return the friendly label. Checks in the same order as INDUSTRIES
    so the first match wins if a place has multiple matching tags."""
    for osm_key, osm_value, label in industries:
        if tags.get(osm_key) == osm_value:
            return label
    return "Other"


def fetch_city_combined(city, bbox, industries, limit_per_industry, max_retries=4):
    """Fetch all industries for a city in one Overpass request, with retry/
    backoff on transient errors (406/429/504 are all common on the free
    public instance under load)."""
    query = build_combined_query(bbox, industries, limit_per_industry)

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=185)
            if resp.status_code == 200:
                break
            print(f"  [!] {city}: Overpass returned {resp.status_code} "
                  f"(attempt {attempt}/{max_retries}) — retrying...")
        except requests.RequestException as e:
            print(f"  [!] {city}: request failed ({e}) (attempt {attempt}/{max_retries}) — retrying...")
            resp = None

        if attempt < max_retries:
            time.sleep(15 * attempt)  # backoff: 15s, 30s, 45s...
    else:
        print(f"  [!!] {city}: all {max_retries} attempts failed — skipping this city.")
        return []

    try:
        elements = resp.json().get("elements", [])
    except ValueError:
        print(f"  [!] {city}: bad response body — skipping.")
        return []

    # Group by industry so we can respect limit_per_industry per category
    per_industry_count = {}
    rows = []

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue

        label = classify_industry(tags, industries)
        if label == "Other":
            continue  # shouldn't happen given our query, but just in case

        if per_industry_count.get(label, 0) >= limit_per_industry:
            continue
        per_industry_count[label] = per_industry_count.get(label, 0) + 1

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
            "Email": email,
            "Email Status": "Found on listing" if email else "",
            "CEO/Owner Name": "",
            "Status": "New",
            "Source": "OpenStreetMap",
        })

    print(f"  [OK] {city}: {len(rows)} businesses found across "
          f"{len(per_industry_count)} industries")
    return rows


def is_generic_email(email):
    lower = email.lower()
    return any(lower.startswith(p) for p in GENERIC_PREFIXES)


def extract_emails_from_html(html):
    found = set(EMAIL_REGEX.findall(html))
    # strip obviously-bad matches (image filenames misread as emails, etc.)
    cleaned = {
        e for e in found
        if not e.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"))
    }
    return cleaned


def find_email_on_site(website, session):
    """
    Visit a business's website (and a couple of likely contact pages) and
    look for a public email address. Returns the best email found, or ''.
    Best-effort only — many sites won't have one, and that's fine, this
    just increases the hit rate over scraping alone.
    """
    if not website:
        return ""

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    parsed = urlparse(website)
    if not parsed.netloc:
        return ""

    candidate_urls = [website]
    for path in CONTACT_PATHS:
        candidate_urls.append(urljoin(website, path))

    all_emails = set()
    for url in candidate_urls:
        try:
            resp = session.get(url, headers=HEADERS, timeout=EMAIL_LOOKUP_TIMEOUT)
            if resp.status_code != 200:
                continue
            all_emails |= extract_emails_from_html(resp.text)
        except requests.RequestException:
            continue

        if all_emails:
            # Prefer a non-generic hit as soon as we have one, to save requests
            non_generic = [e for e in all_emails if not is_generic_email(e)]
            if non_generic:
                break

        time.sleep(EMAIL_LOOKUP_DELAY)

    if not all_emails:
        return ""

    non_generic = sorted(e for e in all_emails if not is_generic_email(e))
    if non_generic:
        return non_generic[0]
    return sorted(all_emails)[0]  # fall back to a generic address (e.g. info@)


def guess_email_from_domain(website):
    """
    Last-resort fallback: guess the standard info@domain pattern when no
    real email could be found on the site. This is a GUESS, not a
    verified address — always labeled clearly so it never gets sent to
    blindly. Same technique used by most cheap lead-gen tools.
    """
    if not website:
        return ""

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    parsed = urlparse(website)
    domain = parsed.netloc.replace("www.", "").strip().lower()
    if not domain or "." not in domain:
        return ""

    return f"info@{domain}"


def enrich_with_emails(rows, skip=False):
    if skip:
        return rows

    total = len(rows)
    with_website = [r for r in rows if r.get("Website")]
    print(f"\nLooking up emails on {len(with_website)}/{total} business websites "
          f"(this is the slow part — be patient)...")

    session = requests.Session()
    found_count = 0
    guessed_count = 0

    for i, row in enumerate(rows, 1):
        if row.get("Email"):
            continue  # OSM already had one tagged directly, keep it
        website = row.get("Website")
        if not website:
            continue

        email = find_email_on_site(website, session)
        if email:
            row["Email"] = email
            row["Email Status"] = "Found on site"
            found_count += 1
        else:
            # Fallback: guess the standard info@domain pattern, clearly
            # labeled so it always gets a human glance before sending.
            guess = guess_email_from_domain(website)
            if guess:
                row["Email"] = guess
                row["Email Status"] = "Guessed - Verify"
                guessed_count += 1

        if i % 10 == 0 or i == total:
            print(f"  ...processed {i}/{total} "
                  f"(found: {found_count}, guessed: {guessed_count})")

    print(f"Email lookup done: {found_count} found on-site, "
          f"{guessed_count} guessed from domain pattern (verify before sending).")
    return rows


def scrape_city(city, limit, industries):
    bbox = CITY_BBOX[city]
    print(f"\nScraping {city.title()} ({len(industries)} industries, "
          f"1 combined request)...")
    return fetch_city_combined(city, bbox, industries, limit)


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
                  "Phone", "Email", "Email Status", "CEO/Owner Name", "Status", "Source"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} leads -> {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="SeedMediaa free lead scraper (OpenStreetMap)")
    parser.add_argument("--city", choices=["durban", "johannesburg", "both"], default="both")
    parser.add_argument("--limit", type=int, default=50, help="Max results per industry per city")
    parser.add_argument("--all", action="store_true", help="Scrape all built-in industries")
    parser.add_argument("--no-email-lookup", action="store_true",
                         help="Skip visiting websites to find emails (faster, but leaves Email column blank)")
    args = parser.parse_args()

    industries = INDUSTRIES  # --all is the only mode for now; kept flag for compatibility

    cities = ["durban", "johannesburg"] if args.city == "both" else [args.city]

    all_rows = []
    for i, city in enumerate(cities):
        all_rows.extend(scrape_city(city, args.limit, industries))
        if i < len(cities) - 1:
            time.sleep(10)  # be polite between the two city requests

    all_rows = dedupe(all_rows)

    if not all_rows:
        print("\nNo leads found from either city. Overpass may be down or "
              "heavily rate-limited right now — this run produced nothing, "
              "try again later (the next scheduled run will retry automatically).")
        sys.exit(0)

    all_rows = enrich_with_emails(all_rows, skip=args.no_email_lookup)

    write_csv(all_rows)


if __name__ == "__main__":
    main()
