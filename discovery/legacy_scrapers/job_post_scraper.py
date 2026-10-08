"""
Job Post Scraper
Scrapes Indeed and LinkedIn for real estate job posts (ISAs, showing assistants)
This identifies hot accounts where budgets are already allocated
"""

import hashlib
import requests
from typing import List, Dict, Optional
import logging
import time
import re

logger = logging.getLogger(__name__)

class JobPostScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def scrape_indeed_jobs(self, keywords: List[str] = None) -> List[Dict]:
        """
        Scrape Indeed for real estate jobs in LA market
        These are hot accounts - budget already allocated
        """
        leads = []
        if keywords is None:
            keywords = [
                'inside sales agent real estate Los Angeles',
                'showing assistant real estate Los Angeles',
                'real estate ISA Los Angeles',
                'real estate transaction coordinator Los Angeles',
                'real estate client coordinator Los Angeles',
            ]

        for keyword in keywords:
            try:
                logger.info(f"Scraping Indeed for: {keyword}")

                # Indeed search URL
                search_url = f"https://www.indeed.com/jobs?q={keyword.replace(' ', '+')}&l=Los+Angeles%2C+CA"

                response = self.session.get(search_url, timeout=30)

                if response.status_code == 200:
                    # Parse job results
                    job_cards = re.findall(
                        r'href="(/viewjob\?[^"]+)"',
                        response.text
                    )

                    count = 0
                    for job_path in job_cards[:10]:
                        if count >= 5:
                            break
                        job_url = f"https://www.indeed.com{job_path}"
                        job_data = self._scrape_indeed_job(job_url)

                        if job_data and job_data.get('company'):
                            # Check if this maps to a real estate agent/team
                            lead = self._extract_brokerage_from_job(job_data)
                            if lead:
                                leads.append(lead)
                        time.sleep(1)
                        count += 1

            except Exception as e:
                logger.error(f"Error scraping Indeed for '{keyword}': {str(e)}")

        return self._dedupe_leads(leads)

    def _scrape_indeed_job(self, url: str) -> Optional[Dict]:
        """Scrape individual Indeed job posting"""
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return None

            # Extract job details
            job_data = {
                'job_url': url,
                'title': self._extract_meta(response.text, 'title'),
                'company': self._extract_from_json(response.text, 'company'),
                'location': self._extract_from_json(response.text, 'location'),
                'job_description': self._extract_job_description(response.text),
                'posted_date': self._extract_posted_date(response.text),
            }

            # Extract company from job page text
            text = response.text

            # Try to find company name
            company_match = re.search(r'"companyName":"([^"]+)"', text)
            if company_match:
                job_data['company'] = company_match.group(1)

            # Extract brokerage/agent name
            company_text = re.search(r'At\s+([^,.]+?)(?:\s+,\s+|\s+in|\b)', text, re.IGNORECASE)
            if company_text:
                job_data['company_context'] = company_text.group(1)

            return job_data

        except Exception as e:
            logger.error(f"Error scraping Indeed job {url}: {str(e)}")
            return None

    def scrape_linkedin_jobs(self, keywords: List[str] = None) -> List[Dict]:
        """
        Scrape LinkedIn for job posts (may require authentication for full access)
        """
        leads = []
        if keywords is None:
            keywords = [
                'real estate ISA Los Angeles',
                'showing assistant real estate',
                'transaction coordinator real estate Los Angeles',
            ]

        for keyword in keywords:
            try:
                logger.info(f"Scraping LinkedIn for: {keyword}")

                # LinkedIn job search URL
                search_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}&location=Los%20Angeles%2C%20California%2C%20United%20States"

                response = self.session.get(search_url, timeout=30)

                if response.status_code == 200:
                    # Extract job IDs and links
                    job_links = re.findall(
                        r'href="(https://www\.linkedin\.com/jobs/view/\d+[^"]*)"',
                        response.text
                    )

                    count = 0
                    for job_url in job_links[:10]:
                        if count >= 5:
                            break

                        job_data = self._scrape_linkedin_job(job_url)
                        if job_data and job_data.get('company'):
                            lead = self._extract_brokerage_from_job(job_data)
                            if lead:
                                leads.append(lead)
                        time.sleep(1)
                        count += 1

            except Exception as e:
                logger.error(f"Error scraping LinkedIn for '{keyword}': {str(e)}")

        return self._dedupe_leads(leads)

    def _scrape_linkedin_job(self, url: str) -> Optional[Dict]:
        """Scrape individual LinkedIn job posting"""
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return None

            text = response.text

            job_data = {
                'job_url': url,
                'title': self._extract_meta(text, 'title') or re.search(r'<title>([^<]+)', text).group(1) if re.search(r'<title>([^<]+)', text) else None,
                'company': None,
                'location': None,
                'job_description': None,
            }

            # Extract company name
            company_match = re.search(r'"companyName":"?([^",]+)"?', text)
            if company_match:
                job_data['company'] = company_match.group(1)
            else:
                company_match = re.search(r'data-control-name="job-details-company-name"[^>]*>([^<]+)<', text)
                if company_match:
                    job_data['company'] = company_match.group(1).strip()

            # Extract location
            location_match = re.search(r'location":"?([^",]+)"?', text)
            if location_match:
                job_data['location'] = location_match.group(1)

            # Extract job description
            job_data['job_description'] = self._extract_job_description(text)

            return job_data

        except Exception as e:
            logger.error(f"Error scraping LinkedIn job {url}: {str(e)}")
            return None

    def _extract_brokerage_from_job(self, job_data: Dict) -> Optional[Dict]:
        """
        Extract real estate agent/team information from job posting
        This identifies hot accounts where ISA/showing assistants are being hired
        """
        company = job_data.get('company', '')
        description = job_data.get('job_description', '')
        title = job_data.get('title', '')

        # Check if this is a real estate related job
        if not any(keyword.lower() in str(company).lower() + str(description).lower() for keyword in
                   ['real estate', 'realty', 'realty', 'agent', 'broker', 'compass', 'sotheby', 'coldwell', 'remax', 'kw ', 'keller williams']):
            return None

        # Build lead from job data
        # Stable deterministic id derived from the job URL — the SAME job must
        # never produce a new row on re-scrape (the old timestamp fallback did).
        job_url = job_data.get('job_url') or ''
        lead = {
            'source': 'job_post',
            'id': f"job:{hashlib.md5(job_url.encode('utf-8')).hexdigest()[:20]}",
            'trigger': 'hiring_isa',  # This is the strongest buying signal
            'trigger_score': 25,  # From BUYING_TRIGGERS config
            'company_name': company,
            'job_title': title,
            'job_url': job_url,
            'job_description': description,
            'hiring_indication': True,
            'budget_confirmed': True,  # Hiring = budget allocated
            'estimated_annual_spend': '$50K-$75K',  # Typical ISA salary range mentioned in ICP
            'notes': f"Hiring for: {title}. Job post URL: {job_data.get('job_url')}",
        }

        # Try to infer agent/team name from description
        agent_match = re.search(r'(?:for|with|at)\s+(?:agent|team)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', description)
        if agent_match:
            lead['agent_name'] = agent_match.group(1)

        # Try to find brokerage mention
        brokerage_match = re.search(r'(?:Compass|The Agency|Sotheby|Coldwell Banker|Carolwood|Westside|Hilton & Hyland)(?:\s+\w+)?', description)
        if brokerage_match:
            lead['brokerage'] = brokerage_match.group(0)

        return lead

    def _extract_meta(self, text: str, tag: str) -> Optional[str]:
        """Extract meta tag content"""
        match = re.search(rf'<{tag} content="([^"]+)"', text, re.IGNORECASE)
        if match:
            return match.group(1)

        # Try JSON data
        match = re.search(rf'"{tag}":"([^"]+)"', text)
        if match:
            return match.group(1)

        return None

    def _extract_from_json(self, text: str, field: str) -> Optional[str]:
        """Extract field from JSON embedded in page"""
        match = re.search(rf'"{field}":"([^"]+)"', text)
        return match.group(1) if match else None

    def _extract_job_description(self, text: str) -> Optional[str]:
        """Extract job description from page text"""
        # Try to find job description section
        desc_match = re.search(r'<div[^>]*class="job-description"[^>]*>(.*?)</div>', text, re.DOTALL)
        if desc_match:
            clean_text = re.sub(r'<[^>]+>', ' ', desc_match.group(1))
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            return clean_text[:1000]  # Limit length

        # Fallback: look for any large text block
        description_patterns = [
            r'"description":"(.*?)"',
            r'data-job-description="([^"]+)"',
        ]

        for pattern in description_patterns:
            match = re.search(pattern, text)
            if match:
                desc = match.group(1)
                desc = re.sub(r'<[^>]+>', ' ', desc)
                desc = re.sub(r'\\n', ' ', desc)
                return desc[:1000]

        return None

    def _extract_posted_date(self, text: str) -> Optional[str]:
        """Extract job posted date"""
        date_patterns = [
            r'(\d+)\s+(?:days?|hrs?)\s+ago',
            r'(\d{1,2}/\d{1,2}/\d{4})',
            r'(\w+\s+\d{1,2},\s+\d{4})',
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None

    def _dedupe_leads(self, leads: List[Dict]) -> List[Dict]:
        """Remove duplicate leads"""
        seen = set()
        unique = []
        for lead in leads:
            key = f"{lead.get('company_name', '')}_{lead.get('job_url', '')}"
            if key and key not in seen:
                seen.add(key)
                unique.append(lead)
        return unique