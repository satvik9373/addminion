"""
Provider: public Realtor.com profile page.

Reuses the existing RealtorScraper._scrape_realtor_agent() (free, no new API)
to pull phone/email/instagram from a lead's public agent profile. That method
already applies its own request timeout and returns None on failure, so this
provider stays consistent with the existing scraping infrastructure and never
raises on a network problem.

phone_type is 'business' because the value comes from a professional public
profile. phone_verified is left unset — we have no verification mechanism.
"""

import logging
from typing import Dict, Optional

from discovery.legacy_scrapers.realtor_scraper import RealtorScraper

logger = logging.getLogger(__name__)


class RealtorProfileProvider:
    name = 'RealtorProfileProvider'
    source = 'website'

    def __init__(self, realtor_scraper: Optional[RealtorScraper] = None):
        self.scraper = realtor_scraper or RealtorScraper()

    def enrich(self, lead: Dict) -> Dict:
        url = lead.get('profile_url')
        if not url or 'realtor.com' not in str(url):
            return {}
        try:
            # checked variant returns (http_status, data) so a 403/429 block or
            # 404 is distinguishable from a page with genuinely no contact info.
            status, data = self.scraper._scrape_realtor_agent_checked(str(url))
        except Exception as e:  # never let one fetch break the whole run
            logger.warning('[enrich] realtor profile fetch failed for %s: %s',
                           lead.get('id'), e)
            return {'provider_error': f'realtor.com profile fetch failed: {e}'}
        if status is None:
            return {'provider_error': 'realtor.com profile fetch/parse error (no HTTP status)'}
        if status != 200:
            # Do NOT report this as 'no contact' — we were blocked, not informed.
            logger.warning('[enrich] realtor.com blocked profile fetch for %s (HTTP %s)',
                           lead.get('id'), status)
            return {'provider_error': f'realtor.com refused profile fetch (HTTP {status})'}
        if not data:
            return {}

        result = {}
        if data.get('phone'):
            result['phone'] = str(data['phone'])
            result['phone_source'] = self.source
            result['phone_type'] = 'business'
        if data.get('email'):
            result['email'] = data['email']
        if data.get('instagram'):
            result['instagram'] = data['instagram']
        return result
