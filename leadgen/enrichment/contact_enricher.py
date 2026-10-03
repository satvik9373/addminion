"""
ContactEnricher — find professional/public contact info for a qualified lead.

Runs a chain of provider objects; each returns only contact fields it actually
discovered. Nothing is fabricated: if no provider finds a value, the field is
absent. Provider failures are isolated per-lead so one bad lead (or one slow
source) never stops the remaining leads.

Design constraints honored:
    - Pure: no direct database / dashboard / Sheets / outreach coupling.
      The orchestrator (LeadGenSystem.run_contact_enrichment) handles DB reads
      and writes; this class just decides WHAT was found.
    - Rate-limited: a configurable delay between provider fetches and a cap on
      leads per run (config CONTACT_ENRICHMENT_*).
    - Phone normalization to E.164; unparseable values are preserved in
      phone_raw instead of being corrupted.
    - phone_verified is never set to 1 — no provider verifies today.
"""

import logging
import time
from typing import Dict, List, Optional

from .phone_utils import normalize_phone
from .providers import RealtorProfileProvider, ScrapedDataProvider

logger = logging.getLogger(__name__)

# enrichment_status values
ENRICHED = 'enriched'      # all of phone+email+instagram discovered
PARTIAL = 'partial'        # at least one channel discovered
NO_CONTACT = 'no_contact'  # nothing discovered
FAILED = 'failed'          # enrichment itself errored for this lead


def default_providers(config) -> List:
    """Provider chain used in production: existing scraped data first, then the
    free public Realtor profile page. Order matters for priority display."""
    providers = [ScrapedDataProvider()]
    try:
        from ..scrapers.realtor_scraper import RealtorScraper
        providers.append(RealtorProfileProvider(RealtorScraper()))
    except Exception as e:
        logger.warning('[enrich] RealtorProfileProvider unavailable: %s', e)
    return providers


def classify_status(contact: Dict) -> str:
    """Derive enrichment_status from what was discovered."""
    if not contact:
        return NO_CONTACT
    has_phone = bool(contact.get('phone'))
    has_email = bool(contact.get('email'))
    has_instagram = bool(contact.get('instagram'))
    if has_phone and has_email and has_instagram:
        return ENRICHED
    if has_phone or has_email or has_instagram:
        return PARTIAL
    return NO_CONTACT


class ContactEnricher:
    def __init__(self, config, providers: Optional[List] = None):
        self.config = config
        self.providers = providers if providers is not None else default_providers(config)
        self.max_leads = getattr(config, 'CONTACT_ENRICHMENT_MAX_LEADS_PER_RUN', 50)
        self.delay = getattr(config, 'CONTACT_ENRICHMENT_DELAY_SECONDS', 1.0)

    def enrich_lead(self, lead: Dict) -> Dict:
        """Enrich one lead. Returns {phone?, phone_type?, phone_source?,
        phone_verified, phone_raw?, email?, instagram?, sources: [...]}."""
        result: Dict = {'sources': []}

        for provider in self.providers:
            try:
                found = provider.enrich(lead)
            except Exception as e:
                logger.warning('[enrich] provider %s failed for lead %s: %s',
                               getattr(provider, 'name', provider), lead.get('id'), e)
                result.setdefault('provider_errors', []).append(
                    f"{getattr(provider, 'name', provider)}: {e}")
                continue
            if not found:
                continue

            result['sources'].append(getattr(provider, 'source', 'unknown'))

            # A provider can report it was BLOCKED (rather than discovering
            # nothing). Record that so the caller classifies the lead as
            # 'failed' instead of a misleading 'no contact' — while still
            # keeping any real contact fields this provider returned.
            p_err = found.get('provider_error')
            if p_err:
                result.setdefault('provider_errors', []).append(
                    f"{getattr(provider, 'name', provider)}: {p_err}")

            for key in ('email', 'instagram'):
                val = found.get(key)
                if val and not result.get(key):
                    result[key] = str(val)

            if found.get('phone'):
                phone = str(found['phone'])
                if not result.get('phone'):
                    result['phone'] = phone
                    result['phone_raw'] = phone
                    result['phone_source'] = found.get('phone_source') or getattr(provider, 'source', 'unknown')
                    result['phone_type'] = found.get('phone_type') or 'unknown'
                else:
                    # Prefer a more specific type (business) over 'unknown'
                    new_type = found.get('phone_type') or 'unknown'
                    if result.get('phone_type') in (None, 'unknown') and new_type != 'unknown':
                        result['phone_type'] = new_type

        # Normalize the discovered phone to E.164. If it cannot be normalized
        # confidently, keep the trimmed original in `phone` AND the raw string
        # in `phone_raw` (never corrupt the number).
        if result.get('phone'):
            raw = result['phone']
            norm = normalize_phone(raw)
            if norm:
                result['phone'] = norm
                result['phone_raw'] = raw
            else:
                result['phone'] = raw.strip()
                result['phone_raw'] = raw

        if result.get('phone'):
            result['phone_verified'] = 0  # never claim verification we don't have

        return result

    def enrich_leads(self, leads: List[Dict]) -> List[Dict]:
        """Enrich many leads with per-lead failure isolation + rate limiting.
        Returns a list of {'lead', 'contact', 'error?'} for every input lead."""
        results = []
        for idx, lead in enumerate(leads):
            if idx:
                time.sleep(self.delay)
            try:
                results.append({'lead': lead, 'contact': self.enrich_lead(lead)})
            except Exception as e:
                logger.error('[enrich] lead %s failed: %s', lead.get('id'), e)
                results.append({'lead': lead, 'contact': {}, 'error': str(e)})
        return results
