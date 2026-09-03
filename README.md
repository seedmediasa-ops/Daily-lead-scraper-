# 🚀 SeedMediaa Lead Scraper

**Automated lead generation for SeedMediaa outreach campaigns**

Scrapes business leads from Durban & Johannesburg using free methods.

---

## 📁 What's in this repo?

| File | Purpose |
|------|---------|
| `seedmediaa_scraper.py` | Main scraper script |
| `.github/workflows/scraper.yml` | Runs automatically every day |
| `requirements.txt` | Python dependencies |
| `leads_output/` | Generated CSV files (auto-committed) |

---

## 🆓 Free Methods Used

1. **Google Places API** — $200 free credit/month (~10,000 searches)
2. **Yellow Pages SA** — Direct web scraping (no API needed)
3. **Google Search** — Backup scraping with delays

---

## ⚡ Quick Start (Run on your computer)

### 1. Install Python & dependencies
```bash
pip install -r requirements.txt
```

### 2. Get a free Google Places API key
- Go to [Google Cloud Console](https://console.cloud.google.com)
- Create project → Enable **Places API**
- Create API Key → Copy it

### 3. Run the scraper
```bash
# Scrape construction companies in Durban
python seedmediaa_scraper.py --city durban --industry construction --limit 30

# Scrape all industries in both cities
python seedmediaa_scraper.py --city both --all --limit 25

# Scrape specific industries in Johannesburg
python seedmediaa_scraper.py --city johannesburg --industries legal medical real_estate --limit 20
```

### 4. Import to Google Sheets
- Open your SeedMediaa Outreach Sheet
- File → Import → Upload → Select the generated CSV
- Choose "Append to current sheet"
- Run Apps Script personalization

---

## 🤖 Automated Daily Scraping (GitHub Actions)

This repo includes a GitHub Actions workflow that **runs automatically every day** and commits new leads.

### Setup:

1. **Fork this repo** to your own GitHub account

2. **Add your API key as a secret:**
   - Go to repo → Settings → Secrets and variables → Actions
   - Click **New repository secret**
   - Name: `GOOGLE_PLACES_API_KEY`
   - Value: [your Google Places API key]

3. **Enable Actions:**
   - Go to Actions tab → Click "I understand my workflows, go ahead and enable them"

4. **That's it!** The scraper runs daily at 6 AM SA time and commits CSV files to `leads_output/`

5. **Download leads:**
   - Go to `leads_output/` folder in your repo
   - Download the latest CSV
   - Import to Google Sheets

---

## 📊 What you get

Each CSV contains these columns (ready for Google Sheets):
- ID, Date Added, Company Name, Industry, City
- Website, CEO Name (empty — you fill this), Email, Email Status
- Subject, Body, Video Link, Sent Date, Opened, Replied
- Notes, Gemini Prompt

---

## 💡 Pro Tips

- **Start with 1 city + 3 industries** to test quality
- **Verify emails** before sending — many will be `info@` guesses
- **Use Hunter.io** (free 25 searches/month) to find real CEO emails
- **The scraper gets company names + websites** — you find the CEO names manually via LinkedIn
- **Run weekly, not daily** if you don't need that many leads

---

## ⚠️ Important Notes

- Google Places API free tier: $200/month credit (plenty for this)
- GitHub Actions free tier: 2,000 minutes/month (this uses ~5 min/day)
- Yellow Pages scraping may break if they change their website
- Always verify emails before sending — don't spam
- Respect POPIA — only email business addresses

---

## 🔗 Connect to Google Sheets

After scraping, import the CSV into your SeedMediaa Outreach Sheet:

1. Open Google Sheets
2. File → Import
3. Upload → Select CSV
4. Choose "Append to current sheet"
5. The data maps perfectly to the Leads tab structure

Then run `generatePersonalizations()` in Apps Script to write the emails.

---

**Built for SeedMediaa. Let's get those CEOs replying.** 🎯
