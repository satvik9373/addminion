"""Compatibility package for the isolated legacy outreach integrations."""

from integrations.legacy_outreach.demo_generator import DemoGenerator
from integrations.legacy_outreach.email_sender import EmailSender
from integrations.legacy_outreach.instagram_dm import InstagramDM

__all__ = ['EmailSender', 'InstagramDM', 'DemoGenerator']
