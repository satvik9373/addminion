"""
Provider: existing scraper data.

The current scrapers (Realtor/Brokerage/Zillow direct profile pages) already
extract phone/email/instagram in many cases. This provider surfaces whatever
contact fields are already present on the lead so enrichment never discards
data the existing pipeline captured — and never pays for a source that already
has the answer.
"""

from typing import Dict


class ScrapedDataProvider:
    """Reads contact fields already stored on the lead from the scrapes."""

    name = 'ScrapedDataProvider'
    source = 'scraped'

    def enrich(self, lead: Dict) -> Dict:
        result = {}
        if lead.get('phone'):
            result['phone'] = str(lead['phone'])
            result['phone_source'] = self.source
            result['phone_type'] = lead.get('phone_type') or 'unknown'
        if lead.get('email'):
            result['email'] = lead['email']
        if lead.get('instagram'):
            result['instagram'] = lead['instagram']
        return result
