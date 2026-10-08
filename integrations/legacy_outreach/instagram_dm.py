"""
Instagram DM Automation
Automates Instagram outreach for High/Medium score leads
Follows the script pattern from the ICP doc:
1. Comment-warm target accounts (3-5 days)
2. Send DM after engagement
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Dict, List, Optional
import logging
import time
import json
import os
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class GraphAPIClient:
    """
    Instagram Graph API client using the long-lived access token.

    IMPORTANT LIMITATION: The Graph API only allows sending DMs to users who
    have ALREADY messaged the business account (within the 24h window) or via
    approved template messages. It CANNOT send cold/unsolicited DMs.

    Use case here: warm follow-ups with leads who have already engaged, and
    token/account validation. Cold outreach uses the Selenium browser path.
    """

    GRAPH_URL = 'https://graph.instagram.com'

    def __init__(self, config):
        self.config = config
        self.token = config.INSTA_ACCESS_TOKEN
        self.ig_id = config.INSTA_IG_ID

    def has_token(self) -> bool:
        return bool(self.token)

    def validate_token(self) -> Dict:
        """
        Validate the token and return connected account info.
        Returns {ok, ig_id, username, name, error}
        """
        if not self.token:
            return {'ok': False, 'error': 'No INSTAGRAM_ACCESS_TOKEN configured'}

        try:
            import requests
            resp = requests.get(
                f'{self.GRAPH_URL}/me',
                params={
                    'fields': 'id,username,name,account_type,media_count',
                    'access_token': self.token,
                },
                timeout=15,
            )
            data = resp.json()

            if resp.status_code == 200 and 'id' in data:
                # Cache the IG user id so senders don't need to set it manually
                self.ig_id = data.get('id', self.ig_id)
                return {
                    'ok': True,
                    'ig_id': data.get('id'),
                    'username': data.get('username'),
                    'name': data.get('name'),
                    'account_type': data.get('account_type'),
                    'media_count': data.get('media_count'),
                }

            error = data.get('error', {}).get('message', resp.text[:200])
            return {'ok': False, 'error': error}

        except Exception as e:
            return {'ok': False, 'error': f'Request failed: {str(e)}'}

    def send_dm(self, recipient_ig_id: str, message: str) -> Dict:
        """
        Send a DM via the Graph API.
        Only works if recipient has an existing conversation with the business
        (recipient messaged first within 24h), or is allowed by a template.

        recipient_ig_id: the Instagram user id of the recipient (NOT their handle)
        """
        if not self.token:
            return {'ok': False, 'error': 'No INSTAGRAM_ACCESS_TOKEN configured'}
        if not self.ig_id:
            # Try to resolve the sender id from the token
            validation = self.validate_token()
            if not validation.get('ok'):
                return {'ok': False, 'error': validation.get('error')}

        try:
            import requests
            resp = requests.post(
                f'{self.GRAPH_URL}/{self.ig_id}/messages',
                params={'access_token': self.token},
                json={
                    'recipient': {'id': str(recipient_ig_id)},
                    'message': {'text': message},
                },
                timeout=15,
            )
            data = resp.json()

            if resp.status_code == 200 and 'message_id' in data:
                return {'ok': True, 'message_id': data['message_id']}

            error = data.get('error', {}).get('message', resp.text[:200])
            return {'ok': False, 'error': error}

        except Exception as e:
            return {'ok': False, 'error': f'Request failed: {str(e)}'}


class InstagramDM:
    def __init__(self, config):
        self.config = config
        self.dm_history_path = 'data/sent_dms.json'
        self.dm_history = self._load_dm_history()
        self.driver = None
        self.api = GraphAPIClient(config)

    def _load_dm_history(self) -> Dict:
        """Load DM history from file"""
        if os.path.exists(self.dm_history_path):
            try:
                with open(self.dm_history_path, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_dm_history(self):
        """Save DM history to file"""
        os.makedirs(os.path.dirname(self.dm_history_path), exist_ok=True)
        with open(self.dm_history_path, 'w') as f:
            json.dump(self.dm_history, f, indent=2, default=str)

    def init_driver(self, headless: bool = False):
        """Initialize Chrome WebDriver for Instagram"""
        chrome_options = Options()

        if headless:
            chrome_options.add_argument('--headless')

        # Add various options to appear less like a bot
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extension=false')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument(f'--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # Disable automation indicators
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        return self.driver

    def login(self, username: str = None, password: str = None) -> bool:
        """Login to Instagram"""
        username = username or self.config.INSTA_USERNAME
        password = password or self.config.INSTA_PASSWORD

        if not username or not password:
            logger.error("Instagram credentials not provided")
            return False

        if not self.driver:
            self.init_driver()

        try:
            logger.info(f"Logging in as {username}...")
            self.driver.get("https://www.instagram.com/accounts/login/")
            time.sleep(3)

            # Wait for login form
            username_field = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            password_field = self.driver.find_element(By.NAME, "password")

            username_field.send_keys(username)
            password_field.send_keys(password)

            # Click login
            login_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            login_button.click()

            # Wait for login to complete
            time.sleep(5)

            # Check if login was successful
            if "login" not in self.driver.current_url:
                logger.info("Login successful")
                return True
            else:
                logger.error("Login failed")
                return False

        except Exception as e:
            logger.error(f"Error logging in: {str(e)}")
            return False

    def comment_warm_account(self, instagram_handle: str, comments: List[str] = None) -> bool:
        """
        Comment on target account's posts for 3-5 days before DM
        Following the ICP doc: 'Days 1-4: follow, meaningfully comment on 2-3 listing posts'
        """
        if not self.driver:
            if not self.login():
                return False

        if not comments:
            # Use generic meaningful comments about property/listing
            comments = [
                "Stunning shot! That lighting is incredible. 📸",
                "This is absolutely breathtaking! That view though... 😍",
                "The architecture here is mesmerizing. Great capture!",
                "Incredible property! That [specific detail] really stands out.",
                "Absolutely stunning. The attention to detail is impeccable.",
            ]

        try:
            logger.info(f"Comment warminG {instagram_handle}...")
            url = f"https://www.instagram.com/{instagram_handle}/"
            self.driver.get(url)
            time.sleep(3)

            # Check if account exists
            error_check = self.driver.find_elements(By.XPATH, "//div[contains(text(), 'Sorry, this page')]")
            if error_check:
                logger.warning(f"Account {instagram_handle} not found")
                return False

            # Check if we already follow
            follow_button = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Follow') or contains(text(), 'Following')]")
            if not follow_button:
                logger.warning(f"Could not find follow button for {instagram_handle}")
                return False

            # Follow if not already following
            if "Follow" in follow_button[0].text:
                follow_button[0].click()
                logger.info(f"Followed {instagram_handle}")
                time.sleep(2)

            # Find recent posts (not stories/highlights)
            posts = self.driver.find_elements(By.XPATH, "//div[@role='link']//img")

            # Comment on first 2-3 posts
            comment_count = 0
            for post_img in posts[:10]:  # Limit to first 10
                if comment_count >= 3:  # Comment on 2-3 posts as per ICP
                    break

                try:
                    # Click on the post to open it
                    post_img.click()
                    time.sleep(2)

                    # Find comment box and add comment
                    comment_box = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//textarea[@placeholder='Add a comment...']"))
                    )

                    if comment_box:
                        # Add a meaningful comment (not about the pitch)
                        comment_text = comments[comment_count % len(comments)]
                        comment_box.send_keys(comment_text)

                        # Submit comment
                        post_button = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Post')]")
                        if post_button:
                            post_button[0].click()
                            comment_count += 1
                            logger.info(f"Commented '{comment_text}' on post")
                            time.sleep(3)

                    # Close the post
                    close_button = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Close')]")
                    if close_button:
                        close_button[0].click()
                    time.sleep(1)

                except Exception as e:
                    logger.debug(f"Could not comment on a post: {str(e)}")
                    # Try to close any open post
                    close_buttons = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Close')]")
                    for btn in close_buttons:
                        try:
                            btn.click()
                        except:
                            pass
                    time.sleep(2)

            return comment_count > 0

        except Exception as e:
            logger.error(f"Error comment warming {instagram_handle}: {str(e)}")
            return False

    def send_dm(self, instagram_handle: str, lead: Dict, is_open_house_lead: bool = False) -> bool:
        """
        Send DM to target account after warming
        Following ICP script patterns
        """
        if not self.driver:
            if not self.login():
                return False

        try:
            # First, comment-warm the account
            warmed = self.comment_warm_account(instagram_handle)
            if not warmed:
                logger.warning(f"Could not warm account {instagram_handle}, attempting DM anyway...")

            # Wait a bit between warming and DM
            time.sleep(5)

            # Navigate to DMs
            self.driver.get("https://www.instagram.com/direct/inbox/")
            time.sleep(3)

            # Start new conversation
            new_message_button = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(@aria-label, 'New')]"))
            )
            new_message_button.click()
            time.sleep(2)

            # Search for the user
            search_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Search...']"))
            )
            search_input.send_keys(instagram_handle)
            time.sleep(3)

            # Select the user
            user_select = self.driver.find_elements(By.XPATH, f"//div[contains(text(), '{instagram_handle}')]")
            if user_select:
                user_select[0].click()
                time.sleep(2)
            else:
                logger.error(f"Could not find {instagram_handle} in search")
                return False

            # Click next
            next_button = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Next')]")
            if next_button:
                next_button[0].click()
                time.sleep(2)

            # Prepare message based on lead type
            if is_open_house_lead:
                message = self._format_open_house_message(lead)
            else:
                message = self._format_initial_message(lead)

            # Find message input and send
            message_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//textarea[@placeholder='Message...']"))
            )
            message_input.send_keys(message)
            time.sleep(1)

            # Send
            send_button = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Send')]")
            if send_button:
                send_button[0].click()

            # Record DM sent
            lead_id = lead.get('id', lead.get('profile_url', ''))
            if lead_id not in self.dm_history:
                self.dm_history[lead_id] = []

            self.dm_history[lead_id].append({
                'instagram_handle': instagram_handle,
                'message': message,
                'sent_at': datetime.now().isoformat(),
                'lead_data': {
                    'name': lead.get('name'),
                    'listing_street': lead.get('listing_street', ''),
                    'specific_detail': lead.get('specific_detail', ''),
                },
            })
            self._save_dm_history()

            logger.info(f"Sent DM to {instagram_handle}")
            return True

        except Exception as e:
            logger.error(f"Error sending DM to {instagram_handle}: {str(e)}")
            return False

    def _format_initial_message(self, lead: Dict) -> str:
        """
        Format initial DM message using ICP script template
        Uses Instagram DM track from config
        """
        from ..config import INSTAGRAM_DM_TEMPLATES

        template = INSTAGRAM_DM_TEMPLATES['initial']

        # Extract data for template
        first_name = lead.get('name', 'there').split()[0] if lead.get('name') else 'there'

        # Try to get listing info
        listings = lead.get('active_listings', [])
        first_listing = listings[0] if listings else {}

        if isinstance(first_listing, dict):
            street = first_listing.get('address', 'your listing').split(',')[0]
            # Extract a specific detail
            detail = self._extract_specific_detail(first_listing.get('price', ''), first_listing.get('address', ''))
        else:
            street = 'your listing'
            detail = 'that view'

        return template.format(
            first_name=first_name,
            street=street,
            specific_detail=detail
        )

    def _format_open_house_message(self, lead: Dict) -> str:
        """Format open house DM message"""
        from ..config import INSTAGRAM_DM_TEMPLATES

        template = INSTAGRAM_DM_TEMPLATES['open_house']

        street = lead.get('listing_street', lead.get('address', 'the listing'))
        return template.format(
            street=street
        )

    def _extract_specific_detail(self, price: str, address: str) -> str:
        """Extract a specific detail to mention in DM for personalization"""
        details = ['that kitchen', 'that staircase', 'those doors', 'that lighting',
                   'that pool', 'that view', 'that entryway', 'those windows']

        # Try to infer from address
        if 'ocean' in address.lower():
            return 'that ocean view'
        elif 'park' in address.lower():
            return 'that park view'
        elif 'hills' in address.lower() or 'ridge' in address.lower():
            return 'that city light'

        # Default to a generic specific detail
        return 'that [specific detail] shot'

    def validate_setup(self) -> Dict:
        """
        Validate Instagram setup.
        Returns info about both the token (Graph API) and browser path.
        """
        info = {
            'token_configured': bool(self.config.INSTA_ACCESS_TOKEN),
            'browser_credentials_configured': bool(self.config.INSTA_USERNAME and self.config.INSTA_PASSWORD),
            'token': None,
        }

        if info['token_configured']:
            info['token'] = self.api.validate_token()

        return info

    def send_dm_via_api(self, recipient_ig_id: str, lead: Dict, message: str = None) -> bool:
        """
        Send a DM via the Graph API (warm leads only — recipient must have an
        existing conversation with the account). Records to DM history.
        """
        if not message:
            message = self._format_initial_message(lead)

        result = self.api.send_dm(recipient_ig_id, message)
        if not result.get('ok'):
            logger.error(f"Graph API DM failed: {result.get('error')}")
            return False

        # Record in history
        lead_id = lead.get('id', lead.get('profile_url', ''))
        if lead_id not in self.dm_history:
            self.dm_history[lead_id] = []

        self.dm_history[lead_id].append({
            'instagram_handle': recipient_ig_id,
            'channel': 'graph_api',
            'message': message,
            'sent_at': datetime.now().isoformat(),
        })
        self._save_dm_history()

        logger.info(f"Sent Graph API DM to {recipient_ig_id} (message_id={result.get('message_id')})")
        return True

    def can_send_next_dm(self, lead_id: str) -> bool:
        """Check if we can send another DM to this lead"""
        if lead_id not in self.dm_history:
            return True

        dms_sent = self.dm_history[lead_id]
        if len(dms_sent) >= 2:  # Limit to 2 DMs per lead
            return False

        # Check timing - wait at least 24 hours between DMs
        if dms_sent:
            last_dm = datetime.fromisoformat(dms_sent[-1]['sent_at'])
            hours_since = (datetime.now() - last_dm).total_seconds() / 3600
            if hours_since < 24:
                return False

        return True

    def send_all_pending_dms(self, leads: List[Dict], open_house_leads: List[Dict] = None):
        """Send all pending DMs to qualified leads"""
        results = {
            'sent': 0,
            'skipped': 0,
            'failed': 0,
        }

        # Initialize browser if needed
        if not self.driver:
            if not self.login():
                logger.error("Could not login to Instagram")
                return results

        # Send DMs to regular leads with Instagram handles
        for lead in leads:
            instagram_handle = lead.get('instagram', '')
            if not instagram_handle:
                # Try to extract handle from social links
                instagram_handle = self._extract_instagram_handle(lead)

            if not instagram_handle:
                continue

            # Skip if already contacted
            lead_id = lead.get('id', lead.get('profile_url', ''))
            if not self.can_send_next_dm(lead_id):
                results['skipped'] += 1
                continue

            is_open_house = lead_id in (open_house_leads or [])
            success = self.send_dm(instagram_handle, lead, is_open_house)
            if success:
                results['sent'] += 1
            else:
                results['failed'] += 1

        return results

    def _extract_instagram_handle(self, lead: Dict) -> Optional[str]:
        """Extract Instagram handle from lead data"""
        # Check various fields that might contain Instagram handle
        fields_to_check = ['instagram', 'instagram_handle', 'ig', 'social_instagram']

        for field in fields_to_check:
            value = lead.get(field, '')
            if value:
                # Handle various formats
                if isinstance(value, str):
                    # Direct handle
                    if not value.startswith('http'):
                        return value.replace('@', '')
                    # URL format
                    handle_match = re.search(r'instagram\.com/([^/?]+)', value)
                    if handle_match:
                        return handle_match.group(1)

        # Try bio/description
        bio = lead.get('bio', '') or ''
        handle_match = re.search(r'instagram\.com/([a-zA-Z0-9_.]+)', bio)
        if handle_match:
            return handle_match.group(1)

        return None

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()