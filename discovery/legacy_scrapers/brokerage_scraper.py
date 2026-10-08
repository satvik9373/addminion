"""
Brokerage Scraper
Scrapes agent and team information from brokerage websites
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import time
import re
import logging
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

class BrokerageScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def scrape_compass_teams(self, city: str = 'los-angeles-ca') -> List[Dict]:
        """
        Scrape Compass team pages for agent information
        Target URL: compass.com/teams/los-angeles-ca or similar
        """
        leads = []
        try:
            base_url = f"https://www.compass.com/teams/{city}"
            response = self.session.get(base_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find agent profile links
            profile_links = soup.find_all('a', href=re.compile(r'/agents/'))

            for link in profile_links[:50]:  # Limit to avoid too many requests
                href = link.get('href', '')
                if href and '/agents/' in href:
                    agent_url = urljoin(base_url, href)
                    agent_data = self._scrape_compass_agent(agent_url)
                    if agent_data:
                        leads.append(agent_data)
                    time.sleep(1)  # Rate limiting

        except Exception as e:
            logger.error(f"Error scraping Compass: {str(e)}")

        return leads

    def _scrape_compass_agent(self, url: str) -> Optional[Dict]:
        """Scrape individual agent page from Compass"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract agent information
            agent_data = {
                'source': 'compass',
                'profile_url': url,
                'name': self._extract_text(soup, ['h1.agent-name', '.agent-profile-name', 'h1']),
                'title': self._extract_text(soup, ['.agent-title', '.title', '.agent-role']),
                'team': self._extract_text(soup, ['.team-name', '.brokerage-team']),
                'brokerage': 'Compass',
                'bio': self._extract_text(soup, ['.bio-text', '.agent-bio']),
                'listings_url': self._extract_attr(soup, 'a[href*="listings"]', 'href'),
                'email': self._extract_email(soup),
                'phone': self._extract_phone(soup),
                'website': self._extract_attr(soup, 'a[href*="website"]', 'href'),
                'instagram': self._extract_social(soup, 'instagram'),
                'linkedin': self._extract_social(soup, 'linkedin'),
                'zip_codes': [],  # Will be populated from listings
                'active_listings': [],
                'past_sales': [],
            }

            # Try to get zip codes from area mentions
            text = soup.get_text()
            zip_mentions = re.findall(r'(\d{5})', text)
            if zip_mentions:
                agent_data['zip_codes'] = list(set(zip_mentions))

            # Scrape listings if available
            if agent_data['listings_url']:
                agent_data['active_listings'] = self._scrape_compass_listings(agent_data['listings_url'])

            return agent_data

        except Exception as e:
            logger.error(f"Error scraping Compass agent {url}: {str(e)}")
            return None

    def _scrape_compass_listings(self, url: str) -> List[Dict]:
        """Scrape listings for an agent"""
        listings = []
        try:
            if not url.startswith('http'):
                return listings

            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            listing_cards = soup.find_all(['div', 'a'], class_=re.compile(r'listing|property|card'))
            for card in listing_cards[:20]:
                listing = {
                    'address': self._extract_text(card, ['.property-address', '.listing-address', 'address']),
                    'price': self._extract_text(card, ['.price', '.property-price', '.listing-price']),
                    'status': self._extract_text(card, ['.status', '.listing-status']),
                    'link': self._extract_attr(card, 'a', 'href'),
                }
                if listing['address'] or listing['price']:
                    listings.append(listing)

        except Exception as e:
            logger.error(f"Error scraping listings: {str(e)}")

        return listings

    def scrape_the_agency_teams(self) -> List[Dict]:
        """
        Scrape The Agency team pages
        Target URL: theagencyre.com/team
        """
        leads = []
        try:
            base_url = "https://www.theagencyre.com/team"
            response = self.session.get(base_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find team member profiles
            profile_links = soup.find_all('a', href=re.compile(r'/team/'))

            for link in profile_links[:30]:
                href = link.get('href', '')
                if href and '/team/' in href:
                    agent_url = urljoin(base_url, href)
                    agent_data = self._scrape_the_agency_agent(agent_url)
                    if agent_data:
                        leads.append(agent_data)
                    time.sleep(1)

        except Exception as e:
            logger.error(f"Error scraping The Agency: {str(e)}")

        return leads

    def _scrape_the_agency_agent(self, url: str) -> Optional[Dict]:
        """Scrape individual agent from The Agency"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            agent_data = {
                'source': 'the_agency',
                'profile_url': url,
                'name': self._extract_text(soup, ['h1.team-member-name', '.member-name', 'h1']),
                'title': self._extract_text(soup, ['.member-title', '.team-role', '.title']),
                'team': self._extract_text(soup, ['.team-name', '.brokerage-team']),
                'brokerage': 'The Agency',
                'bio': self._extract_text(soup, ['.bio', '.team-member-bio', '.member-bio']),
                'email': self._extract_email(soup),
                'phone': self._extract_phone(soup),
                'instagram': self._extract_social(soup, 'instagram'),
                'linkedin': self._extract_social(soup, 'linkedin'),
                'website': self._extract_attr(soup, 'a[href*="website"]', 'href'),
                'zip_codes': [],
                'active_listings': [],
                'past_sales': [],
            }

            # Try to find contact info in bio section
            contact_section = soup.find(class_=re.compile(r'contact|bio'))
            if contact_section:
                agent_data['phone'] = agent_data['phone'] or self._extract_phone(contact_section)
                agent_data['email'] = agent_data['email'] or self._extract_email(contact_section)

            return agent_data

        except Exception as e:
            logger.error(f"Error scraping The Agency agent {url}: {str(e)}")
            return None

    def scrape_carolwood_roster(self) -> List[Dict]:
        """
        Scrape Carolwood team page
        Target URL: carolwoodre.com/agents
        """
        leads = []
        try:
            base_url = "https://www.carolwoodre.com/agents"
            response = self.session.get(base_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Carolwood typically has agent cards
            agent_cards = soup.find_all(class_=re.compile(r'agent|team-member'))

            for card in agent_cards[:30]:
                agent_data = {
                    'source': 'carolwood',
                    'name': self._extract_text(card, ['.agent-name', '.name', 'h3', 'h4']),
                    'title': self._extract_text(card, ['.agent-title', '.title']),
                    'brokerage': 'Carolwood',
                    'bio': self._extract_text(card, ['.bio', '.agent-bio']),
                    'phone': self._extract_phone(card),
                    'email': self._extract_email(card),
                    'instagram': self._extract_social(card, 'instagram'),
                    'profile_url': self._extract_attr(card, 'a', 'href'),
                    'zip_codes': [],
                    'active_listings': [],
                    'past_sales': [],
                }

                if agent_data['name']:
                    links = card.find_all('a')
                    for link in links:
                        if link.get('href') and 'agent' in link.get('href', '').lower():
                            agent_data['profile_url'] = urljoin(base_url, link['href'])
                            break

                    leads.append(agent_data)
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error scraping Carolwood: {str(e)}")

        return leads

    def scrape_all_brokerages(self) -> List[Dict]:
        """Scrape all configured brokerages"""
        all_leads = []

        logger.info("Scraping Compass...")
        compass_leads = self.scrape_compass_teams()
        all_leads.extend(compass_leads)

        logger.info("Scraping The Agency...")
        agency_leads = self.scrape_the_agency_teams()
        all_leads.extend(agency_leads)

        logger.info("Scraping Carolwood...")
        carolwood_leads = self.scrape_carolwood_roster()
        all_leads.extend(carolwood_leads)

        # Dedupe by URL or name
        seen = set()
        unique_leads = []
        for lead in all_leads:
            key = lead.get('profile_url') or lead.get('name')
            if key and key not in seen:
                seen.add(key)
                unique_leads.append(lead)

        logger.info(f"Found {len(unique_leads)} unique leads from brokerages")
        return unique_leads

    def _extract_text(self, element, selectors) -> Optional[str]:
        """Extract text from element using multiple selectors"""
        for selector in selectors:
            if isinstance(selector, str):
                el = element.select_one(selector) if hasattr(element, 'select_one') else None
            else:
                continue

            if el:
                text = el.get_text(strip=True)
                if text:
                    return text

        # Try finding by class patterns
        for pattern in ['name', 'title', 'bio', 'team']:
            el = element.find(class_=re.compile(pattern))
            if el:
                text = el.get_text(strip=True)
                if text:
                    return text

        return None

    def _extract_attr(self, element, selector, attr) -> Optional[str]:
        """Extract attribute value from element"""
        try:
            if isinstance(element, str):
                return None

            if hasattr(element, 'select_one'):
                el = element.select_one(selector)
                if el:
                    return el.get(attr)
            elif hasattr(element, 'find'):
                el = element.find(lambda x: selector in str(x.get(attr, '')) if x.has_attr(attr) else False)
                if el:
                    return el.get(attr)
        except:
            pass
        return None

    def _extract_email(self, element) -> Optional[str]:
        """Extract email from element"""
        try:
            text = element.get_text() if hasattr(element, 'get_text') else str(element)
            emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
            # Filter out common non-personal emails
            personal_emails = [e for e in emails if 'info@' not in e and 'support@' not in e]
            return personal_emails[0] if personal_emails else emails[0] if emails else None
        except:
            return None

    def _extract_phone(self, element) -> Optional[str]:
        """Extract phone number from element"""
        try:
            text = element.get_text() if hasattr(element, 'get_text') else str(element)
            # Match various phone formats
            phones = re.findall(r'[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4}', text)
            return phones[0] if phones else None
        except:
            return None

    def _extract_social(self, element, platform: str) -> Optional[str]:
        """Extract social media link from element"""
        try:
            text = str(element) if not hasattr(element, 'get_text') else element.get_text()

            if platform == 'instagram':
                # Look for Instagram links or @mentions
                links = re.findall(r'(?:instagram\.com/|ig\.com/|instagram\.com/)[^\s"\']+', text)
                if links:
                    return links[0]
                handles = re.findall(r'@([a-zA-Z0-9_]+)', text)
                return handles[0] if handles else None

            elif platform == 'linkedin':
                links = re.findall(r'(?:linkedin\.com/.*\?|linkedin\.com/in/)[^\s"\']+', text)
                return links[0] if links else None

        except:
            pass
        return None