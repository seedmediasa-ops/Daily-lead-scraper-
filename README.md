🚀 SeedMediaa Lead Scraper (OpenStreetMap Edition)

No API key. No billing. No card. 100% free.

## What changed from the Google version
The original scraper used Google Places API, which requires a linked billing
card even for free-tier usage. This version pulls business data from
**OpenStreetMap** via the public Overpass API instead — no signup, no key,
no card, ever.

**Trade-off:** OpenStreetMap has less complete data than Google (fewer phone
numbers and websites, almost never emails). Treat this as your first pass —
you still fill in CEO names and verified emails manually via LinkedIn +
Hunter.io, same as before.

## Files
- `seedmediaa_scraper.py` — the scraper
- `requirements.txt` — just `requests`, nothing else
- `.github/workflows/daily-scraper.yml` — runs automatically every day at
  6 AM SA time (04:00 UTC) and commits new leads to `leads_output/`

## Run it yourself
```
pip install -r requirements.txt
python seedmediaa_scraper.py --city both --all --limit 30
```

## Run it on GitHub Actions
1. Upload all files (keeping the `.github/workflows/` folder structure)
2. Go to the **Actions** tab → enable workflows
3. Click **Run workflow** to trigger it manually the first time
4. After it finishes, check `leads_output/` for a new CSV
5. Import that CSV into your Google Sheet's Leads tab (same as before)

No secrets, no API keys, nothing to configure. It just works.
