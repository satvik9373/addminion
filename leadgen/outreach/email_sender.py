"""
Email Sender
Sends automated email sequences using the 5-touch sequence from ICP doc
"""

import smtplib
import ssl
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import json
import os
from jinja2 import Template

logger = logging.getLogger(__name__)

class EmailSender:
    def __init__(self, config):
        self.config = config
        self.sent_history_path = 'data/sent_emails.json'
        self.sent_history = self._load_sent_history()

        # Templates for each touch point
        self.templates = {
            'T1': {
                'subject': "{listing_street} listing: Quick idea for {sender_name_first}",
                'body': """<html><body>
<p>Hi {first_name},</p>

<p>Saw your ${price}M listing on {listing_street}. I built an AI that answers inquiries on it in 60 seconds, qualifies the buyer's budget and financing, and books showings, nights and weekends included.</p>

<p>Recorded a 2-min demo on your actual listing: <a href="{loom_link}">Watch Demo</a></p>

<p>Worth 15 minutes this week?</p>

<p><a href="{calendar_link}">Pick a time</a></p>

<p>{decline_text}</p>
</body></html>"""
            },
            'T2': {
                'subject': "Quick math on {listing_address}",
                'body': """<html><body>
<p>{first_name},</p>

<p>Quick math: your average deal is probably $50K-75K in commission. Agents miss 30-40% of inbound because it lands after hours.</p>

<p>If this saves one deal a year it pays for itself 4x.</p>

<p>Demo's still live: <a href="{loom_link}">Watch Demo</a></p>

<p>{decline_text}</p>
</body></html>"""
            },
            'T3': {
                'subject': "Before you commit to that ISA hire...",
                'body': """<html><body>
<p>{first_name},</p>

<p>Noticed you're hiring an ISA.</p>

<p>Before you commit $60K/year: this does the qualification half of that job 24/7 and never quits mid-escrow.</p>

<p>Happy to show both working together - <a href="{calendar_link}">Schedule a quick call</a></p>

<p>{decline_text}</p>
</body></html>"""
            },
            'T4': {
                'subject': "Still open?",
                'body': """<html><body>
<p>{first_name},</p>

<p>A 4-hour reply reads as 'not that agent' now.</p>

<p>15 minutes this week? - <a href="{calendar_link}">Let's talk</a></p>

<p>{decline_text}</p>
</body></html>"""
            },
            'T5': {
                'subject': "Closing the file",
                'body': """<html><body>
<p>{first_name},</p>

<p>Closing the file: the demo comes down Friday.</p>

<p>If it's a priority: <a href="{calendar_link}">Book now</a></p>

<p>{decline_text}</p>
</body></html>"""
            },
        }

    def _load_sent_history(self) -> Dict:
        """Load sent email history from file"""
        if os.path.exists(self.sent_history_path):
            try:
                with open(self.sent_history_path, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_sent_history(self):
        """Save sent email history to file"""
        os.makedirs(os.path.dirname(self.sent_history_path), exist_ok=True)
        with open(self.sent_history_path, 'w') as f:
            json.dump(self.sent_history, f, indent=2, default=str)

    def send_sequence_email(self, lead: Dict, touch_number: int, loom_link: str = None,
                           calendar_link: str = "https://calendly.com/your-cal-link") -> bool:
        """
        Send a specific touch in the email sequence
        touch_number: 1-5 (T1-T5)
        """
        touch_key = f"T{touch_number}"

        if touch_key not in self.templates:
            logger.error(f"Invalid touch number: {touch_number}")
            return False

        template = self.templates[touch_key]
        template_vars = self._prepare_template_vars(lead, loom_link, calendar_link)

        try:
            # Render subject and body
            subject_template = Template(template['subject'])
            body_template = Template(template['body'])

            subject = subject_template.render(**template_vars)
            body = body_template.render(**template_vars)

            # Send email
            success = self._send_email(
                to_email=lead.get('email', ''),
                subject=subject,
                html_body=body,
                lead_id=lead.get('id', lead.get('profile_url', ''))
            )

            if success:
                # Record sent email
                lead_id = lead.get('id', lead.get('profile_url', ''))
                if lead_id not in self.sent_history:
                    self.sent_history[lead_id] = []

                self.sent_history[lead_id].append({
                    'touch_number': touch_number,
                    'touch_key': touch_key,
                    'subject': subject,
                    'sent_at': datetime.now().isoformat(),
                    'loom_link': loom_link,
                })
                self._save_sent_history()

                logger.info(f"Sent T{touch_number} email to {lead.get('name', 'Unknown')} ({lead.get('email', '')})")
                return True

        except Exception as e:
            logger.error(f"Error sending T{touch_number} email: {str(e)}")
            return False

        return False

    def _prepare_template_vars(self, lead: Dict, loom_link: str, calendar_link: str) -> Dict:
        """Prepare template variables for email rendering"""
        # Extract listing info if available
        listings = lead.get('active_listings', [])
        first_listing = listings[0] if listings else {}

        if isinstance(first_listing, dict):
            price = first_listing.get('price', '$3M+')
            street = first_listing.get('address', lead.get('name', 'your listing'))
        else:
            price = '$3M+'
            street = lead.get('name', 'your listing')

        # Parse price into number for template
        price_num = self._parse_price(street, price)

        return {
            'first_name': lead.get('name', 'there').split()[0] if lead.get('name') else 'there',
            'name': lead.get('name', 'there'),
            'listing_address': street,
            'listing_street': street,
            'price': price_num,
            'loom_link': loom_link or 'https://loom.com/share/placeholder',
            'calendar_link': calendar_link,
            'decline_text': "P.S. If now's not the right time, just ignore this. If you'd prefer I stop reaching out, reply 'STOP' and I'll remove you from all sequences.",
            'sender_name_first': 'Deepak',
            'sender_name': 'Deepak at Ember Agency',
        }

    def _parse_price(self, street: str, price: str) -> str:
        """Parse price for template"""
        # Try to extract a number from price
        numbers = re.findall(r'\d+(?:\.\d+)?', str(price))
        if numbers:
            return numbers[0]
        return '3'  # Default to 3 for template

    def _send_email(self, to_email: str, subject: str, html_body: str, lead_id: str = None) -> bool:
        """Actually send the email via SMTP"""
        if not to_email:
            logger.error("No email address provided")
            return False

        try:
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = self.config.SMTP_USERNAME
            message['To'] = to_email

            # Attach HTML body
            html_part = MIMEText(html_body, 'html')
            message.attach(html_part)

            # Create secure SSL context
            context = ssl.create_default_context()

            # Send email
            with smtplib.SMTP(self.config.SMTP_SERVER, self.config.SMTP_PORT) as server:
                server.starttls(context=context)
                server.login(self.config.SMTP_USERNAME, self.config.SMTP_PASSWORD)
                server.sendmail(self.config.SMTP_USERNAME, to_email, message.as_string())

            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    def get_lead_email_status(self, lead_id: str) -> Dict:
        """Get email sending status for a lead"""
        if lead_id not in self.sent_history:
            return {'sent_count': 0, 'touches': []}

        touches = self.sent_history[lead_id]
        return {
            'sent_count': len(touches),
            'touches': touches,
            'next_touch': len(touches) + 1 if len(touches) < 5 else None,
            'last_sent': touches[-1]['sent_at'] if touches else None,
        }

    def can_send_next_email(self, lead_id: str, sequence_start_date: str = None) -> bool:
        """Check if we can send the next email in sequence"""
        send_history = self.get_lead_email_status(lead_id)
        sent_count = send_history['sent_count']

        # Maximum 5 emails
        if sent_count >= 5:
            return False

        # Check timing - emails should be sent based on schedule from T1
        if send_history['last_sent']:
            last_sent = datetime.fromisoformat(send_history['last_sent'])
            days_since = (datetime.now() - last_sent).days

            # Next touch timing based on ICP doc schedule
            next_touch = sent_count + 1
            required_days = {
                2: 2,   # T2 after 2 days
                3: 3,   # T3 after 3 days from T2
                4: 4,   # T4 after 4 days from T3
                5: 4,   # T5 after 4 days from T4
            }

            min_days = required_days.get(next_touch, 2)
            if days_since < min_days:
                return False

        return True

    def send_all_pending(self, leads: List[Dict], loom_links: Dict[str, str] = None):
        """Send all pending emails in sequences"""
        results = {
            'sent': 0,
            'skipped': 0,
            'failed': 0,
        }

        for lead in leads:
            lead_id = lead.get('id', lead.get('profile_url', ''))

            if not self.can_send_next_email(lead_id):
                results['skipped'] += 1
                continue

            # Determine which touch to send
            status = self.get_lead_email_status(lead_id)
            next_touch = status['next_touch']

            if next_touch:
                loom_link = loom_links.get(lead_id) if loom_links else None
                success = self.send_sequence_email(lead, next_touch, loom_link)
                if success:
                    results['sent'] += 1
                else:
                    results['failed'] += 1

        return results