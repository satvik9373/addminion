"""
Google Sheets Sync
Syncs leads to Google Sheets with proper tab organization
Following the ICP doc structure with separate tabs for scoring categories
"""

import json
import logging
from typing import List, Dict
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


class SheetsSync:
    """Syncs lead data to Google Sheets"""

    def __init__(self, config):
        self.config = config
        self.creds = None
        self.client = None
        self.service = None

    def authenticate(self) -> bool:
        """Authenticate with Google Sheets API"""
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
            from google.auth.exceptions import GoogleAuthError

            SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

            if not self.config.GOOGLE_SHEETS_CREDENTIALS_PATH:
                logger.error("Google Sheets credentials path not configured")
                return False

            try:
                creds = Credentials.from_service_account_file(
                    self.config.GOOGLE_SHEETS_CREDENTIALS_PATH,
                    scopes=SCOPES
                )
                self.creds = creds
                self.service = build('sheets', 'v4', credentials=creds)
                logger.info("Google Sheets authentication successful")
                return True

            except GoogleAuthError as e:
                logger.error(f"Google authentication error: {str(e)}")
                return False
            except FileNotFoundError:
                logger.error(f"Credentials file not found: {self.config.GOOGLE_SHEETS_CREDENTIALS_PATH}")
                return False

        except ImportError as e:
            logger.error(f"Google API libraries not installed: {str(e)}")
            logger.info("Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
            return False

    def sync_leads_to_tab(self, tab_name: str, leads: List[Dict]) -> bool:
        """Sync leads to a specific tab in the spreadsheet"""
        if not self.service:
            if not self.authenticate():
                return False

        try:
            # Prepare data for the tab
            data = self._prepare_lead_data(leads)

            # Format for Sheets API (header row + data rows)
            values = [self._get_header_row()] + data

            # Build the spreadsheet update body
            body = {
                'values': values
            }

            # Clear existing content and update
            range_name = f"{tab_name}!A1:AC2000"

            self.service.spreadsheets().values().clear(
                spreadsheetId=self.config.GOOGLE_SHEETS_ID,
                range=range_name
            ).execute()

            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.config.GOOGLE_SHEETS_ID,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()

            logger.info(f"Updated {len(leads)} leads in tab '{tab_name}'")
            return True

        except Exception as e:
            logger.error(f"Error syncing to tab '{tab_name}': {str(e)}")
            return False

    def _get_header_row(self) -> List[str]:
        """Get the header row for the spreadsheet"""
        return [
            'Lead Name',
            'Company/Brokerage',
            'Role/Title',
            'ICP Tier',
            'Score',
            'Category',
            'Triggers',
            'Email',
            'Phone',
            'Phone Type',
            'Phone Source',
            'Phone Verified',
            'Phone Last Checked',
            'Instagram',
            'LinkedIn',
            'Website',
            'Zip Code',
            'Source',
            'Active Listings',
            'Annual Volume Est',
            'Monthly Spend Est',
            'Demo Link',
            'Last Email Status',
            'Last DM Status',
            'Lead Status',
            'First Contact',
            'Last Contact',
            'Notes',
            'Enrichment Status',
        ]

    def _prepare_lead_data(self, leads: List[Dict]) -> List[List[str]]:
        """Prepare lead data for spreadsheet rows"""
        rows = []

        for lead in leads:
            # Format score breakdown
            triggers_str = self._format_triggers(lead)

            # Format active listings
            listings_str = self._format_listings(lead)

            # Format dates
            first_contact = self._format_date(lead.get('first_contact_attempt'))
            last_contact = self._format_date(lead.get('last_contact_attempt'))

            row = [
                lead.get('name', ''),
                lead.get('brokerage', ''),
                lead.get('title', lead.get('role', '')),
                lead.get('icp_tier', ''),
                str(lead.get('score', '')),
                lead.get('category', ''),
                triggers_str,
                lead.get('email', ''),
                lead.get('phone', ''),
                lead.get('phone_type', ''),
                lead.get('phone_source', ''),
                lead.get('phone_verified', ''),
                lead.get('phone_last_checked', ''),
                lead.get('instagram', ''),
                lead.get('linkedin', ''),
                lead.get('website', ''),
                lead.get('zip_code', '') or ', '.join(map(str, lead.get('zip_codes', []))),
                lead.get('source', ''),
                listings_str,
                self._format_money(lead.get('annual_volume')),
                lead.get('monthly_spend', ''),
                lead.get('loom_link', ''),
                lead.get('email_status', ''),
                lead.get('instagram_dm_status', ''),
                lead.get('status', ''),
                first_contact,
                last_contact,
                self._generate_notes(lead),
                lead.get('enrichment_status', ''),
            ]

            rows.append(row)

        return rows

    def _format_triggers(self, lead: Dict) -> str:
        """Format trigger information"""
        triggers = []

        # Check for triggers
        if lead.get('trigger'):
            triggers.append(lead['trigger'])
        elif lead.get('hiring_indication'):
            triggers.append('Hiring ISA')

        if lead.get('active_listings'):
            try:
                listings = json.loads(lead['active_listings']) if isinstance(lead['active_listings'], str) else lead['active_listings']
                if any(l.get('price', '').startswith('$5') or '5,' in str(l.get('price', '')).startswith('$5') for l in listings if isinstance(l, dict)):
                    triggers.append('$5M+ Listing')
            except:
                pass

        return ', '.join(triggers) if triggers else 'None'

    def _format_listings(self, lead: Dict) -> str:
        """Format active listings for display"""
        listings = lead.get('active_listings', [])
        if not listings:
            return ''

        try:
            if isinstance(listings, str):
                listings = json.loads(listings)

            if isinstance(listings, list):
                formatted = []
                for listing in listings[:3]:
                    if isinstance(listing, dict):
                        addr = listing.get('address', '')
                        price = listing.get('price', '')
                        formatted.append(f"{addr} ({price})")
                return '; '.join(formatted)
        except:
            pass

        return str(listings)[:100]

    def _format_money(self, amount) -> str:
        """Format money amounts"""
        if not amount:
            return ''

        try:
            amount_float = float(amount)
            if amount_float >= 1_000_000:
                return f"${amount_float / 1_000_000:.1f}M"
            elif amount_float >= 1_000:
                return f"${amount_float / 1_000:.1f}K"
            return f"${amount_float:,.0f}"
        except:
            return str(amount)

    def _format_date(self, date_str: str) -> str:
        """Format date for display"""
        if not date_str:
            return ''

        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime('%m/%d/%Y %I:%M %p')
        except:
            return str(date_str)[:20]

    def _generate_notes(self, lead: Dict) -> str:
        """Generate notes for lead"""
        notes = []

        if lead.get('hiring_indication'):
            notes.append("Hiring ISA - strong signal")
        if lead.get('budget_confirmed'):
            notes.append("Budget confirmed")
        if lead.get('source') == 'job_post':
            notes.append(f"Job post: {lead.get('job_url', 'N/A')}")
        if lead.get('open_house_lead'):
            notes.append("Open house lead")

        # Add score breakdown
        breakdown = lead.get('score_breakdown', {})
        if isinstance(breakdown, str):
            try:
                breakdown = json.loads(breakdown)
            except:
                pass

        if isinstance(breakdown, dict):
            notes.append(f"Financial: {breakdown.get('financial', 0):.1f}, Triggers: {breakdown.get('triggers', 0):.1f}, ICP: {breakdown.get('icp', 0):.1f}")

        return ' | '.join(notes) if notes else ''

    def create_spreadsheet_tabs(self, spreadsheet_id: str = None):
        """Create the tab structure in Google Sheets"""
        if not self.service:
            if not self.authenticate():
                return False

        spreadsheet_id = spreadsheet_id or self.config.GOOGLE_SHEETS_ID

        try:
            # Get current spreadsheet
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()

            existing_sheets = [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]

            # Create missing tabs
            new_sheets = []
            for tab_name in [
                'High Score (15+)',
                'Medium Score (10-14)',
                'Low Score (5-9)',
                'Disqualified (<5)',
                'Interested',
                'Booked Call',
                'Low Scored Leads',
            ]:
                if tab_name not in existing_sheets:
                    new_sheets.append({'properties': {'title': tab_name}})

            if new_sheets:
                body = {
                    'requests': [
                        {
                            'addSheet': {
                                'properties': sheet['properties']
                            }
                        } for sheet in new_sheets
                    ]
                }

                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body=body
                ).execute()

                logger.info(f"Created {len(new_sheets)} new tabs")

            return True

        except Exception as e:
            logger.error(f"Error creating tabs: {str(e)}")
            return False

    def sync_responses_back(self, lead_statuses: List[Dict]):
        """Sync lead status updates back to sheets"""
        # This would update the Google Sheet with latest lead status
        # Implementation depends on how you're tracking responses
        pass