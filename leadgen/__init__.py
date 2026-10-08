"""
LeadGen System - Automated Lead Generation for Luxury Real Estate Agents

A system that scrapes leads based on ICP criteria, scores them, and runs
automated outreach campaigns following the weekly rhythm defined in the ICP doc.

Weekly workflow:
- Mon: Build 50-contact list by signal
- Tue: Demo batch day (record 8-10 Looms)
- Wed-Thu: IG engagement, DMs, email outreach
- Fri: Follow-ups and pipeline review
- Sun: Open house circuit
"""

__version__ = '0.1.0'
__author__ = 'Ember Systems'

from application.legacy_pipeline import LeadGenSystem

__all__ = ['LeadGenSystem']