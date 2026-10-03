#!/usr/bin/env python3
"""
Live Apify smoke test — Realtor.com agents scrape for one ZIP.
Runs cleansyntax~realtor-com-agents-scraper with maxResults=10,
polls to completion, and prints the parsed leads.
Consumes a small amount of Apify credits.
"""

import sys
import os
import time
import json

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from leadgen.config import config
from leadgen.scrapers.realtor_scraper import RealtorScraper

API = 'https://api.apify.com'
KEY = config.APIFY_API_KEY


def main():
    if not KEY:
        print('No APIFY_API_KEY configured. Aborting.')
        return 1

    scraper = RealtorScraper()
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {KEY}',
    }

    # Start a minimal run: one ZIP, 10 results
    print('Starting Apify run: cleansyntax~realtor-com-agents-scraper (zip 90210, max 10)...')
    r = requests_post(f'{API}/v2/acts/cleansyntax~realtor-com-agents-scraper/runs',
                      json={'zipcodes_text': '90210', 'maxResults': 10},
                      headers=headers)
    print(f'  Run start status: {r.status_code}')
    if r.status_code != 201:
        print('  FAILED to start run:', r.text[:300])
        return 1

    run_id = r.json()['data']['id']
    print(f'  Run ID: {run_id}')

    # Poll for completion
    for attempt in range(30):
        time.sleep(5)
        sr = requests_get(f'{API}/v2/actor-runs/{run_id}', headers=headers)
        status = (sr.json().get('data', {}).get('status', '?') or '?').upper()
        print(f'  [{attempt}] status: {status}')
        if status == 'SUCCEEDED':
            dataset_id = sr.json()['data'].get('defaultDatasetId')
            print(f'  Dataset ID: {dataset_id}')
            leads = scraper._fetch_apify_dataset(dataset_id)
            print(f'\n=== Parsed {len(leads)} leads ===')
            for lead in leads[:10]:
                print(f"  - {lead.get('name')} | brokerage={lead.get('brokerage')} "
                      f"| active={len(lead.get('active_listings') or [])} | volume={lead.get('annual_volume')} | rating={lead.get('rating')}")
            print('\nSample lead JSON:')
            if leads:
                print(json.dumps(leads[0], indent=2, default=str)[:1200])
            return 0
        elif status in ('FAILED', 'ABORTED', 'TIMED_OUT'):
            print('  Run ended with bad status:', status)
            print('  ', sr.text[:400])
            return 1

    print('  Timed out waiting for run to finish.')
    return 1


def requests_post(url, json, headers):
    import requests
    return requests.post(url, json=json, headers=headers, timeout=20)


def requests_get(url, headers):
    import requests
    return requests.get(url, headers=headers, timeout=20)


if __name__ == '__main__':
    sys.exit(main())
