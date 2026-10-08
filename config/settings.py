"""
Configuration file for LeadGen System
All settings should be configured here
"""

import os
from dataclasses import dataclass
from typing import List, Dict

from .env_loader import load_dotenv

# Load .env first so all os.environ.get() calls below see credentials
load_dotenv()

@dataclass
class Config:
    # Environment
    DEBUG: bool = True

    # Google Sheets Configuration
    GOOGLE_SHEETS_CREDENTIALS_PATH: str = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_PATH', '')
    GOOGLE_SHEETS_ID: str = os.environ.get('GOOGLE_SHEETS_ID', '')  # Your spreadsheet ID

    # Email Configuration (SMTP)
    SMTP_SERVER: str = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT: int = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USERNAME: str = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD: str = os.environ.get('SMTP_PASSWORD', '')
    SMTP_USE_TLS: bool = True

    # Instagram Configuration
    INSTA_USERNAME: str = os.environ.get('INSTA_USERNAME', '')
    INSTA_PASSWORD: str = os.environ.get('INSTA_PASSWORD', '')
    INSTA_ACCESS_TOKEN: str = os.environ.get('INSTAGRAM_ACCESS_TOKEN', '')
    INSTA_IG_ID: str = os.environ.get('INSTAGRAM_IG_ID', '')

    # Apify Configuration (for Zillow/Realtor scraping)
    APIFY_API_KEY: str = os.environ.get('APIFY_API_KEY', '')

    # Database
    DATABASE_PATH: str = os.environ.get('DATABASE_PATH', 'data/leadgen.db')

    # Scoring Thresholds
    HIGH_SCORE_THRESHOLD: int = 15
    MEDIUM_SCORE_THRESHOLD: int = 10
    LOW_SCORE_THRESHOLD: int = 5

    # ICP Fit Settings
    TARGET_ZIP_CODES: List[str] = None
    TARGET_BROKERAGES: List[str] = None

    # Email Sequence Settings
    EMAIL_SEQUENCE_DAYS: List[int] = None  # Days when emails are sent: [0, 2, 5, 9, 13]
    EMAIL_REPLY_WAIT_DAYS: int = 2

    # Contact Enrichment Settings
    CONTACT_ENRICHMENT_TTL_HOURS: int = int(os.environ.get('CONTACT_ENRICHMENT_TTL_HOURS', '168'))  # 7 days
    CONTACT_ENRICHMENT_MAX_LEADS_PER_RUN: int = int(os.environ.get('CONTACT_ENRICHMENT_MAX_LEADS_PER_RUN', '50'))
    CONTACT_ENRICHMENT_DELAY_SECONDS: float = float(os.environ.get('CONTACT_ENRICHMENT_DELAY_SECONDS', '1.0'))

    def __post_init__(self):
        if self.TARGET_ZIP_CODES is None:
            self.TARGET_ZIP_CODES = [
                '90210',  # Beverly Hills
                '90077',  # Bel Air
                '90210',  # Brentwood (shares with Beverly Hills)
                '90272',  # Pacific Palisades
                '90265',  # Malibu
                '91302',  # Hidden Hills/Calabasas
                '90402',  # Santa Monica
                '90290',  # Manhattan Beach
            ]

        if self.TARGET_BROKERAGES is None:
            self.TARGET_BROKERAGES = [
                'Compass',
                'The Agency',
                'Sotheby\'s',
                'Coldwell Banker Global Luxury',
                'Carolwood',
                'Westside Estate Agency',
                'Hilton & Hyland',
                'The Beverly Hills Estates',
            ]

        if self.EMAIL_SEQUENCE_DAYS is None:
            self.EMAIL_SEQUENCE_DAYS = [0, 2, 5, 9, 13]  # 5 touches over 14 days

    def validate(self) -> List[str]:
        """Validate configuration and return list of missing items"""
        errors = []

        if not self.GOOGLE_SHEETS_ID:
            errors.append("GOOGLE_SHEETS_ID not configured")
        if not self.SMTP_USERNAME or not self.SMTP_PASSWORD:
            errors.append("SMTP credentials not configured")
        if not self.GOOGLE_SHEETS_CREDENTIALS_PATH or not os.path.exists(self.GOOGLE_SHEETS_CREDENTIALS_PATH):
            errors.append(f"Google Sheets credentials file not found at {self.GOOGLE_SHEETS_CREDENTIALS_PATH}")

        return errors

# Scoring Weights
SCORING_WEIGHTS = {
    'financial_indicators': 30,  # 30% of total score
    'buying_triggers': 40,       # 40% of total score
    'icp_fit': 30,               # 30% of total score
}

# Buying Triggers with Points
BUYING_TRIGGERS = {
    'hiring_isa': 25,            # Hiring ISA or showing assistant
    'new_high_value_listing': 20, # New $5M+ listing in MLS
    'running_zillow_premier': 15, # Running Zillow Premier Agent
    'team_expansion': 12,         # Team expansion announcements
    'recent_independence': 10,    # Just went independent
    'weekend_open_houses': 8,     # Regular weekend open houses
}

# Financial Indicators with Points (max ~25 points)
FINANCIAL_INDICATORS = {
    'transaction_volume_50m_plus': 15,
    'transaction_volume_30m_49m': 12,
    'transaction_volume_20m_29m': 8,
    'avg_sale_2m_plus': 7,
    'avg_sale_1m_1_9m': 4,
    'active_listings_5_plus': 6,
    'active_listings_3_4': 4,
    'active_listings_1_2': 2,
    'monthly_spend_10k_plus': 4,
    'monthly_spend_5k_9k': 2,
}

# ICP Fit with Points (max ~20 points)
ICP_FIT = {
    'icp_tier_1_team': 20,        # $50M+ teams
    'icp_tier_1_brokerage': 15,    # At target brokerages
    'icp_tier_1_zip': 10,          # In target zip codes
    'icp_tier_2_solo': 15,        # $30M+ solo producers
    'icp_tier_3_boutique': 10,    # Boutique brokerages
    'role_ops_director': 18,      # Director of Operations/Team Manager
    'role_team_lead': 15,         # Team Lead/Rainmaker
    'role_solo_agent': 10,        # Solo agent
}

# Outreach Templates
EMAIL_TEMPLATES = {
    'T1': {
        'subject': '{listing_street} listing: Quick idea for {sender_name_first}',
        'body': '''
Hi {first_name},

Saw your ${price}M listing on {listing_street}. I built an AI that answers inquiries on it in 60 seconds, qualifies the buyer's budget and financing, and books showings, nights and weekends included.

Recorded a 2-min demo on your actual listing: {loom_link}

Worth 15 minutes this week?

{decline_text}
'''
    },
    'T2': {
        'subject': 'Quick math on {listing_address}',
        'body': '''
{first_name},

Quick math: your average deal is probably $50K-75K in commission. Agents miss 30-40% of inbound because it lands after hours.

If this saves one deal a year it pays for itself 4x.

Demo's still live: {loom_link}

{decline_text}
'''
    },
    'T3': {
        'subject': 'Before you commit to that ISA hire...',
        'body': '''
{first_name},

Noticed you're hiring an ISA.

Before you commit $60K/year: this does the qualification half of that job 24/7 and never quits mid-escrow.

Happy to show both working together - {calendar_link}

{decline_text}
'''
    },
    'T4': {
        'subject': 'Still open?',
        'body': '''
{first_name},

A 4-hour reply reads as 'not that agent' now.

15 minutes this week? - {calendar_link}

{decline_text}
'''
    },
    'T5': {
        'subject': 'Closing the file',
        'body': '''
{first_name},

Closing the file: the demo comes down Friday.

If it's a priority: {calendar_link}

{decline_text}
'''
    },
}

INSTAGRAM_DM_TEMPLATES = {
    'initial': '''
Yo {first_name}, the {street} listing is unreal, that {specific_detail} shot. Quick one: I build growth systems for luxury agents. Made a 2-min demo of an AI answering inquiries on that exact listing, qualifying budget + booking showings at 2am. Want me to send it?
''',
    'open_house': '''
Beautiful listing on {street}. How are you handling all the inquiries on it? ... That's actually what we do: AI that answers and qualifies them in 60 seconds. Can I text you a 2-minute demo on this exact property?
'''
}

# Google Sheets Tab Names
SHEETS_TABS = {
    'high_score': 'High Score (15+)',
    'medium_score': 'Medium Score (10-14)',
    'low_score': 'Low Score (5-9)',
    'disqualified': 'Disqualified (<5)',
    'no_response': 'No Response',
    'interested': 'Interested',
    'booked_call': 'Booked Call',
}

config = Config()