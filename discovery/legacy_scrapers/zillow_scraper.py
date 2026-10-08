"""
Zillow Scraper
Uses Apify for Zillow scraping as mentioned in the ICP
Alternative: direct scraping for public profiles
"""

import requests
from typing import List, Dict, Optional
import logging
import time
import re
import os

logger = logging.getLogger(__name__)


def _normalize_agent_profile_url(url) -> Optional[str]:
    """The agent profile URL is the stable identity for a Zillow agent.
    A listing URL is NOT a valid fallback — it changes per listing and would
    fabricate a new lead row on every scrape — so if no agent profile is
    present we return None and let the DB dedupe via canonical_key
    (email/phone). Relative paths are completed against the Zillow origin."""
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if url.startswith('/'):
        return 'https://www.zillow.com' + url
    return url


class ZillowScraper:
    def __init__(self):
        self.apify_api_key = os.environ.get('APIFY_API_KEY', '')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def scrape_top_producers_apify(self, zip_codes: List[str] = None) -> List[Dict]:
        """
        Use Apify to scrape Zillow top producers in target zip codes
        """
        leads = []

        if not self.apify_api_key:
            logger.warning("Apify API key not configured. Using direct scraping instead.")
            return self._scrape_zillow_direct(zip_codes)

        if zip_codes is None:
            zip_codes = ['90210', '90077', '90272', '90265', '91302', '90402', '90290']

        try:
            for zip_code in zip_codes:
                logger.info(f"Scraping Zillow listings in {zip_code} via Apify...")

                # Apify actor: igolaizola/zillow-scraper-ppe (verified live)
                url = f"https://api.apify.com/v2/acts/igolaizola~zillow-scraper-ppe/runs"

                payload = {
                    "location": zip_code,
                    "locationType": "zipcode",
                    "operation": "buy",
                    "homeTypes": ["houses"],
                    "minPrice": 500000,   # luxury floor
                    "maxItems": 25,       # per zip, keep it light
                    "sortBy": "highPrice",
                }

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.apify_api_key}"
                }

                # Run the actor
                run_response = requests.post(url, json=payload, headers=headers)
                if run_response.status_code == 201:
                    run_data = run_response.json()
                    run_id = run_data.get('data', {}).get('id')

                    # Wait for completion
                    leads.extend(self._wait_for_apify_results(run_id, zip_code))
                else:
                    logger.error(f"Apify run failed for {zip_code}: {run_response.text}")

                time.sleep(2)  # Rate limiting

        except Exception as e:
            logger.error(f"Error in Apify scraping: {str(e)}")

        return leads

    def _wait_for_apify_results(self, run_id: str, zip_code: str) -> List[Dict]:
        """Wait for Apify actor to complete and fetch results"""
        leads = []
        max_attempts = 30
        attempt = 0

        while attempt < max_attempts:
            try:
                status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
                headers = {"Authorization": f"Bearer {self.apify_api_key}"}

                status_response = requests.get(status_url, headers=headers)
                status_data = status_response.json()

                status = (status_data.get('data', {}).get('status') or '').upper()

                if status == 'SUCCEEDED':
                    # Fetch results
                    dataset_id = status_data['data'].get('defaultDatasetId')
                    if dataset_id:
                        leads = self._fetch_apify_dataset(dataset_id)
                    break
                elif status in ['FAILED', 'ABORTED', 'TIMED_OUT']:
                    logger.error(f"Apify run failed with status: {status}")
                    break

                time.sleep(5)
                attempt += 1

            except Exception as e:
                logger.error(f"Error checking Apify status: {str(e)}")
                attempt += 1

        return leads

    def _fetch_apify_dataset(self, dataset_id: str) -> List[Dict]:
        """Fetch results from Apify dataset"""
        leads = []
        offset = 0
        limit = 100

        while True:
            try:
                url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?format=json&offset={offset}&limit={limit}"
                headers = {"Authorization": f"Bearer {self.apify_api_key}"}

                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()

                    # Items endpoint returns a plain list (format=json);
                    # actor-run endpoints return {'data': [...]}.
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        items = data.get('data', [])
                    else:
                        items = []

                    if not items:
                        break

                    for item in items:
                        listing = item.get('listing', {}) or {}
                        agent_name = listing.get('agentName') or listing.get('agent_name')
                        if not agent_name:
                            continue  # Skip listings with no agent attribution

                        address = item.get('address', {}) or {}
                        zip_code = address.get('zipcode') or address.get('zip') or item.get('zip_code') or ''

                        lead = {
                            'source': 'zillow',
                            'name': agent_name,
                            'brokerage': listing.get('brokerName') or listing.get('broker_name'),
                            'zip_code': str(zip_code),
                            'profile_url': _normalize_agent_profile_url(
                                listing.get('agentProfileUrl') or listing.get('agent_profile_url')),
                            'phone': listing.get('agentPhoneNumber') or listing.get('phone'),
                            'email': listing.get('agentEmail') or listing.get('email'),
                            'website': listing.get('website'),
                            'instagram': listing.get('instagram'),
                            'listing_url': item.get('url'),
                            'listing_price': item.get('price'),
                            'active_listings': [{
                                'address': f"{address.get('streetAddress', '')}, {address.get('city', '')}, {address.get('state', '')} {zip_code}".strip(', '),
                                'price': item.get('price'),
                                'beds': item.get('bedrooms'),
                                'baths': item.get('bathrooms'),
                                'sqft': item.get('livingArea'),
                                'url': item.get('url'),
                            }] if item.get('price') else [],
                            'recent_sales': [],
                        }
                        leads.append(lead)

                    offset += limit
                else:
                    break

            except Exception as e:
                logger.error(f"Error fetching Apify dataset: {str(e)}")
                break

        return leads

    def _scrape_zillow_direct(self, zip_codes: List[str] = None) -> List[Dict]:
        """
        Direct scraping of Zillow agent profiles (publicly available info)
        This is a fallback when Apify is not available
        """
        leads = []
        if zip_codes is None:
            zip_codes = ['90210', '90077', '90272', '90265', '91302', '90402', '90290']

        for zip_code in zip_codes:
            try:
                # Zillow agent directory
                search_url = f"https://www.zillow.com/agent-directory/california/los-angelle/90210/{zip_code}/"
                response = self.session.get(search_url, timeout=15)

                if response.status_code == 200:
                    # Parse agent links from search results
                    agent_links = re.findall(r'href="(/agents/[^"]+)"', response.text)

                    for link in agent_links[:10]:
                        agent_url = f"https://www.zillow.com{link}"
                        agent_data = self._scrape_zillow_agent(agent_url)
                        if agent_data:
                            leads.append(agent_data)
                        time.sleep(1)

            except Exception as e:
                logger.error(f"Error scraping Zillow for {zip_code}: {str(e)}")

        return leads

    def _scrape_zillow_agent(self, url: str) -> Optional[Dict]:
        """Scrape individual Zillow agent profile"""
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return None

            text = response.text
            soup = BeautifulSoup(text, 'html.parser')

            # Extract data from the page
            agent_data = {
                'source': 'zillow',
                'profile_url': url,
                'name': self._extract_from_zillow(soup, ['h1.agent-name', '.agent-name', 'h1']),
                'brokerage': self._extract_from_zillow(soup, ['.brokerage-name', '.team-name']),
                'phone': self._extract_phone_from_zillow(soup),
                'email': self._extract_email_from_zillow(soup),
                'bio': self._extract_from_zillow(soup, ['.bio-text', '.agent-bio']),
                'website': self._extract_link_from_zillow(soup, 'website'),
                'instagram': self._extract_link_from_zillow(soup, 'instagram'),
                'recent_sales': self._extract_sales_from_zillow(soup),
            }

            return agent_data

        except Exception as e:
            logger.error(f"Error scraping Zillow agent {url}: {str(e)}")
            return None

    def _extract_from_zillow(self, soup, selectors) -> Optional[str]:
        for selector in selectors:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                if text:
                    return text
        return None

    def _extract_phone_from_zillow(self, soup) -> Optional[str]:
        text = soup.get_text()
        phones = re.findall(r'[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4}', text)
        return phones[0] if phones else None

    def _extract_email_from_zillow(self, soup) -> Optional[str]:
        # Zillow typically doesn't show emails publicly
        links = soup.find_all('a', href=re.compile(r'mailto:'))
        for link in links:
            mailto = link.get('href', '')
            email = re.search(r'mailto:([^?]+)', mailto)
            if email:
                return email.group(1)
        return None

    def _extract_link_from_zillow(self, soup, platform: str) -> Optional[str]:
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            if platform in href.lower():
                return href
        return None

    def _extract_sales_from_zillow(self, soup) -> List[Dict]:
        sales = []
        # Look for recent sales section
        sales_section = soup.find(class_=re.compile(r'sale|recent|transaction'))
        if sales_section:
            sale_items = sales_section.find_all(class_=re.compile(r'sale|item|card'))
            for item in sale_items[:5]:
                sale = {
                    'address': self._extract_from_zillow(item, ['.address']),
                    'price': self._extract_from_zillow(item, ['.price']),
                    'date': self._extract_from_zillow(item, ['.date']),
                }
                if sale['address'] or sale['price']:
                    sales.append(sale)
        return sales

# Import BeautifulSoup at the end to avoid issues
from bs4 import BeautifulSoup