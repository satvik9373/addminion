"""
Demo Generator
Creates personalized demo videos for each lead using their actual listings
Following the ICP doc: "Before touch one, the team builds the AI qualifying a fake buyer on one of the prospect's ACTUAL listings and records a 2 to 3 minute Loom"
"""

from typing import Dict, List, Optional
import logging
import time
import os
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class DemoGenerator:
    """
    Generates personalized demo videos/loom links for leads
    Currently implements mock generation - in production, integrate with
    actual screen recording tools or AI video generation
    """

    def __init__(self):
        self.demo_cache_path = 'data/demo_cache.json'
        self.demo_cache = self._load_cache()
        self.default_loom_template = 'https://www.loom.com/share/{demo_id}'

    def _load_cache(self) -> Dict:
        """Load cached demo information"""
        if os.path.exists(self.demo_cache_path):
            try:
                with open(self.demo_cache_path, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_cache(self):
        """Save demo cache to file"""
        os.makedirs(os.path.dirname(self.demo_cache_path), exist_ok=True)
        with open(self.demo_cache_path, 'w') as f:
            json.dump(self.demo_cache, f, indent=2, default=str)

    def generate_demo(self, lead: Dict) -> Dict:
        """
        Generate a demo for a specific lead
        Uses the lead's actual listing as the demo property
        """
        lead_id = lead.get('id', lead.get('profile_url', ''))
        if not lead_id:
            lead_id = f"lead_{datetime.now().isoformat()}"

        # Check if we already have a demo for this lead
        if lead_id in self.demo_cache:
            cached = self.demo_cache[lead_id]
            # Use cached demo if less than 7 days old
            created = datetime.fromisoformat(cached['created_at'])
            if (datetime.now() - created).days < 7:
                return cached

        # Generate new demo
        demo_content = self._create_demo_content(lead)

        # Generate demo ID
        import uuid
        demo_id = str(uuid.uuid4())[:8]

        demo_info = {
            'lead_id': lead_id,
            'demo_id': demo_id,
            'loom_link': self.default_loom_template.format(demo_id=demo_id),
            'created_at': datetime.now().isoformat(),
            'listing_used': demo_content.get('listing_used', {}),
            'script_used': demo_content.get('script_used', ''),
            'estimated_duration': demo_content.get('estimated_duration', '2-3 min'),
        }

        # Cache the demo
        self.demo_cache[lead_id] = demo_info
        self._save_cache()

        logger.info(f"Generated demo for lead {lead.get('name', 'Unknown')}")
        return demo_info

    def _create_demo_content(self, lead: Dict) -> Dict:
        """Create personalized demo content based on lead's listing"""
        # Find the lead's best listing to demo on
        listings = lead.get('active_listings', [])
        selected_listing = None
        listing_price = 0

        for listing in listings:
            if isinstance(listing, dict):
                price_str = listing.get('price', '')
                price = self._parse_price(price_str)
                if price > listing_price:
                    listing_price = price
                    selected_listing = listing

        # If no listings found, create a mock based on lead info
        if not selected_listing:
            selected_listing = {
                'address': lead.get('name', 'Luxury Property'),
                'price': '$5M+',
                'beds': '4',
                'baths': '5',
                'sqft': '5,000',
            }

        # Generate script for the demo
        script = self._generate_script(lead, selected_listing)

        return {
            'listing_used': selected_listing,
            'script_used': script,
            'estimated_duration': '2-3 min',
        }

    def _parse_price(self, price_str: str) -> float:
        """Parse price string to number"""
        if not price_str:
            return 0

        import re
        # Handle formats: $2.5M, $2,500,000, 2.5M, etc.
        num_match = re.search(r'(\d+(?:\.\d+)?)', str(price_str))
        if not num_match:
            return 0

        number = float(num_match.group(1))

        if 'M' in str(price_str) or 'million' in str(price_str).lower():
            number *= 1_000_000
        elif 'K' in str(price_str):
            number *= 1_000

        return number

    def _generate_script(self, lead: Dict, listing: Dict) -> str:
        """
        Generate personalized demo script
        Template based on the ICP doc's approach
        """
        first_name = lead.get('name', 'there').split()[0] if lead.get('name') else 'there'

        listing_address = listing.get('address', 'this beautiful property')
        listing_price = listing.get('price', '$5M+')
        beds = listing.get('beds', '4+')
        baths = listing.get('baths', '5+')
        sqft = listing.get('sqft', '5,000+')

        script = f"""
[Demo Start - 2:30 minutes]

Hi {first_name},

I saw your listing at {listing_address} and wanted to show you something quick.

This is what I built: An AI system that would answer inquiries on {listing_address} in real-time - day or night.

[Show interface]

When a buyer texts or calls at 2 AM asking about {listing_address}:

AI: 'Hi there, I can see you're interested in {listing_address}. Before we connect you with {first_name}, let me qualify your interest...'

[Demo interaction]

AI: 'Great! Let's check your budget - what's your target price range?'
Buyer: '{listing_price}'

AI: 'Perfect match. And financing?'
Buyer: 'Cash'

AI: 'Excellent. Let me book you a showing with {first_name} - the next available slot is tomorrow at 10 AM.'

[Show booking confirmation]

The system:
1. Answers 24/7 - never misses a lead
2. Qualifies budget, financing, and timeline
3. Books showings directly on {first_name}'s calendar
4. Routes hot buyers to {first_name}'s phone

For {listing_address} ({beds} beds, {baths} baths, {sqft} sqft) worth {listing_price}, this means you'll never lose another buyer to a missed call.

[Demo End]

That's a 2-minute demo. The full setup takes about 48 hours.

Want me to show you the dashboard with the actual lead flow for {listing_address}?

[Call to action: Schedule 15-min call]
"""

        return script.strip()

    def generate_batch_demos(self, leads: List[Dict]) -> Dict[str, Dict]:
        """
        Generate demos for multiple leads
        This is the "Demo Batch Day" mentioned in ICP doc (Tuesday)
        """
        demos = {}

        for lead in leads:
            lead_id = lead.get('id', lead.get('profile_url', ''))
            if not lead_id:
                continue

            demo = self.generate_demo(lead)
            demos[lead_id] = demo

        logger.info(f"Generated {len(demos)} demos in batch")
        return demos

    def get_demo_for_lead(self, lead: Dict) -> Optional[Dict]:
        """Get the demo for a specific lead"""
        lead_id = lead.get('id', lead.get('profile_url', ''))
        if lead_id in self.demo_cache:
            return self.demo_cache[lead_id]
        return None

    def get_all_pending_demos(self, leads: List[Dict]) -> List[Dict]:
        """Get all leads that don't have demos yet"""
        pending = []
        for lead in leads:
            lead_id = lead.get('id', lead.get('profile_url', ''))
            if lead_id not in self.demo_cache:
                pending.append(lead)
        return pending