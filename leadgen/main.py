"""
Main LeadGen System Orchestrator
Coordinates scraping, scoring, and outreach automation

Weekly workflow following ICP doc:
- Mon: Build 50-contact list by signal
- Tue: Demo batch day (record 8-10 Looms)
- Wed-Thu: IG engagement, DMs, email outreach
- Fri: Follow-ups and pipeline review
- Sun: Open house circuit
"""

import os
import sys
import logging
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Local imports
from .config import config, SHEETS_TABS
from .database import Database
from .scrapers.brokerage_scraper import BrokerageScraper
from .scrapers.zillow_scraper import ZillowScraper
from .scrapers.realtor_scraper import RealtorScraper
from .scrapers.job_post_scraper import JobPostScraper
from .scoring.lead_scorer import LeadScorer
from .outreach.email_sender import EmailSender
from .outreach.instagram_dm import InstagramDM
from .outreach.demo_generator import DemoGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('leadgen.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class LeadGenSystem:
    """Main orchestrator for the automated lead generation system"""

    def __init__(self):
        self.config = config
        self.db = Database(self.config.DATABASE_PATH)
        self.scorer = LeadScorer()
        self.email_sender = EmailSender(self.config)
        self.demo_generator = DemoGenerator()

        self.brokerage_scraper = BrokerageScraper()
        self.zillow_scraper = ZillowScraper()
        self.realtor_scraper = RealtorScraper()
        self.job_post_scraper = JobPostScraper()

        # Initialize components lazily
        self.instagram_dm = None
        self.enricher = None  # ContactEnricher built lazily in run_contact_enrichment

    def validate_setup(self) -> List[str]:
        """Validate all configuration and return errors"""
        errors = []

        # Check config
        config_errors = self.config.validate()
        errors.extend(config_errors)

        # Check database
        try:
            self.db.connect()
            self.db.create_tables()
        except Exception as e:
            errors.append(f"Database error: {str(e)}")

        # Check Instagram — cold DM path needs account credentials
        if not (self.config.INSTA_USERNAME and self.config.INSTA_PASSWORD):
            errors.append("Instagram account credentials not configured (INSTA_USERNAME/INSTA_PASSWORD) — required for cold DMs")
        # Warm-DM / token path is optional but warn if a token is present yet unset
        if not self.config.INSTA_ACCESS_TOKEN:
            errors.append("INSTAGRAM_ACCESS_TOKEN not configured — warm-lead DMs via API disabled")

        # Check Apify — Zillow/Realtor scraping falls back to direct scraping if absent
        if not self.config.APIFY_API_KEY:
            errors.append("APIFY_API_KEY not configured — Zillow/Realtor scraping will use slower direct fallback")

        return errors

    def run_daily_scraping(self) -> Dict:
        """
        Run daily scraping routine
        Collects new leads from all sources
        """
        logger.info("Starting daily scraping routine...")

        new_leads = []

        # 1. Check for job post signals (highest priority - hot accounts)
        logger.info("Scraping job posts for hiring signals...")
        try:
            job_leads = self.job_post_scraper.scrape_indeed_jobs()
            new_leads.extend(job_leads)
            logger.info(f"Found {len(job_leads)} leads from job posts")
        except Exception as e:
            logger.error(f"Job post scraping failed: {str(e)}")

        # 2. Scrape brokerage rosters
        logger.info("Scraping brokerage rosters...")
        try:
            brokerage_leads = self.brokerage_scraper.scrape_all_brokerages()
            new_leads.extend(brokerage_leads)
            logger.info(f"Found {len(brokerage_leads)} leads from brokerages")
        except Exception as e:
            logger.error(f"Brokerage scraping failed: {str(e)}")

        # 3. Scrape Zillow for top producers
        logger.info("Scraping Zillow agents...")
        try:
            zillow_leads = self.zillow_scraper.scrape_top_producers_apify()
            new_leads.extend(zillow_leads)
            logger.info(f"Found {len(zillow_leads)} leads from Zillow")
        except Exception as e:
            logger.error(f"Zillow scraping failed: {str(e)}")

        # 4. Scrape Realtor.com (Apify agents-by-zip, with direct fallback)
        logger.info("Scraping Realtor.com agents...")
        try:
            realtor_leads = self.realtor_scraper.scrape_agents_apify()
            new_leads.extend(realtor_leads)
            logger.info(f"Found {len(realtor_leads)} leads from Realtor.com")
        except Exception as e:
            logger.error(f"Realtor.com scraping failed: {str(e)}")

        # Save to database
        saved_count = 0
        for lead in new_leads:
            lead_id = self.db.save_lead(lead)
            if lead_id:
                saved_count += 1

        logger.info(f"Daily scraping complete. {saved_count} new leads saved.")

        return {
            'total_new_leads': len(new_leads),
            'saved_to_db': saved_count,
            'sources': {
                'job_posts': len([l for l in new_leads if l.get('source') == 'job_post']),
                'brokerages': len([l for l in new_leads if l.get('source') in ['compass', 'the_agency', 'carolwood']]),
                'zillow': len([l for l in new_leads if l.get('source') == 'zillow']),
                'realtor_com': len([l for l in new_leads if l.get('source') == 'realtor_com']),
            }
        }

    def run_scoring_cycle(self) -> Dict:
        """
        Score all leads in the database that haven't been scored yet
        """
        logger.info("Starting scoring cycle...")

        # Get unscored leads
        leads = self.db.get_unscored_leads(limit=100)
        logger.info(f"Found {len(leads)} leads to score")

        scored_leads = []
        categories = {'high': 0, 'medium': 0, 'low': 0, 'disqualified': 0}

        for lead in leads:
            scored = self.scorer.score_lead(lead)
            scored_leads.append(scored)

            # Update database with score
            self.db.update_lead_score(scored['id'], scored)

            # Count categories
            if scored['score'] >= self.config.HIGH_SCORE_THRESHOLD:
                categories['high'] += 1
            elif scored['score'] >= self.config.MEDIUM_SCORE_THRESHOLD:
                categories['medium'] += 1
            elif scored['score'] >= self.config.LOW_SCORE_THRESHOLD:
                categories['low'] += 1
            else:
                categories['disqualified'] += 1

        logger.info(f"Scoring complete: {categories}")

        return {
            'total_scored': len(scored_leads),
            'categories': categories,
        }

    def run_contact_enrichment(self, limit: int = None) -> Dict:
        """
        Contact Enrichment stage (Lead Generation pipeline).

        Finds professional/public contact info (phone, email, instagram) for
        qualified leads whose contact data is missing or stale (see
        CONTACT_ENRICHMENT_TTL_HOURS). Runs the provider-based ContactEnricher
        with per-lead failure isolation — one bad lead never stops the rest —
        and persists whatever was actually discovered. NEVER sends outreach.
        """
        logger.info("Starting contact enrichment...")
        from .enrichment import ContactEnricher, FAILED, NO_CONTACT, classify_status

        if self.enricher is None:
            self.enricher = ContactEnricher(self.config)

        ttl = self.config.CONTACT_ENRICHMENT_TTL_HOURS
        limit = limit or self.config.CONTACT_ENRICHMENT_MAX_LEADS_PER_RUN
        leads = self.db.get_leads_needing_enrichment(limit=limit, ttl_hours=ttl)
        logger.info("Contact enrichment: %d qualified leads to check", len(leads))

        if not leads:
            return {'checked': 0, 'enriched': 0, 'partial': 0, 'no_contact': 0,
                    'failed': 0, 'provider_errors': []}

        results = self.enricher.enrich_leads(leads)
        counts = {'enriched': 0, 'partial': 0, 'no_contact': 0, 'failed': 0}
        errors = []
        now = datetime.now().isoformat()

        for item in results:
            lead = item['lead']
            contact = item.get('contact') or {}
            if item.get('error'):
                status = FAILED
            else:
                status = classify_status(contact)
                # If nothing was discovered AND a provider reported it was
                # blocked/errored (e.g. realtor.com HTTP 429), record 'failed' —
                # never a misleading 'no contact'.
                if status == NO_CONTACT and contact.get('provider_errors'):
                    status = FAILED

            counts[status] = counts.get(status, 0) + 1
            if status == FAILED:
                reasons = list(contact.get('provider_errors') or [])
                if item.get('error'):
                    reasons.append(str(item['error']))
                for reason in reasons:
                    errors.append(f"{lead.get('id')}: {reason}")

            fields = {
                'email': contact.get('email'),
                'instagram': contact.get('instagram'),
                'phone': contact.get('phone'),
                'phone_raw': contact.get('phone_raw'),
                'phone_type': contact.get('phone_type', 'unknown'),
                'phone_source': contact.get('phone_source', 'unknown'),
                'phone_verified': contact.get('phone_verified', 0),
                'phone_last_checked': now,
                'enrichment_status': status,
                'enrichment_last_checked': now,
            }
            self.db.update_lead_enrichment(lead['id'], fields)

        counts['checked'] = len(results)
        counts['provider_errors'] = errors
        logger.info("Contact enrichment complete: %s", counts)
        if errors:
            logger.warning("Contact enrichment provider errors (%d):", len(errors))
            for err in errors[:10]:
                logger.warning("  - %s", err)
        return counts

    def run_demo_batch(self, lead_ids: List[str] = None) -> Dict:
        """
        Generate demos for qualified leads
        This is the Tuesday 'Demo Batch Day' from ICP doc
        """
        logger.info("Starting demo batch generation...")

        # Get qualified leads
        if lead_ids:
            leads = self.db.get_leads_by_ids(lead_ids)
        else:
            # Get high and medium score leads without demos
            leads = self.db.get_qualified_leads_with_listings(
                min_score=self.config.MEDIUM_SCORE_THRESHOLD,
                limit=20  # Cap for demo creation
            )

        logger.info(f"Generating demos for {len(leads)} leads")

        demos = {}
        for lead in leads:
            demo = self.demo_generator.generate_demo(lead)
            demos[lead.get('id')] = demo

            # Save demo info to database
            self.db.update_lead_demo_info(lead['id'], demo)

        logger.info(f"Demo batch complete. Generated {len(demos)} demos.")

        return {
            'total_demos': len(demos),
            'demos': demos
        }

    def run_outreach_cycle(self, categories_to_target: List[str] = None) -> Dict:
        """
        Run email and Instagram outreach for qualified leads
        """
        logger.info("Starting outreach cycle...")

        if categories_to_target is None:
            categories_to_target = ['high', 'medium']

        results = {
            'emails_sent': 0,
            'emails_skipped': 0,
            'dms_sent': 0,
            'dms_skipped': 0,
        }

        # Get leads to outreach
        leads = self.db.get_leads_for_outreach(
            categories=categories_to_target,
            limit=50
        )

        logger.info(f"Found {len(leads)} leads for outreach")

        # Prepare loom links for emails
        loom_links = {}
        for lead in leads:
            demo = self.demo_generator.get_demo_for_lead(lead)
            if demo:
                loom_links[lead['id']] = demo['loom_link']

        # Send emails
        email_results = self.email_sender.send_all_pending(leads, loom_links)
        results['emails_sent'] = email_results['sent']
        results['emails_skipped'] = email_results['skipped']

        # Send Instagram DMs
        instagram_leads = [l for l in leads if l.get('instagram') or l.get('instagram_handle')]
        if instagram_leads:
            if not self.instagram_dm:
                self.instagram_dm = InstagramDM(self.config)

            dm_results = self.instagram_dm.send_all_pending_dms(instagram_leads)
            results['dms_sent'] = dm_results['sent']
            results['dms_skipped'] = dm_results['skipped']

        logger.info(f"Outreach complete: {results}")
        return results

    def run_follow_ups(self) -> Dict:
        """
        Send follow-up emails (T2-T5) based on schedule
        """
        logger.info("Running follow-up cycle...")

        # Get leads that have received at least T1
        leads = self.db.get_leads_with_email_history(limit=100)

        results = {
            'follow_ups_sent': 0,
            'follow_ups_skipped': 0,
        }

        # Get loom links for leads
        loom_links = {}
        for lead in leads:
            demo = self.demo_generator.get_demo_for_lead(lead)
            if demo:
                loom_links[lead['id']] = demo['loom_link']

        email_results = self.email_sender.send_all_pending(leads, loom_links)
        results['follow_ups_sent'] = email_results['sent']
        results['follow_ups_skipped'] = email_results['skipped']

        logger.info(f"Follow-ups complete: {results}")
        return results

    def run_open_house_circuit(self, open_house_data: List[Dict] = None) -> Dict:
        """
        Sunday open house circuit
        Visit luxury open houses, collect contacts, send same-night demos
        """
        logger.info("Starting open house circuit...")

        if open_house_data is None:
            open_house_data = self._find_open_houses()

        results = {
            'houses_visited': len(open_house_data),
            'contacts_collected': 0,
            'demos_sent': 0,
        }

        # Initialize Instagram for DM sending
        if not self.instagram_dm:
            self.instagram_dm = InstagramDM(self.config)
            if not self.instagram_dm.login():
                logger.error("Could not login to Instagram for open house outreach")

        # Process each open house lead
        for house in open_house_data:
            lead = self._process_open_house_lead(house)

            if lead:
                # Score the lead
                scored = self.scorer.score_lead(lead)

                if scored['score'] >= self.config.LOW_SCORE_THRESHOLD:
                    # Save to database
                    lead_id = self.db.save_lead(lead, scored)

                    # Generate demo
                    demo = self.demo_generator.generate_demo(scored)
                    self.db.update_lead_demo_info(lead_id, demo)

                    # Send Instagram DM that night
                    instagram_handle = scored.get('instagram', '')
                    if instagram_handle and self.instagram_dm:
                        message_sent = self.instagram_dm.send_dm(
                            instagram_handle,
                            scored,
                            is_open_house_lead=True
                        )
                        if message_sent:
                            results['demos_sent'] += 1
                            results['contacts_collected'] += 1

        logger.info(f"Open house circuit complete: {results}")
        return results

    def _find_open_houses(self) -> List[Dict]:
        """
        Find luxury open houses for the upcoming Sunday
        This would integrate with real estate APIs in production
        """
        # Mock open houses - in production, this would scrape actual open house listings
        mock_houses = [
            {
                'address': "123 Billionaire's Row, Beverly Hills",
                'price': '$8,500,000',
                'agent_name': 'Sarah Johnson',
                'agent_instagram': 'sarahjohnson_realtor',
                'agent_brokerage': 'The Agency',
                'zip_code': '90210',
            },
            {
                'address': '456 Palisades Estate, Pacific Palisades',
                'price': '$12,000,000',
                'agent_name': 'Michael Chen',
                'agent_instagram': 'michaelchen_realtor',
                'agent_brokerage': 'Compass',
                'zip_code': '90272',
            },
        ]

        return mock_houses

    def _process_open_house_lead(self, house: Dict) -> Dict:
        """Convert open house data to lead format"""
        return {
            'source': 'open_house',
            'name': house.get('agent_name', 'Unknown Agent'),
            'brokerage': house.get('agent_brokerage', ''),
            'zip_code': house.get('zip_code', ''),
            'instagram': house.get('agent_instagram', ''),
            'listing_street': house.get('address', '').split(',')[0],
            'active_listings': [{
                'address': house.get('address', ''),
                'price': house.get('price', ''),
            }],
            'open_house_lead': True,
        }

    def run_pipeline_review(self) -> Dict:
        """
        Friday pipeline review
        Analyze the week's performance and update lead statuses
        """
        logger.info("Running weekly pipeline review...")

        stats = {}

        # Get weekly stats
        since_date = datetime.now() - timedelta(days=7)
        stats['new_leads_week'] = self.db.count_leads_since(since_date)
        stats['emails_sent_week'] = self.db.count_emails_sent_since(since_date)
        stats['calls_booked'] = self.db.count_leads_by_status('booked_call')
        stats['interested_leads'] = self.db.count_leads_by_status('interested')

        # Update lead statuses based on responses
        leads_with_responses = self.db.get_leads_with_email_responses()
        for lead in leads_with_responses:
            # Update lead status based on reply
            if 'yes' in lead.get('email_response', '').lower() or 'interested' in lead.get('email_response', '').lower():
                self.db.update_lead_status(lead['id'], 'interested')
            elif 'no' in lead.get('email_response', '').lower() or 'not interested' in lead.get('email_response', '').lower():
                self.db.update_lead_status(lead['id'], 'not_interested')

        logger.info(f"Pipeline review complete: {stats}")
        return stats

    def sync_to_sheets(self):
        """
        Sync leads to Google Sheets with proper tab organization
        """
        logger.info("Syncing leads to Google Sheets...")

        try:
            from .sheets_sync import SheetsSync
            sync = SheetsSync(self.config)

            if not sync.authenticate():
                logger.error("Google Sheets authentication failed")
                return False

            # Get all scored leads
            leads = self.db.get_all_scored_leads()

            # Categorize leads
            categorized = self.scorer.categorize_leads(leads)

            # Sync each category to its tab
            for category, category_leads in categorized.items():
                tab_name = SHEETS_TABS.get(category.split()[0].lower() + '_score',
                                            SHEETS_TABS.get('disqualified' if 'disqual' in category.lower() else 'medium_score'))
                sync.sync_leads_to_tab(tab_name, category_leads)

            # Sync special status tabs
            booked_leads = self.db.get_leads_by_status('booked_call')
            sync.sync_leads_to_tab(SHEETS_TABS['booked_call'], booked_leads)

            logger.info("Sheets sync complete")
            return True

        except Exception as e:
            logger.error(f"Error syncing to sheets: {str(e)}")
            return False

    def run_weekly_rhythm(self, day_of_week: str = None):
        """
        Execute the weekly workflow as defined in ICP doc
        Mon: list building | Tue: demo batch | Wed-Thu: outreach | Fri: review | Sun: open houses
        """
        if not day_of_week:
            day_of_week = datetime.now().strftime('%a')

        logger.info(f"Running weekly rhythm for {day_of_week}")

        results = {}

        if day_of_week == 'Mon':
            results['scraping'] = self.run_daily_scraping()
            results['scoring'] = self.run_scoring_cycle()

        elif day_of_week == 'Tue':
            results['demos'] = self.run_demo_batch()

        elif day_of_week in ['Wed', 'Thu']:
            results['outreach'] = self.run_outreach_cycle()

        elif day_of_week == 'Fri':
            results['followups'] = self.run_follow_ups()
            results['review'] = self.run_pipeline_review()
            results['sheets_sync'] = self.sync_to_sheets()

        elif day_of_week == 'Sun':
            results['open_houses'] = self.run_open_house_circuit()

        return results

    def run_full_cycle(self) -> Dict:
        """
        Run a complete end-to-end cycle
        Useful for testing or initial setup
        """
        logger.info("Running full lead gen cycle...")

        results = {}

        # Step 1: Scrape leads
        logger.info("Step 1: Scraping...")
        results['scraping'] = self.run_daily_scraping()

        # Step 2: Score leads
        logger.info("Step 2: Scoring...")
        results['scoring'] = self.run_scoring_cycle()

        # Step 3: Generate demos
        logger.info("Step 3: Generating demos...")
        results['demos'] = self.run_demo_batch()

        # Step 4: Send initial outreach
        logger.info("Step 4: Sending outreach...")
        results['outreach'] = self.run_outreach_cycle()

        # Step 5: Sync to sheets
        logger.info("Step 5: Syncing to sheets...")
        results['sheets_sync'] = self.sync_to_sheets()

        logger.info("Full cycle complete!")
        return results

    def close(self):
        """Clean up resources"""
        if self.instagram_dm:
            self.instagram_dm.close()
        if self.db:
            self.db.close()


def main():
    """Main entry point"""
    system = LeadGenSystem()

    # Validate setup
    errors = system.validate_setup()
    if errors:
        logger.error("Setup validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        sys.exit(1)

    # Run the system
    try:
        results = system.run_full_cycle()
        print(json.dumps(results, indent=2, default=str))
    finally:
        system.close()


if __name__ == '__main__':
    main()