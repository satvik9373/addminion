"""
Contact enrichment for the Lead Generation pipeline.

Exposes the provider-based ContactEnricher and phone normalization helpers so
Lead Generation can make qualified leads contactable (phone / email / instagram)
before the final Google Sheets sync.
"""

from .phone_utils import is_valid_phone, normalize_phone
from .contact_enricher import (ContactEnricher, classify_status,
                               default_providers, ENRICHED, PARTIAL,
                               NO_CONTACT, FAILED)
from .providers import RealtorProfileProvider, ScrapedDataProvider

__all__ = [
    'ContactEnricher', 'classify_status', 'default_providers',
    'normalize_phone', 'is_valid_phone',
    'ScrapedDataProvider', 'RealtorProfileProvider',
    'ENRICHED', 'PARTIAL', 'NO_CONTACT', 'FAILED',
]
