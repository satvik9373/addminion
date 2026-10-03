"""
Enrichment providers. Each provider returns contact fields it DISCOVERED
(never fabricated) as a dict with optional keys: phone, email, instagram,
phone_source, phone_type. Providers are constructor-injectable so additional
public/professional sources can be plugged in without touching the dashboard,
database, scoring, Sheets sync, or outreach runner.
"""

from .scraped_data import ScrapedDataProvider
from .realtor_profile import RealtorProfileProvider

__all__ = ['ScrapedDataProvider', 'RealtorProfileProvider']
