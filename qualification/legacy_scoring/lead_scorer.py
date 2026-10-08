"""
Lead Scoring Engine
Scores leads based on:
1. Financial Indicators (30% weight)
2. Buying Triggers (40% weight)
3. ICP Fit (30% weight)

Uses thresholds from config.py
"""

from typing import Dict, List, Optional
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class LeadScorer:
    def __init__(self):
        # Import scoring criteria from config
        from config.settings import (
            SCORING_WEIGHTS,
            BUYING_TRIGGERS,
            FINANCIAL_INDICATORS,
            ICP_FIT,
            Config
        )

        self.weights = SCORING_WEIGHTS
        self.buying_triggers = BUYING_TRIGGERS
        self.financial_indicators = FINANCIAL_INDICATORS
        self.icp_fit = ICP_FIT
        self.config = Config()

        # Maximum possible scores for normalization
        self.max_financial = sum(self.financial_indicators.values())
        self.max_triggers = sum(self.buying_triggers.values())
        self.max_icp = sum(self.icp_fit.values())

    def score_lead(self, lead: Dict) -> Dict:
        """
        Score a lead based on all criteria
        Returns enriched lead dict with scores
        """
        try:
            # Calculate component scores
            financial_score = self._calculate_financial_score(lead)
            trigger_score = self._calculate_trigger_score(lead)
            icp_score = self._calculate_icp_score(lead)

            # Normalize to weighted percentages (max 100)
            normalized_financial = (financial_score / self.max_financial) * 100 if self.max_financial > 0 else 0
            normalized_triggers = (trigger_score / self.max_triggers) * 100 if self.max_triggers > 0 else 0
            normalized_icp = (icp_score / self.max_icp) * 100 if self.max_icp > 0 else 0

            # Apply weights
            weighted_financial = normalized_financial * (self.weights['financial_indicators'] / 100)
            weighted_triggers = normalized_triggers * (self.weights['buying_triggers'] / 100)
            weighted_icp = normalized_icp * (self.weights['icp_fit'] / 100)

            # Final weighted score (0-100)
            total_score = weighted_financial + weighted_triggers + weighted_icp

            # Round to nearest integer
            final_score = round(total_score)

            # Determine category
            category = self._determine_category(final_score)
            tier = self._determine_tier(lead, final_score)

            return {
                **lead,
                'score': final_score,
                'score_breakdown': {
                    'financial': round(weighted_financial, 2),
                    'triggers': round(weighted_triggers, 2),
                    'icp': round(weighted_icp, 2),
                },
                'category': category,
                'icp_tier': tier,
                'qualified': final_score >= self.config.LOW_SCORE_THRESHOLD,
                'scored_at': datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error scoring lead: {str(e)}")
            return {
                **lead,
                'score': 0,
                'category': 'Disqualified',
                'qualified': False,
                'error': str(e)
            }

    def _calculate_financial_score(self, lead: Dict) -> float:
        """Calculate financial indicator score"""
        score = 0

        # Extract transaction volume if available
        volume = self._extract_transaction_volume(lead)
        if volume is not None:
            if volume >= 50:
                score += self.financial_indicators['transaction_volume_50m_plus']
            elif volume >= 30:
                score += self.financial_indicators['transaction_volume_30m_49m']
            elif volume >= 20:
                score += self.financial_indicators['transaction_volume_20m_29m']

        # Extract average sale price
        avg_sale = self._extract_avg_sale(lead)
        if avg_sale is not None:
            if avg_sale >= 2_000_000:
                score += self.financial_indicators['avg_sale_2m_plus']
            elif avg_sale >= 1_000_000:
                score += self.financial_indicators['avg_sale_1m_1_9m']

        # Count active listings
        listing_count = self._count_listings(lead)
        if listing_count >= 5:
            score += self.financial_indicators['active_listings_5_plus']
        elif listing_count >= 3:
            score += self.financial_indicators['active_listings_3_4']
        elif listing_count >= 1:
            score += self.financial_indicators['active_listings_1_2']

        # Monthly spend indicators
        description = (lead.get('bio', '') or '') + ' ' + (lead.get('notes', '') or '')
        if 'zillow' in description.lower() or 'premier' in description.lower():
            if any(keyword in description.lower() for keyword in ['$10k', '$15k', '$10,000', '$15,000', '10k/month', '15k/month']):
                score += self.financial_indicators['monthly_spend_10k_plus']
            else:
                score += self.financial_indicators['monthly_spend_5k_9k']

        return score

    def _calculate_trigger_score(self, lead: Dict) -> float:
        """Calculate buying trigger score"""
        score = 0

        # Check for each trigger
        # 1. Hiring ISA or showing assistant
        if self._has_hiring_trigger(lead):
            score += self.buying_triggers['hiring_isa']

        # 2. New $5M+ listing in MLS
        if self._has_new_high_value_listing(lead):
            score += self.buying_triggers['new_high_value_listing']

        # 3. Running Zillow Premier Agent
        if self._runs_paid_ads(lead):
            score += self.buying_triggers['running_zillow_premier']

        # 4. Team expansion
        if self._has_team_expansion(lead):
            score += self.buying_triggers['team_expansion']

        # 5. Recently went independent
        if self._is_recently_independent(lead):
            score += self.buying_triggers['recent_independence']

        # 6. Weekend open houses
        if self._has_open_houses(lead):
            score += self.buying_triggers['weekend_open_houses']

        return score

    def _calculate_icp_score(self, lead: Dict) -> float:
        """Calculate ICP fit score"""
        score = 0

        # Determine ICP tier based on profile
        tier = self._determine_raw_tier(lead)
        if tier == 1:  # Team
            score += self.icp_fit['icp_tier_1_team']
        elif tier == 2:  # Solo producer
            score += self.icp_fit['icp_tier_2_solo']
        elif tier == 3:  # Boutique brokerage
            score += self.icp_fit['icp_tier_3_boutique']

        # Brokerage fit
        if self._at_target_brokerage(lead):
            score += self.icp_fit['icp_tier_1_brokerage']

        # Zip code fit
        if self._in_target_zip_codes(lead):
            score += self.icp_fit['icp_tier_1_zip']

        # Role scoring
        role = self._determine_role(lead)
        if role == 'ops_director':
            score += self.icp_fit['role_ops_director']
        elif role == 'team_lead':
            score += self.icp_fit['role_team_lead']
        elif role == 'solo_agent':
            score += self.icp_fit['role_solo_agent']

        return score

    def _extract_transaction_volume(self, lead: Dict) -> Optional[float]:
        """Extract estimated annual transaction volume (in millions USD)"""
        # Check explicit volume fields
        volume_fields = [
            'annual_volume', 'transaction_volume', 'annual_sales',
            'total_sales', 'volume', 'est_volume'
        ]

        for field in volume_fields:
            if lead.get(field):
                value = self._parse_money_amount(str(lead[field]))
                if value:
                    return value / 1_000_000  # Convert to millions

        # Try to extract from bio/description
        text = (lead.get('bio', '') or '') + ' ' + (lead.get('notes', '') or '')
        if not text:
            return None

        # Search a window around volume/sales/annual keywords for a dollar amount
        for m in re.finditer(r'(volume|sales|annual|transaction)', text, re.IGNORECASE):
            window = text[max(0, m.start() - 40): m.end() + 40]
            amount = self._parse_money_amount(window)
            if amount:
                return amount / 1_000_000

        # Fallback: any "$50M" / "50 million" mention in the text
        amounts = re.findall(r'\$?\s*(\d+(?:\.\d+)?)\s*(?:million|M)\b', text, re.IGNORECASE)
        if amounts:
            return float(amounts[0])

        return None

    def _extract_avg_sale(self, lead: Dict) -> Optional[float]:
        """Extract average sale price"""
        text = (lead.get('bio', '') or '') + ' ' + (lead.get('notes', '') or '')
        if not text:
            return None

        # Search a window around "average"/"avg" keywords for a dollar amount
        for m in re.finditer(r'(average|avg)\b', text, re.IGNORECASE):
            window = text[max(0, m.start() - 30): m.end() + 60]
            amount = self._parse_money_amount(window)
            if amount:
                return amount

        # Fallback: look for "$2M+" / "$3M" / "$2,500,000" type figures near "sale"
        for m in re.finditer(r'(sale|price|deal)', text, re.IGNORECASE):
            window = text[max(0, m.start() - 40): m.end() + 40]
            amount = self._parse_money_amount(window)
            if amount and amount >= 1_000_000:
                return amount

        return None

    def _count_listings(self, lead: Dict) -> int:
        """Count active listings"""
        return len(self._get_listings(lead))

    def _get_listings(self, lead: Dict) -> List[Dict]:
        """Return active listings as a list, parsing JSON strings if needed"""
        listings = lead.get('active_listings', [])
        if isinstance(listings, str):
            import json as _json
            try:
                parsed = _json.loads(listings)
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, dict)]
            except Exception:
                return []
            return []
        if isinstance(listings, list):
            return [item for item in listings if isinstance(item, dict)]
        return []

    def _has_hiring_trigger(self, lead: Dict) -> bool:
        """Check if lead has hiring trigger"""
        # Direct trigger indication
        if lead.get('trigger') == 'hiring_isa':
            return True

        if lead.get('hiring_indication'):
            return True

        # Check notes/bio for hiring keywords
        text = (lead.get('bio', '') or '') + ' ' + (lead.get('notes', '') or '')
        hiring_keywords = ['hiring', 'join our team', 'is a', 'showing assistant', 'transaction coordinator']

        return any(keyword in text.lower() for keyword in hiring_keywords)

    def _has_new_high_value_listing(self, lead: Dict) -> bool:
        """Check for new $5M+ listing"""
        listings = self._get_listings(lead)
        for listing in listings:
            price_str = str(listing.get('price', ''))
            amount = self._parse_money_amount(price_str)
            if amount and amount >= 5_000_000:
                return True

        # Check text for high value mentions
        text = (lead.get('bio', '') or '') + ' ' + (lead.get('notes', '') or '')
        high_value_patterns = [r'\$5M', r'\$[5-9]M', r'\$[1-9]\d\s*million', r'\$5,000,000', r'\$[5-9],\d{3},\d{3}']

        return any(re.search(pattern, text) for pattern in high_value_patterns)

    def _runs_paid_ads(self, lead: Dict) -> bool:
        """Check if lead runs Zillow Premier Agent or other paid lead gen"""
        text = (lead.get('bio', '') or '') + ' ' + (lead.get('notes', '') or '')
        paid_keywords = ['zillow premier', 'premier agent', 'paid lead', 'lead gen', 'lead generation']

        return any(keyword in text.lower() for keyword in paid_keywords)

    def _has_team_expansion(self, lead: Dict) -> bool:
        """Check for team expansion"""
        text = (lead.get('bio', '') or '') + ' ' + (lead.get('notes', '') or '')
        expansion_keywords = ['expanding', 'joining our', 'growing our team', 'adding to our']

        return any(keyword in text.lower() for keyword in expansion_keywords)

    def _is_recently_independent(self, lead: Dict) -> bool:
        """Check if recently went independent"""
        text = (lead.get('bio', '') or '') + ' ' + (lead.get('notes', '') or '')
        independence_keywords = ['formerly', 'previously with', 'now independent', 'transitioned', 'joined']

        return any(keyword in text.lower() for keyword in independence_keywords)

    def _has_open_houses(self, lead: Dict) -> bool:
        """Check for weekend open houses"""
        text = (lead.get('bio', '') or '') + ' ' + (lead.get('notes', '') or '')
        return 'open house' in text.lower() or 'open house' in (lead.get('title', '') or '').lower()

    def _determine_raw_tier(self, lead: Dict) -> int:
        """Determine raw ICP tier without scoring"""
        name = lead.get('name', '') or ''
        bio = lead.get('bio', '') or ''
        team = lead.get('team') or ''
        title = lead.get('title', '') or ''
        source = lead.get('source', '')
        notes = lead.get('notes', '') or ''

        # Check for job post lead (hiring trigger = team lead)
        if source == 'job_post' or lead.get('trigger') == 'hiring_isa':
            return 1 if 'team' in (team or '').lower() or 'team' in bio.lower() else 2

        # Check for team vs solo
        combined_text = f"{name} {bio} {team} {title} {notes}".lower()

        if any(keyword in combined_text for keyword in ['team', 'team leader', 'team captain', 'director']):
            return 1
        elif 'team' in team.lower() if team else False:
            return 1
        elif 'team' in combined_text:
            return 1
        else:
            # Default: solo if they have high volume, otherwise solo
            return 2

    def _determine_tier(self, lead: Dict, score: int) -> str:
        """Determine final tier classification"""
        raw_tier = self._determine_raw_tier(lead)

        if raw_tier == 1:
            return 'ICP-1 (Teams)'
        elif raw_tier == 2:
            return 'ICP-2 (Solo Producers)'
        elif raw_tier == 3:
            return 'ICP-3 (Boutiques)'
        else:
            # Fallback based on score
            if score >= 15:
                return 'ICP-1'
            elif score >= 10:
                return 'ICP-2'
            else:
                return 'ICP-3'

    def _at_target_brokerage(self, lead: Dict) -> bool:
        """Check if lead is at a target brokerage"""
        brokerage = (lead.get('brokerage') or '').lower()
        if not brokerage:
            return False

        target_brokerages = [
            'compass', 'the agency', 'sotheby', 'coldwell banker',
            'carolwood', 'westside', 'hilton', 'beverly hills estates'
        ]

        return any(target in brokerage for target in target_brokerages)

    def _in_target_zip_codes(self, lead: Dict) -> bool:
        """Check if lead operates in target zip codes"""
        lead_zips = lead.get('zip_codes', [])

        # Target zips from config
        target_zips = ['90210', '90077', '90272', '90265', '91302', '90402', '90290']

        # Also check zip_code field
        zip_code = lead.get('zip_code', '')
        if zip_code and str(zip_code) in target_zips:
            return True

        # Check zip_codes array
        if isinstance(lead_zips, list):
            return any(str(z) in target_zips for z in lead_zips)

        return False

    def _determine_role(self, lead: Dict) -> str:
        """Determine lead's role"""
        title = (lead.get('title') or '').lower()
        role = lead.get('role') or ''

        if role:
            role_lower = role.lower()
            if 'ops' in role_lower or 'director' in role_lower or 'manager' in role_lower:
                return 'ops_director'
            elif 'team lead' in role_lower or 'team captain' in role_lower or 'rainmaker' in role_lower:
                return 'team_lead'
            elif 'assistant' in role_lower or 'coordinator' in role_lower:
                return 'assistant'

        # Infer from title and bio
        if 'director' in title or 'manager' in title or 'ops' in title:
            return 'ops_director'
        elif 'team' in title.lower():
            return 'team_lead'
        elif 'agent' in title.lower() or 'realtor' in title.lower():
            # Check if it's a solo agent
            bio = (lead.get('bio') or '').lower()
            if 'team' in bio or 'team of' in bio:
                return 'team_lead'
            return 'solo_agent'

        return 'solo_agent'  # Default

    def _determine_category(self, score: int) -> str:
        """Determine lead category based on score"""
        if score >= self.config.HIGH_SCORE_THRESHOLD:
            return 'High Score'
        elif score >= self.config.MEDIUM_SCORE_THRESHOLD:
            return 'Medium Score'
        elif score >= self.config.LOW_SCORE_THRESHOLD:
            return 'Low Score'
        else:
            return 'Disqualified'

    def _parse_money_amount(self, text: str) -> Optional[float]:
        """Parse monetary amount from string"""
        if not text:
            return None

        # Match dollar amounts: $2M, $2.5M, $2,500,000, 2M, 2.5 million
        text = str(text).strip()

        # Handle abbreviated amounts
        if 'million' in text.lower() or re.search(r'\d\s*M(?!\w)', text, re.IGNORECASE):
            match = re.search(r'(\d+(?:\.\d+)?)', text)
            if match:
                return float(match.group(1)) * 1_000_000

        if 'k' in text.lower() and 'm' not in text.lower():
            match = re.search(r'(\d+(?:\.\d+)?)K', text, re.IGNORECASE)
            if match:
                return float(match.group(1)) * 1_000

        # Handle full amounts
        match = re.search(r'\$\s*([\d,]+\.?\d*)', text)
        if match:
            amount_str = match.group(1).replace(',', '')
            return float(amount_str)

        # Handle bare numbers
        match = re.search(r'(\d[\d,]*\.?\d*)', text)
        if match:
            amount_str = match.group(1).replace(',', '')
            number = float(amount_str)

            # If there's a million indicator nearby
            if 'million' in text.lower() or 'm' in text[text.find(match.group(0))-1:text.find(match.group(0))+10]:
                number *= 1_000_000

            return number

        return None

    def score_leads_batch(self, leads: List[Dict]) -> List[Dict]:
        """Score multiple leads"""
        scored_leads = []

        for lead in leads:
            try:
                scored = self.score_lead(lead)
                scored_leads.append(scored)
            except Exception as e:
                logger.error(f"Error scoring lead: {str(e)}")
                scored_leads.append({
                    **lead,
                    'score': 0,
                    'category': 'Disqualified',
                    'qualified': False,
                    'error': str(e)
                })

        return scored_leads

    def filter_qualified_leads(self, leads: List[Dict]) -> List[Dict]:
        """Filter out disqualified leads (score < 5)"""
        return [lead for lead in leads if lead.get('score', 0) >= self.config.LOW_SCORE_THRESHOLD]

    def categorize_leads(self, leads: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize leads by score category"""
        categories = {
            'High Score': [],
            'Medium Score': [],
            'Low Score': [],
            'Disqualified': [],
        }

        for lead in leads:
            category = lead.get('category', 'Disqualified')
            if category in categories:
                categories[category].append(lead)
            else:
                categories['Disqualified'].append(lead)

        return categories