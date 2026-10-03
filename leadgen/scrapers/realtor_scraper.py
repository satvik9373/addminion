"""
Realtor.com Scraper
Scrapes agent profiles from Realtor.com
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging
import time
import re
import os

logger = logging.getLogger(__name__)

class RealtorScraper:
    def __init__(self):
        self.apify_api_key = os.environ.get('APIFY_API_KEY', '')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        })

    def scrape_top_agents_by_zip(self, zip_codes: List[str] = None) -> List[Dict]:
        """
        Scrape Realtor.com for top agents in target zip codes
        """
        leads = []
        if zip_codes is None:
            zip_codes = ['90210', '90077', '90272', '90265', '91302', '90402', '90290']

        for zip_code in zip_codes:
            try:
                logger.info(f"Scraping Realtor.com for agents in {zip_code}...")

                # Realtor.com agent search URL
                search_url = f"https://www.realtor.com/realestateagents/{zip_code}"

                response = self.session.get(search_url, timeout=30)

                if response.status_code == 200:
                    # Parse agent profile links
                    agent_cards = re.findall(
                        r'href="(/realestateagents/[^"]+)"',
                        response.text
                    )

                    for card_path in agent_cards[:15]:  # Top 15 per zip
                        agent_url = f"https://www.realtor.com{card_path}"
                        agent_data = self._scrape_realtor_agent(agent_url)
                        if agent_data:
                            agent_data['zip_code'] = zip_code
                            leads.append(agent_data)
                        time.sleep(1)  # Rate limiting

            except Exception as e:
                logger.error(f"Error scraping Realtor.com for {zip_code}: {str(e)}")

        return self._dedupe_leads(leads)

    def scrape_agents_apify(self, zip_codes: List[str] = None) -> List[Dict]:
        """
        Scrape Realtor.com agent profiles via Apify.
        Actor: cleansyntax/realtor-com-agents-scraper (verified live).
        Accepts all ZIP codes in a single run (newline-separated).
        """
        if not self.apify_api_key:
            logger.warning("Apify API key not configured. Using direct scraping.")
            return self.scrape_top_agents_by_zip(zip_codes)

        if zip_codes is None:
            zip_codes = ['90210', '90077', '90272', '90265', '91302', '90402', '90290']

        leads = []
        try:
            logger.info(f"Scraping Realtor.com agents via Apify for zips: {zip_codes}")

            url = "https://api.apify.com/v2/acts/cleansyntax~realtor-com-agents-scraper/runs"
            payload = {
                "zipcodes_text": "\n".join(zip_codes),
                "maxResults": 50,  # per ZIP
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.apify_api_key}"
            }

            run_response = requests.post(url, json=payload, headers=headers)
            if run_response.status_code == 201:
                run_data = run_response.json()
                run_id = run_data.get('data', {}).get('id')
                leads = self._wait_for_apify_results(run_id, 'all-zips')
            else:
                logger.error(f"Apify Realtor run failed: {run_response.text}")

        except Exception as e:
            logger.error(f"Error in Apify Realtor scraping: {str(e)}")

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
                        if not isinstance(item, dict):
                            continue

                        lead = self._parse_apify_agent(item)
                        if lead and lead.get('name'):
                            leads.append(lead)

                    offset += limit
                else:
                    break

            except Exception as e:
                logger.error(f"Error fetching Apify dataset: {str(e)}")
                break

        return leads

    def _parse_apify_agent(self, item: Dict) -> Optional[Dict]:
        """
        Parse an agent record from the cleansyntax Realtor.com agents actor.
        Verified schema (live): fullname, broker.name, ratings_reviews.*,
        listing_stats.{for_sale, recently_sold_annual, combined_annual},
        fulfillment_id.
        """
        try:
            name = (item.get('fullname') or item.get('fullName') or item.get('name') or '').strip()
            if not name:
                return None

            broker = item.get('broker') or {}
            if isinstance(broker, dict):
                brokerage = broker.get('name')
            else:
                brokerage = str(broker) if broker else None

            ratings = item.get('ratings_reviews') or {}
            if isinstance(ratings, dict):
                rating = ratings.get('average_rating')
                reviews = ratings.get('reviews_count')
            else:
                rating = item.get('rating')
                reviews = item.get('reviews')

            listing_stats = item.get('listing_stats') or {}
            for_sale = listing_stats.get('for_sale') or {}
            sold_annual = listing_stats.get('recently_sold_annual') or {}
            combined_annual = listing_stats.get('combined_annual') or {}

            # Build active listings from for_sale stats
            active_listings = []
            for_sale_count = for_sale.get('count') or 0
            for_sale_min = for_sale.get('min')
            for_sale_max = for_sale.get('max')
            if for_sale_count:
                active_listings = [{
                    'price': for_sale_max,
                    'status': 'active',
                }]

            # Sold listings detail
            sold_details = listing_stats.get('recently_sold_listing_details') or {}
            recent_sales = sold_details.get('listings') or []

            # Estimate annual volume: sold count x average price band
            annual_volume = None
            sold_count = sold_annual.get('count')
            combined_min = combined_annual.get('min')
            combined_max = combined_annual.get('max')
            if sold_count and (combined_min or combined_max):
                avg_price = ((combined_min or 0) + (combined_max or 0)) / 2
                annual_volume = (sold_count * avg_price) / 1_000_000  # in millions

            fulfillment_id = item.get('fulfillment_id') or item.get('id')

            lead = {
                'source': 'realtor_com',
                'name': name,
                'title': 'Real Estate Agent',
                'brokerage': brokerage,
                'bio': None,
                'phone': None,
                'email': None,
                'website': None,
                'instagram': None,
                'linkedin': None,
                'profile_url': f"https://www.realtor.com/realestateagents/{fulfillment_id}" if fulfillment_id else None,
                'realtor_id': fulfillment_id,
                'zip_code': '',
                'annual_volume': round(annual_volume, 1) if annual_volume else None,
                'active_listings': active_listings,
                'recent_sales': recent_sales if isinstance(recent_sales, list) else [],
                'rating': rating,
                'reviews': reviews,
                'sold_count': sold_count,
                'avg_sale': round(((combined_min or 0) + (combined_max or 0)) / 2, 0) if (combined_min or combined_max) else None,
            }
            return lead
        except Exception as e:
            logger.debug(f"Error parsing Apify agent item: {str(e)}")
            return None

    def _parse_volume_to_millions(self, value) -> Optional[float]:
        """Convert a sold-volume string/number to millions of dollars"""
        if value is None:
            return None
        text = str(value)
        # e.g. "$50M", "$50M+", "50M", "$50,000,000", "25M-50M"
        match = re.search(r'\$?\s*(\d+(?:\.\d+)?)\s*(M|million)', text, re.IGNORECASE)
        if match:
            return float(match.group(1))
        match = re.search(r'\$?\s*([\d,]+(?:\.\d+)?)', text)
        if match:
            num = float(match.group(1).replace(',', ''))
            if num >= 1000:
                return num / 1_000_000
        return None

    def _scrape_realtor_agent(self, url: str) -> Optional[Dict]:
        """Scrape individual Realtor.com agent profile.

        Existing contract unchanged: returns a parsed dict, or None for any
        non-200 response or fetch/parse error. Search-fallback callers that only
        need 'did we get data' keep using this method.
        """
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return None
            return self._parse_agent_profile(response, url)
        except Exception as e:
            logger.error(f"Error scraping Realtor.com agent {url}: {str(e)}")
            return None

    def _scrape_realtor_agent_checked(self, url: str):
        """Fetch + parse a Realtor.com agent profile for enrichment.

        Returns (http_status, data). A 403/429 block or 404 is surfaced to the
        caller so it can be distinguished from a page that genuinely carries no
        contact info — the provider reports those as a failure, never as
        'no contact'. Returns (None, None) when no HTTP status was obtained
        (network/parse error) so callers can tell that apart from a real page.
        """
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return response.status_code, None
            return response.status_code, self._parse_agent_profile(response, url)
        except Exception as e:
            logger.error(f"Error scraping Realtor.com agent {url}: {str(e)}")
            return None, None

    def _parse_agent_profile(self, response, url: str) -> Dict:
        """Parse a successful Realtor.com agent profile response body."""
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract agent information
        agent_data = {
            'source': 'realtor_com',
            'profile_url': url,
            'name': self._extract_text(soup, [
                '.agent-name',
                '.profile-name',
                'h1[data-test="agent-name"]',
                'h1'
            ]),
            'title': self._extract_text(soup, [
                '.agent-title',
                '.profile-title',
                '.title'
            ]),
            'brokerage': self._extract_text(soup, [
                '.brokerage-name',
                '.company-name',
                '.agent-brokerage'
            ]),
            'bio': self._extract_text(soup, [
                '.bio-text',
                '.agent-bio',
                '.about-section'
            ]),
            'phone': self._extract_phone(soup),
            'email': self._extract_email(soup),
            'website': self._extract_link(soup, 'website'),
            'instagram': self._extract_social(soup, 'instagram'),
            'linkedin': self._extract_social(soup, 'linkedin'),
            'recent_sales': self._extract_sales(soup),
            'zip_codes': [],
        }

        # Extract zip codes from service areas
        text = soup.get_text()
        zip_mentions = re.findall(r'\b(\d{5})\b', text)
        if zip_mentions:
            agent_data['zip_codes'] = list(set(zip_mentions[:5]))

        # Extract years licensed
        license_text = self._extract_text(soup, ['.license-info', '.licensed'])
        if license_text:
            years = re.search(r'(\d+)\s*(?:years|yrs)?', license_text)
            if years:
                agent_data['years_experience'] = int(years.group(1))

        return agent_data

    def scrape_by_brokerage(self, brokerages: List[str]) -> List[Dict]:
        """
        Search for agents by brokerage name
        """
        leads = []
        for brokerage in brokerages:
            try:
                # Search URL for realtor.com
                search_url = f"https://www.realtor.com/realestateagents/?term={brokerage.replace(' ', '+')}"

                response = self.session.get(search_url, timeout=30)

                if response.status_code == 200:
                    # Parse agent profile links from search results
                    agent_links = re.findall(
                        r'href="(/realestateagents/[^"]+)"',
                        response.text
                    )

                    count = 0
                    for link in agent_links:
                        if count >= 10:  # Limit per brokerage
                            break
                        agent_url = f"https://www.realtor.com{link}"
                        agent_data = self._scrape_realtor_agent(agent_url)
                        if agent_data:
                            agent_data['brokerage'] = brokerage
                            leads.append(agent_data)
                        time.sleep(1)
                        count += 1

            except Exception as e:
                logger.error(f"Error searching brokerage {brokerage}: {str(e)}")

        return self._dedupe_leads(leads)

    def _extract_text(self, soup, selectors) -> Optional[str]:
        """Extract text content using multiple selectors"""
        for selector in selectors:
            el = soup.select_one(selector) if hasattr(soup, 'select_one') else None
            if el:
                text = el.get_text(strip=True)
                if text:
                    return text

        # Fallback: look for elements with matching text patterns
        for pattern in ['agent-name', 'brokerage', 'title', 'bio']:
            el = soup.find(class_=re.compile(pattern, re.IGNORECASE))
            if el:
                text = el.get_text(strip=True)
                if text:
                    return text

        return None

    def _extract_phone(self, soup) -> Optional[str]:
        """Extract phone number"""
        # Try to find phone in the page
        text = soup.get_text()
        phones = re.findall(r'[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4}', text)
        return phones[0] if phones else None

    def _extract_email(self, soup) -> Optional[str]:
        """Extract email address"""
        # Check for mailto links
        mailto_links = soup.find_all('a', href=re.compile(r'mailto:'))
        for link in mailto_links:
            href = link.get('href', '')
            email = re.search(r'mailto:([^?]+)', href)
            if email:
                return email.group(1)

        # Check text content for email patterns
        text = soup.get_text()
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        # Filter common non-personal emails
        personal = [e for e in emails if not any(x in e for x in ['realtor', 'zillow', 'info'])]
        return personal[0] if personal else None

    def _extract_link(self, soup, platform: str) -> Optional[str]:
        """Extract website or social link"""
        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            if platform in href.lower():
                return href
        return None

    def _extract_social(self, soup, platform: str) -> Optional[str]:
        """Extract social media link"""
        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            platform_domains = {
                'instagram': ['instagram.com', 'instagr.am'],
                'linkedin': ['linkedin.com'],
                'facebook': ['facebook.com'],
            }
            if platform in platform_domains:
                if any(domain in href.lower() for domain in platform_domains[platform]):
                    return href
        return None

    def _extract_sales(self, soup) -> List[Dict]:
        """Extract recent sales information"""
        sales = []
        sales_section = soup.find(class_=re.compile(r'sale|recent|transaction', re.IGNORECASE))

        if sales_section:
            cards = sales_section.find_all(['div', 'li'], class_=re.compile(r'sale|card|item'))
            for card in cards[:5]:
                sale = {
                    'address': card.get_text()[:100],  # First 100 chars usually contains address
                    'link': card.find('a', href=True).get('href') if card.find('a') else None,
                }

                # Extract price and date
                text = card.get_text()
                price_match = re.search(r'\$[\d,]+[KMB]?', text)
                if price_match:
                    sale['price'] = price_match.group()

                date_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}', text)
                if date_match:
                    sale['date'] = date_match.group()

                if sale.get('address'):
                    sales.append(sale)

        return sales

    def _dedupe_leads(self, leads: List[Dict]) -> List[Dict]:
        """Remove duplicate leads"""
        seen = set()
        unique = []
        for lead in leads:
            key = lead.get('profile_url') or lead.get('name')
            if key and key not in seen:
                seen.add(key)
                unique.append(lead)
        return unique