"""Compatibility package for legacy discovery providers."""

from discovery.legacy_scrapers import (
    BrokerageScraper,
    JobPostScraper,
    RealtorScraper,
    ZillowScraper,
)

__all__ = [
    'BrokerageScraper',
    'JobPostScraper',
    'RealtorScraper',
    'ZillowScraper',
]
