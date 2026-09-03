#!/usr/bin/env python3
"""
SEEDMEDIAA FREE LEAD SCRAPER
Scrapes business leads from Durban & Johannesburg
Outputs CSV ready for Google Sheets import

REQUIREMENTS (all free):
  pip install requests beautifulsoup4 pandas openpyxl

FREE METHODS USED:
  1. Google Places API (free $200/month credit = ~10,000 searches)
  2. Yellow Pages SA scraping
  3. CIPC business search
  4. Industry association directories
  5. Google Search scraping (with delays to avoid blocks)

USAGE:
  python seedmediaa_scraper.py --city durban --industry construction --limit 50
  python seedmediaa_scraper.py --city johannesburg --all --limit 200
"""

import requests
import json
import time
import re
import csv
import os
import sys
import argparse
from datetime import datetime
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — EDIT THESE
# ═══════════════════════════════════════════════════════════════

# Get a FREE Google Places API key from:
# https://console.cloud.google.com → APIs & Services → Credentials → Create API Key
# Enable "Places API" and "Maps JavaScript API"
# You get $200 free credit every month (enough for ~10,000 business searches)
GOOGLE_PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY', 'YOUR_API_KEY_HERE')

# Output file
OUTPUT_DIR = 'leads_output'

# Delay between requests (seconds) — be respectful
REQUEST_DELAY = 2

# ═══════════════════════════════════════════════════════════════
# INDUSTRY KEYWORDS FOR SEARCHING
# ═══════════════════════════════════════════════════════════════
INDUSTRIES = {
    'construction': ['construction company', 'building contractor', 'civil engineering', 'renovation company'],
    'legal': ['law firm', 'attorney', 'legal practice', 'conveyancer'],
    'medical': ['medical practice', 'dental clinic', 'physiotherapy', 'specialist doctor'],
    'real_estate': ['real estate agency', 'property management', 'estate agent'],
    'hospitality': ['restaurant', 'hotel', 'catering company', 'event venue'],
    'automotive': ['car dealership', 'auto repair', 'panel beater', 'mechanic'],
    'financial': ['accounting firm', 'financial advisor', 'insurance broker', 'tax consultant'],
    'technology': ['software company', 'IT services', 'web development', 'digital agency'],
    'manufacturing': ['manufacturing company', 'factory', 'industrial supply'],
    'retail': ['retail store', 'ecommerce company', 'wholesale distributor'],
    'education': ['training company', 'private college', 'tutoring service'],
    'logistics': ['logistics company', 'transport company', 'courier service', 'freight forwarder'],
    'beauty': ['salon', 'spa', 'beauty clinic', 'aesthetic clinic'],
    'fitness': ['gym', 'fitness center', 'personal trainer', 'sports facility'],
    'consulting': ['business consultant', 'management consultant', 'strategy firm']
}

# ═══════════════════════════════════════════════════════════════
# GOOGLE PLACES API SCRAPER (FREE TIER)
# ═══════════════════════════════════════════════════════════════
class GooglePlacesScraper:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = 'https://maps.googleapis.com/maps/api/place'
        self.results = []

    def search(self, query, city, max_results=50):
        """Search for businesses using Google Places API (free tier)"""
        if self.api_key == 'YOUR_API_KEY_HERE':
            print("⚠️  No Google Places API key set. Skipping Places API.")
            print("   Get one free: https://console.cloud.google.com → APIs → Credentials")
            return []

        search_query = f"{query} in {city}, South Africa"
        url = f"{self.base_url}/textsearch/json"
        params = {
            'query': search_query,
            'key': self.api_key,
            'region': 'za'
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            data = response.json()

            if data.get('status') != 'OK':
                print(f"   Places API error: {data.get('status')} — {data.get('error_message', '')}")
                if data.get('status') == 'REQUEST_DENIED':
                    print("   → Make sure Places API is enabled in Google Cloud Console")
                return []

            places = data.get('results', [])[:max_results]

            for place in places:
                # Get detailed info
                details = self.get_place_details(place['place_id'])

                lead = {
                    'id': f"GP-{place['place_id'][:8]}",
                    'date_added': datetime.now().strftime('%Y-%m-%d'),
                    'company_name': place.get('name', ''),
                    'industry': query,
                    'city': city,
                    'website': details.get('website', ''),
                    'ceo_name': '',  # Will need manual research
                    'email': self.guess_email(details.get('website', ''), place.get('name', '')),
                    'email_status': 'Pending',
                    'subject': '',
                    'body': '',
                    'video_link': '',
                    'sent_date': '',
                    'opened': '',
                    'replied': '',
                    'notes': f"Google Places: {query} | Rating: {place.get('rating', 'N/A')} | Address: {place.get('formatted_address', '')}",
                    'gemini_prompt': ''
                }
                self.results.append(lead)

            print(f"   ✓ Found {len(places)} places for '{query}' in {city}")
            time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"   ✗ Error searching Places API: {e}")

        return self.results

    def get_place_details(self, place_id):
        """Get detailed info for a place"""
        url = f"{self.base_url}/details/json"
        params = {
            'place_id': place_id,
            'fields': 'name,website,formatted_phone_number,formatted_address',
            'key': self.api_key
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            return data.get('result', {})
        except:
            return {}

    def guess_email(self, website, company_name):
        """Guess email from website domain"""
        if not website:
            return ''
        try:
            domain = re.sub(r'^https?://', '', website)
            domain = re.sub(r'^www\.', '', domain)
            domain = domain.split('/')[0]
            return f"info@{domain}"
        except:
            return ''

# ═══════════════════════════════════════════════════════════════
# YELLOW PAGES SA SCRAPER (FREE — NO API NEEDED)
# ═══════════════════════════════════════════════════════════════
class YellowPagesScraper:
    def __init__(self):
        self.base_url = 'https://www.yellowpages.co.za'
        self.results = []
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def search(self, industry, city, max_pages=3):
        """Scrape Yellow Pages SA for business listings"""
        search_term = quote_plus(f"{industry} {city}")

        for page in range(1, max_pages + 1):
            url = f"{self.base_url}/search?search={search_term}&page={page}"

            try:
                print(f"   Scraping Yellow Pages page {page}...")
                response = self.session.get(url, timeout=30)

                if response.status_code != 200:
                    print(f"   ✗ Yellow Pages blocked or returned {response.status_code}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                listings = soup.find_all('div', class_=re.compile('listing|result|business'))

                if not listings:
                    # Try alternative selectors
                    listings = soup.find_all(['article', 'div'], class_=re.compile('card|item|result'))

                found = 0
                for listing in listings:
                    try:
                        name_elem = listing.find(['h2', 'h3', 'a'], class_=re.compile('title|name|business'))
                        name = name_elem.get_text(strip=True) if name_elem else 'Unknown'

                        # Skip ads and empty entries
                        if not name or len(name) < 3 or 'ad' in name.lower():
                            continue

                        phone_elem = listing.find(['a', 'span'], href=re.compile('tel:'))
                        phone = phone_elem.get_text(strip=True) if phone_elem else ''

                        website_elem = listing.find('a', href=re.compile('http'))
                        website = website_elem['href'] if website_elem else ''

                        lead = {
                            'id': f"YP-{hash(name) % 100000:05d}",
                            'date_added': datetime.now().strftime('%Y-%m-%d'),
                            'company_name': name,
                            'industry': industry,
                            'city': city,
                            'website': website,
                            'ceo_name': '',
                            'email': self.guess_email(website, name),
                            'email_status': 'Pending',
                            'subject': '',
                            'body': '',
                            'video_link': '',
                            'sent_date': '',
                            'opened': '',
                            'replied': '',
                            'notes': f"Yellow Pages SA | Phone: {phone}",
                            'gemini_prompt': ''
                        }

                        # Avoid duplicates
                        if not any(r['company_name'] == name for r in self.results):
                            self.results.append(lead)
                            found += 1

                    except Exception as e:
                        continue

                print(f"   ✓ Found {found} listings on page {page}")
                time.sleep(REQUEST_DELAY + 1)  # Extra delay for scraping

            except Exception as e:
                print(f"   ✗ Yellow Pages error: {e}")
                break

        return self.results

    def guess_email(self, website, company_name):
        if not website:
            return ''
        try:
            domain = re.sub(r'^https?://', '', website)
            domain = re.sub(r'^www\.', '', domain)
            domain = domain.split('/')[0]
            return f"info@{domain}"
        except:
            return ''

# ═══════════════════════════════════════════════════════════════
# CIPC SCRAPER (Companies and Intellectual Property Commission)
# ═══════════════════════════════════════════════════════════════
class CIPCScraper:
    """
    CIPC has a public search but requires registration.
    Alternative: Use their open data or scrape public records.
    For now, this is a placeholder — CIPC data is best accessed via:
    - https://www.cipc.co.za (manual search, free)
    - Bulk data purchases (paid)
    - Third-party aggregators
    """
    def __init__(self):
        self.results = []

    def search(self, industry, city):
        print("   CIPC scraping requires manual search or paid bulk data.")
        print("   Visit: https://www.cipc.co.za → Search Enterprise → Free search")
        print("   Filter by: Registration city, Industry code")
        return []

# ═══════════════════════════════════════════════════════════════
# GOOGLE SEARCH SCRAPER (FREE — USE WITH CAUTION)
# ═══════════════════════════════════════════════════════════════
class GoogleSearchScraper:
    """
    Scrapes Google search results for business listings.
    WARNING: Google blocks aggressive scraping. Use sparingly.
    Better alternative: Use SerpAPI (free tier: 100 searches/month)
    """
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.results = []

    def search(self, query, city, max_results=20):
        """Search Google for business listings"""
        search_query = quote_plus(f"{query} {city} South Africa contact email")
        url = f"https://www.google.com/search?q={search_query}&num={max_results}"

        try:
            print(f"   Searching Google for '{query} {city}'...")
            response = self.session.get(url, timeout=30)

            if response.status_code != 200:
                print(f"   ✗ Google blocked the request (status {response.status_code})")
                print("   → Use Google Places API instead (free and reliable)")
                return []

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract business names from search results
            results = soup.find_all('div', class_=re.compile('g|result'))

            for result in results[:max_results]:
                try:
                    title_elem = result.find('h3')
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    link_elem = result.find('a')
                    link = link_elem['href'] if link_elem else ''

                    # Extract snippet text
                    snippet_elem = result.find('div', class_=re.compile('VwiC3b|snippet'))
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

                    # Try to find email in snippet
                    email_match = re.search(r'[\w.-]+@[\w.-]+\.\w+', snippet)
                    email = email_match.group(0) if email_match else ''

                    if title and len(title) > 3:
                        lead = {
                            'id': f"GS-{hash(title) % 100000:05d}",
                            'date_added': datetime.now().strftime('%Y-%m-%d'),
                            'company_name': title,
                            'industry': query,
                            'city': city,
                            'website': link,
                            'ceo_name': '',
                            'email': email,
                            'email_status': 'Pending',
                            'subject': '',
                            'body': '',
                            'video_link': '',
                            'sent_date': '',
                            'opened': '',
                            'replied': '',
                            'notes': f"Google Search: {query} | Snippet: {snippet[:100]}",
                            'gemini_prompt': ''
                        }
                        self.results.append(lead)

                except Exception as e:
                    continue

            print(f"   ✓ Found {len(self.results)} potential leads from Google")
            time.sleep(REQUEST_DELAY + 2)  # Extra delay for Google

        except Exception as e:
            print(f"   ✗ Google search error: {e}")

        return self.results

# ═══════════════════════════════════════════════════════════════
# MAIN SCRAPER ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════
class SeedMediaaScraper:
    def __init__(self, api_key=None):
        self.api_key = api_key or GOOGLE_PLACES_API_KEY
        self.places_scraper = GooglePlacesScraper(self.api_key)
        self.yp_scraper = YellowPagesScraper()
        self.google_scraper = GoogleSearchScraper()
        self.cipc_scraper = CIPCScraper()
        self.all_leads = []

    def scrape_city(self, city, industries=None, limit_per_industry=20):
        """Scrape all sources for a city"""
        city = city.title()
        industries = industries or list(INDUSTRIES.keys())

        print(f"\n{'='*60}")
        print(f"🚀 SCRAPING {city.upper()}")
        print(f"{'='*60}\n")

        for industry_key in industries:
            keywords = INDUSTRIES.get(industry_key, [industry_key])

            print(f"\n📁 Industry: {industry_key.upper()}")
            print(f"   Keywords: {', '.join(keywords)}")

            for keyword in keywords:
                # Method 1: Google Places API (most reliable, free tier)
                print(f"\n   🔍 Method 1: Google Places API — '{keyword}'")
                self.places_scraper.search(keyword, city, limit_per_industry)

                # Method 2: Yellow Pages SA
                print(f"   🔍 Method 2: Yellow Pages SA — '{keyword}'")
                self.yp_scraper.search(keyword, city, max_pages=2)

                # Method 3: Google Search (backup)
                print(f"   🔍 Method 3: Google Search — '{keyword}'")
                self.google_scraper.search(keyword, city, max_results=10)

        # Combine and deduplicate
        self.combine_results()

        return self.all_leads

    def combine_results(self):
        """Combine results from all scrapers and remove duplicates"""
        seen = set()

        for scraper in [self.places_scraper, self.yp_scraper, self.google_scraper]:
            for lead in scraper.results:
                key = lead['company_name'].lower().strip()
                if key and key not in seen and len(key) > 2:
                    seen.add(key)
                    self.all_leads.append(lead)

        print(f"\n{'='*60}")
        print(f"✅ TOTAL UNIQUE LEADS: {len(self.all_leads)}")
        print(f"{'='*60}")

    def enrich_emails(self):
        """Try to find better emails than 'info@'"""
        print("\n📧 Enriching emails...")
        enriched = 0

        for lead in self.all_leads:
            if lead['email'].startswith('info@') and lead['website']:
                # Try common patterns
                domain = lead['email'].replace('info@', '')
                patterns = [
                    f"admin@{domain}",
                    f"contact@{domain}",
                    f"sales@{domain}",
                    f"hello@{domain}",
                    f"enquiries@{domain}"
                ]
                # For now, just note that manual research is needed
                lead['notes'] += " | Email guessed from website — verify with Hunter.io"
                enriched += 1

        print(f"   ✓ Enrichment complete. {enriched} leads need email verification.")

    def export_csv(self, filename=None):
        """Export leads to CSV for Google Sheets import"""
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"seedmediaa_leads_{timestamp}.csv"

        filepath = os.path.join(OUTPUT_DIR, filename)

        if not self.all_leads:
            print("⚠️  No leads to export!")
            return

        fieldnames = [
            'id', 'date_added', 'company_name', 'industry', 'city',
            'website', 'ceo_name', 'email', 'email_status',
            'subject', 'body', 'video_link', 'sent_date',
            'opened', 'replied', 'notes', 'gemini_prompt'
        ]

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.all_leads)

        print(f"\n💾 Exported to: {filepath}")
        print(f"   Total rows: {len(self.all_leads)}")
        print(f"\n📊 Next steps:")
        print(f"   1. Open Google Sheets → File → Import → Upload → Select {filename}")
        print(f"   2. Choose 'Replace current sheet' or 'Append to current sheet'")
        print(f"   3. Run Gemini personalization in Apps Script")
        print(f"   4. Verify emails and send campaign")

        return filepath

    def print_summary(self):
        """Print a summary of scraped leads"""
        cities = {}
        industries = {}

        for lead in self.all_leads:
            cities[lead['city']] = cities.get(lead['city'], 0) + 1
            industries[lead['industry']] = industries.get(lead['industry'], 0) + 1

        print(f"\n{'='*60}")
        print("📊 SCRAPE SUMMARY")
        print(f"{'='*60}")
        print(f"Total Leads: {len(self.all_leads)}")
        print(f"\nBy City:")
        for city, count in sorted(cities.items(), key=lambda x: -x[1]):
            print(f"   {city}: {count}")
        print(f"\nTop Industries:")
        for ind, count in sorted(industries.items(), key=lambda x: -x[1])[:10]:
            print(f"   {ind}: {count}")
        print(f"{'='*60}")

# ═══════════════════════════════════════════════════════════════
# COMMAND LINE INTERFACE
# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description='SeedMediaa Free Lead Scraper — Durban & Johannesburg',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python seedmediaa_scraper.py --city durban --industry construction --limit 30
  python seedmediaa_scraper.py --city johannesburg --all --limit 50
  python seedmediaa_scraper.py --city durban --industries legal medical --limit 20
  python seedmediaa_scraper.py --city both --all --limit 25
        """
    )

    parser.add_argument('--city', required=True, 
                       help='City to scrape: durban, johannesburg, or both')
    parser.add_argument('--industry', 
                       help='Single industry to scrape (e.g., construction)')
    parser.add_argument('--industries', nargs='+',
                       help='Multiple industries (e.g., legal medical real_estate)')
    parser.add_argument('--all', action='store_true',
                       help='Scrape ALL industries')
    parser.add_argument('--limit', type=int, default=20,
                       help='Max results per keyword (default: 20)')
    parser.add_argument('--api-key',
                       help='Google Places API key (or set GOOGLE_PLACES_API_KEY env var)')

    args = parser.parse_args()

    # Determine cities
    cities = []
    if args.city.lower() == 'both':
        cities = ['Durban', 'Johannesburg']
    else:
        cities = [args.city.title()]

    # Determine industries
    if args.all:
        industries = list(INDUSTRIES.keys())
    elif args.industries:
        industries = args.industries
    elif args.industry:
        industries = [args.industry]
    else:
        # Default: scrape top 5 industries
        industries = ['construction', 'legal', 'medical', 'real_estate', 'financial']
        print("No industry specified. Scraping top 5 industries.")

    # Initialize scraper
    api_key = args.api_key or GOOGLE_PLACES_API_KEY
    scraper = SeedMediaaScraper(api_key)

    # Scrape each city
    for city in cities:
        scraper.scrape_city(city, industries, args.limit)

    # Enrich
    scraper.enrich_emails()

    # Summary
    scraper.print_summary()

    # Export
    scraper.export_csv()

    print("\n✅ Done! Import the CSV into your Google Sheet.")

if __name__ == '__main__':
    main()
