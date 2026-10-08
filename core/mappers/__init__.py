"""Mappings between legacy provider shapes and domain models."""

from .legacy import (
    lead_from_mapping,
    enrichment_result_from_mapping,
    qualification_result_from_mapping,
)

__all__ = [
    'lead_from_mapping',
    'qualification_result_from_mapping',
    'enrichment_result_from_mapping',
]
