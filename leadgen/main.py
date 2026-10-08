"""Compatibility import for the legacy pipeline entry point.

The implementation now lives in :mod:`application.legacy_pipeline`.
"""

from application.legacy_pipeline import LeadGenSystem, main

__all__ = ['LeadGenSystem', 'main']
