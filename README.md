# LeadGen System — Automated Lead Generation for Luxury Real Estate

An automated lead-generation system built to the **Ember Systems ICP brief**. It scrapes prospects from the exact sources named in the ICP doc (Zillow, Realtor.com, brokerage rosters, job posts), scores them algorithmically, adds only qualifying leads to your categorized Google Sheet, and runs automated email + Instagram outreach.

```
Scrape ──► Parse ──► Score ──► Categorize ──► Enrich Contacts ──► Google Sheet
   │                          │                                      │
   └──────────────────────────┴────────────► Phone / Email / IG outreach (High & Medium)
```

---

## ✅ What's Already Working (verified live)

- **Apify API key** authenticates (`satviikkk`)
- **Zillow scraper** → `igolaizola~zillow-scraper-ppe` (104k+ runs)
- **Realtor.com agents scraper** → `cleansyntax~realtor-com-agents-scraper` (4k+ runs)
- **Live scrape confirmed**: pulled 10 real Beverly Hills agents, parsed, scored, categorized correctly
- **25/25 automated tests pass** (`py test_system.py`)

## ✅ All credentials configured

| Item | Status |
|------|--------|
| **SMTP email** | `codequarry00@gmail.com` — login tested OK |
| **Google Sheets** | Service account + spreadsheet "Lead-Gen" — sync verified live, tabs auto-created |
| **Instagram account** | `coxdeee` — set (cold-DM browser path) |
| **Instagram token + IG ID** | Valid, warm-DM API path ready |
| **Apify** | Valid, live scrape verified |

---

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

Minimum for the test suite (already installed on this machine):
```bash
pip install beautifulsoup4 requests selenium jinja2 pandas lxml google-auth google-api-python-client
```

> Selenium also needs a **Chrome** browser + [ChromeDriver](https://chromedriver.chromium.org/) (or the `webdriver-manager` package handles it automatically).

## 2. Configure `.env`

A `.env` file already exists in `leadgen/` with your Apify key, SMTP password, and IG token. Edit it to add the missing values:

```env
# --- Email ---
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=          # ← FILL THIS: your sending email address
SMTP_PASSWORD=          # already set (Gmail app password)

# --- Google Sheets ---
GOOGLE_SHEETS_CREDENTIALS_PATH=credentials/google-service-account.json
GOOGLE_SHEETS_ID=       # ← FILL THIS: the spreadsheet ID

# --- Instagram ---
INSTAGRAM_ACCESS_TOKEN= # ← REGENERATE (current token is rejected by Meta)
INSTAGRAM_IG_ID=        # ← FILL THIS: your IG business account ID
INSTA_USERNAME=         # ← FILL THIS: new dedicated outreach account
INSTA_PASSWORD=         # ← FILL THIS
```

### Email (SMTP) setup — Gmail example
1. Use a **dedicated Gmail** for outreach.
2. Turn on **2-Step Verification** (required for app passwords).
3. Google Account → Security → **App passwords** → generate one for "Mail".
4. Put the app password (16 chars, like `abcd efgh ijkl mnop`) in `SMTP_PASSWORD`, and the full email address in `SMTP_USERNAME`.

> The `SMTP_PASSWORD` you already shared works with whatever Gmail account owns it — it just needs to be paired with the right `SMTP_USERNAME`.

### Google Sheets setup
1. Go to [console.cloud.google.com](https://console.cloud.google.com/) → create a **project**.
2. **Enable APIs**: Google Sheets API + Google Drive API.
3. **Create credentials** → Service Account → download the JSON → save as `credentials/google-service-account.json`.
4. Create a spreadsheet in Google Sheets. Its **ID** is in the URL: `docs.google.com/spreadsheets/d/<THIS_IS_THE_ID>/edit`.
5. Put the ID in `GOOGLE_SHEETS_ID`.
6. **Share the spreadsheet** with the service account email (it looks like `name@project.iam.gserviceaccount.com`) — give it **Editor** access.

The system auto-creates these tabs on first sync:
`High Score (15+)` · `Medium Score (10-14)` · `Low Score (5-9)` · `Disqualified (<5)` · `Low Scored Leads` · `No Response` · `Interested` · `Booked Call`

Leads scoring below 5 are **not deleted** — they land in the `Disqualified (<5)` / `Low Scored Leads` tabs, exactly as you specified.

### Instagram setup
- **Cold DMs** (new prospects): the system uses **browser automation** with a **new dedicated account's username + password**. Meta's official API forbids unsolicited DMs, so the token can't do cold outreach — only warm replies. Create the account, fill `INSTA_USERNAME` / `INSTA_PASSWORD`.
- **Warm-lead DMs / account validation** (the `GraphAPIClient`): you need a **valid** long-lived access token (`IGAA...`) and the business account's **IG ID**. Your current token is rejected by Meta (`Failed to decrypt`) — regenerate it at [developers.facebook.com](https://developers.facebook.com/), or via the Graph API Explorer. Store it in `INSTAGRAM_ACCESS_TOKEN` and the numeric account ID in `INSTAGRAM_IG_ID`.

## 3. Run the tests

```bash
py test_system.py          # 25/25 should pass (core + dashboard + phone/enrichment)
py test_apify_live.py      # live Apify smoke test (consumes ~1 small scrape)
```

## 3b. Web Dashboard

A local Flask dashboard layered **on top of** `LeadGenSystem` — it reuses the
existing scrapers, scorer, database, Sheets sync, and outreach modules. The
dashboard is split into **two fully independent pipelines** that share the
existing SQLite DB but never trigger each other.

```bash
py -m dashboard             # → http://127.0.0.1:5001
```

| Page | What it does |
|------|--------------|
| **Overview** | Total / High / Medium / Low / Disqualified / qualified / contacted / replies, contact stats (Contactable / Has Phone / Has Email / Has Instagram / No Contact), plus a status panel for **each** pipeline (last + next run, scheduler, outreach mode) |
| **Lead Generation** | Scrape → Parse → Score → Categorize → **Contact Enrichment** → Google Sheets Sync. **Never sends outreach.** Run/Stop, live 6-stage progress, run history, its own scheduler |
| **Outreach** | Processes **existing qualified leads only** (never scrapes/scores). Builds a queue, sends Email + Instagram, and queues **manual phone calls**. Records every attempt. **Dry Run by default** — previews the queue and sends nothing. Its own scheduler |
| **Leads** | Search & filter the existing SQLite leads (name, source, category, status, contact availability: Contactable / No Contact / Has Phone / Has Email / Has Instagram), per-lead details + outreach history |

### Two independent pipelines

- **Lead Generation** (`/leadgen`): `Scraping → Parsing → Scoring → Categorizing → Contact Enrichment → Google Sheets Sync`. There is no outreach stage and no outreach method call anywhere in this runner.
- **Outreach** (`/outreach`): `Query Leads → Check Eligibility → Check Contact Availability → Check History → Build Queue → Phone Tasks → Email → Instagram → Record Results`. It queries `qualified = 1` leads, checks each lead's channel eligibility and previous outreach history, then processes the enabled channels (Phone as a manual task, Email, Instagram).

### Outreach mode: Dry Run / Live

- **Dry Run (default)** — builds and previews the exact queue (who/what would be sent), sends nothing, records nothing.
- **Live** — actually sends email / Instagram DMs and records every attempt/result to `outreach_history`. Switching to Live and running Live both require an explicit confirmation in the UI.

### Contact Enrichment (Lead Generation stage)

Many scraped prospects arrive with no email or Instagram handle. A dedicated
**Contact Enrichment** stage (between *Categorizing* and *Google Sheets Sync*)
fills in whatever contact data it can find, so leads leave Lead Generation as
**qualified + contactable** on any channel:

- **Enriched fields** — `phone` (normalized to E.164 like `+14155551234`), `phone_type`, `phone_source`, `phone_verified`, `phone_last_checked`, `phone_raw`, plus existing `email` / `instagram`.
- **Providers (pluggable)** — the system reuses contact data already captured during scraping (`scraped`) and the existing free Realtor.com public-profile scraper (`website`). It **never fabricates** a value: if a channel isn't found, it's simply left blank.
- **Never claims verified** — `phone_verified` stays `0`; there is no verification mechanism, so the UI/Sheets never imply one.
- **TTL-aware** — a lead is only re-enriched after `CONTACT_ENRICHMENT_TTL_HOURS` (default **168h**, i.e. weekly) or if the last attempt failed. Per-lead failure isolation: one bad lead never stops the run.
- **Rate limited** — `CONTACT_ENRICHMENT_DELAY_SECONDS` (default 1.0) between provider fetches and `CONTACT_ENRICHMENT_MAX_LEADS_PER_RUN` (default 50) per run.

Phone is **never auto-called or SMS'd** anywhere in the system. Enrichment only
collects the number; calling is always a manual task on the Outreach page.

### Duplicate protection (hard guarantee)

The same channel + touch is **never sent twice** to the same lead, even if the
runner is triggered twice (manual + scheduled):

1. **Pre-send DB check** — `has_successful_outreach(lead, channel, touch)` skips already-sent items.
2. **Unique partial index** on `outreach_history (lead_id, channel, message_type) WHERE success = 1` + `INSERT OR IGNORE` — a duplicate successful record is silently dropped.
3. **Status enum** — `pending / processing / sent / failed / replied / skipped` on `outreach_history.status` / `leads.outreach_status`.
4. Email keeps the **5-touch T1–T5 sequence** (the touch is part of the idempotency key); Instagram uses a single `dm` touch; Phone uses `CALL` (a completed call can never be re-queued, but a skipped/failed one stays retryable).
5. **Phone is always a manual call task** — in both Dry Run and Live the pipeline only *exposes* phone tasks with **Mark Called / Skip** buttons on the Outreach page. It never auto-dials and never sends SMS.

### Independent schedulers

Each pipeline has its **own** scheduler, both **OFF by default**, persisted to
separate files (`data/scheduler_leadgen.json`, `data/scheduler_outreach.json`)
so they survive restarts. Enabling lead-gen's scheduler never triggers
outreach, and vice-versa. Configurable frequency in hours; overlap-safe
(`max_instances=1` + each runner's own running guard).

Notes:

- Binds to **127.0.0.1 only** (local). Override with `DASHBOARD_HOST` / `DASHBOARD_PORT`.
- The old combined **Pipeline** and **Scheduler** pages are gone — `/pipeline` redirects to `/leadgen`, and each pipeline page has its own scheduler controls.
- **No secrets are ever rendered** — the health endpoint returns booleans/counts only; keys stay in `.env` / `credentials/`.
- Run history lives in the existing `leadgen.db` (`pipeline_runs` table), tagged `leadgen-*` / `outreach-*` so each pipeline page shows only its own runs.

## 4. Run the system

```python
from leadgen.main import LeadGenSystem

system = LeadGenSystem()
errors = system.validate_setup()   # tells you what's still missing
print(errors)

results = system.run_full_cycle()        # scrape → score → categorize → outreach
# or the weekly rhythm from the ICP doc:
results = system.run_weekly_rhythm('Mon')  # build 50-contact list by signal
results = system.run_weekly_rhythm('Tue')  # demo batch day
results = system.run_weekly_rhythm('Wed')  # IG engagement + DMs + email
results = system.run_weekly_rhythm('Fri')  # follow-ups + pipeline review
```

## Architecture

```
leadgen/
├── config.py               # Config, scoring weights, templates, sheet tabs
├── env_loader.py           # Loads leadgen/.env (no external deps)
├── main.py                 # Orchestrator: weekly rhythm + full cycle
├── database.py             # SQLite storage
├── sheets_sync.py          # Google Sheets sync with per-category tabs
├── scrapers/
│   ├── brokerage_scraper.py    # Compass, The Agency, Carolwood rosters
│   ├── zillow_scraper.py       # Apify igolaizola~zillow-scraper-ppe + direct
│   ├── realtor_scraper.py      # Apify cleansyntax~realtor-com-agents-scraper + direct
│   └── job_post_scraper.py     # Indeed hiring signals (ISA/assistant postings)
├── enrichment/
│   ├── phone_utils.py          # E.164 phone normalization / validation
│   ├── contact_enricher.py     # Provider-based ContactEnricher (TTL, isolation)
│   └── providers/
│       ├── scraped_data.py         # contact data already captured during scraping
│       └── realtor_profile.py      # reuses the free Realtor.com profile scraper
├── scoring/
│   └── lead_scorer.py          # Financial (30%) + Buying Triggers (40%) + ICP fit (30%)
└── outreach/
    ├── email_sender.py         # 5-touch sequence (T1–T5 over 14 days)
    ├── instagram_dm.py         # GraphAPIClient (token) + Selenium cold-DM
    └── demo_generator.py       # Personalized Loom demos per listing
```

## Scoring model (from the ICP doc)

- **Financial Indicators (30%)** — transaction volume ($50M+ = 15 pts …), avg sale price, active listings, est. monthly spend
- **Buying Triggers (40%)** — hiring ISA (25), new $5M+ listing (20), Zillow Premier (15), team expansion (12), went independent (10), weekend open houses (8)
- **ICP Fit (30%)** — team/solo/boutique tier, target brokerage, target zip, ops-director role

Scores are weighted to **0–100**. Categories:
**High ≥15** · **Medium 10–14** · **Low 5–9** · **Disqualified <5** (moved to the low-score tab, never deleted).

## Security notes

- `.env` and `credentials/` are gitignored — **never commit them**.
- The Instagram token and Apify key you shared in chat are now in your local `.env`. Rotate the **Instagram token** when convenient (it's the one most exposed), and avoid pasting secrets into chat going forward.
