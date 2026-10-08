"""Compatibility imports for centralized application configuration."""

from config.settings import (
    BUYING_TRIGGERS,
    EMAIL_TEMPLATES,
    FINANCIAL_INDICATORS,
    ICP_FIT,
    INSTAGRAM_DM_TEMPLATES,
    SCORING_WEIGHTS,
    SHEETS_TABS,
    Config,
    config,
)

__all__ = [
    'Config',
    'config',
    'SCORING_WEIGHTS',
    'BUYING_TRIGGERS',
    'FINANCIAL_INDICATORS',
    'ICP_FIT',
    'EMAIL_TEMPLATES',
    'INSTAGRAM_DM_TEMPLATES',
    'SHEETS_TABS',
]
