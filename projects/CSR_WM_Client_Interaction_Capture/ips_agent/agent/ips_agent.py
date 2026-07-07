"""
IPS Agent — Core Intelligence Layer
====================================
Processes client conversation transcripts in real time, extracts structured
IPS parameters using NER and pattern matching, maps them deterministically
to Investortools Perform schema fields, and stages the result for API push.

Architecture:
  Transcript → NER Extraction → Confidence Scoring → Deterministic Mapping
  → Completeness Tracking → Conflict Detection → Perform Staging Payload

Author: IPS Agent Team
"""

import re
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from anthropic import Anthropic

# ─────────────────────────────────────────────────────────────
# PERFORM SCHEMA — Deterministic Picklist Definitions
# All conversational output must resolve to one of these values.
# No free-text ever reaches Perform.
# ─────────────────────────────────────────────────────────────

PERFORM_SCHEMA = {
    "account_type": [
        "Individual", "Joint Tenants", "Joint Tenants with Right of Survivorship",
        "Tenants in Common", "Revocable Trust", "Irrevocable Trust",
        "Corporate", "Partnership", "Custodial (UGMA/UTMA)", "IRA", "Roth IRA",
        "401k Rollover", "Foundation", "Endowment", "Pension"
    ],
    "tax_status": [
        "Fully Taxable", "Federal Exempt Only",
        "State & Federal Exempt — NJ", "State & Federal Exempt — NY",
        "State & Federal Exempt — CA", "State & Federal Exempt — PA",
        "State & Federal Exempt — CT", "State & Federal Exempt — MA",
        "State & Federal Exempt — Other (specify)",
        "AMT-Eligible Excluded", "Dual-State Split (specify percentages)"
    ],
    "credit_quality": [
        "Investment Grade Only (BBB-/Baa3 and above)",
        "High Grade (A-/A3 and above)",
        "Very High Grade (AA-/Aa3 and above)",
        "Highest Grade Only (AAA/Aaa)",
        "Custom Minimum — specify rating",
        "No Restriction"
    ],
    "duration_bucket": [
        "Ultra-Short (< 1 year)", "Short (1–3 years)",
        "Short-Intermediate (2–5 years)", "Intermediate (3–7 years)",
        "Intermediate-Long (5–10 years)", "Long (7–15 years)",
        "Extended Long (15+ years)", "Custom range — specify"
    ],
    "risk_tolerance": [
        "Capital Preservation — minimize all risk",
        "Conservative — prioritize income, minimal principal risk",
        "Moderate Conservative — income-oriented, limited growth",
        "Moderate — balanced income and growth",
        "Moderate Aggressive — growth-oriented with income",
        "Aggressive — maximum growth, high volatility tolerance"
    ],
    "investment_objective": [
        "Capital Preservation", "Income Generation",
        "Tax-Exempt Income Maximization", "Capital Appreciation",
        "Total Return", "Balanced Growth and Income",
        "Liability Matching", "Inflation Protection"
    ],
    "sector_exclusions": [
        "Energy / Fossil Fuels (GICS 10)",
        "Tobacco (GICS 302020)", "Alcohol (GICS 302010)",
        "Gambling / Gaming (GICS 253120)",
        "Weapons / Defense (GICS 201010)",
        "Private Prisons", "Adult Entertainment",
        "Nuclear Power", "Specific Issuer (CUSIP — specify)",
        "Competitor Company (specify)", "None"
    ],
    "esg_mandate": [
        "No ESG Mandate", "ESG Integration (screen and score)",
        "Negative Screening Only", "Best-in-Class ESG",
        "Impact Investing Focus", "Full SRI Mandate",
        "Custom — specify criteria"
    ],
    "amt_treatment": [
        "AMT Paper Permitted", "AMT Paper Excluded — client subject to AMT"
    ],
    "de_minimis_treatment": [
        "Accrue market discount as ordinary income (standard)",
        "Restrict to par or premium bonds only",
        "Tax-exempt treatment preferred — avoid discount bonds"
    ],
    "withdrawal_source_priority": [
        "Draw from dedicated cash sleeve first",
        "Use maturing / called bond proceeds",
        "Sell shortest-duration holdings first",
        "Pro-rata liquidation across portfolio",
        "Prioritize tax-loss positions first",
        "Portfolio Manager discretion at time of withdrawal"
    ],
    "transition_treatment": [
        "Liquidate immediately to model — no restriction",
        "Limit realized short-term gains — specify $",
        "Limit total realized net gains — specify $",
        "Maximize tax-loss harvesting offsets",
        "Hold all legacy positions — transition gradually",
        "Hold specific CUSIPs — specify"
    ],
    "rebalancing_policy": [
        "Calendar-based — Quarterly", "Calendar-based — Semi-Annual",
        "Calendar-based — Annual", "Threshold-based — ±5% from target",
        "Threshold-based — ±10% from target", "Portfolio Manager Discretion"
    ]
}

# ─────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────

class ConfidenceLevel(Enum):
    HIGH = "high"       # ≥ 90% — green, auto-stage
    MEDIUM = "medium"   # 70–89% — amber, CSR confirm
    LOW = "low"         # < 70% — red, must resolve before staging


@dataclass
class ExtractedField:
    """A single IPS field extracted from conversation."""
    field_name: str
    raw_text: str               # What the client actually said
    mapped_value: str           # Perform schema value
    confidence: ConfidenceLevel
    confidence_score: float     # 0.0 – 1.0
    timestamp: float = field(default_factory=time.time)
    confirmed_by_csr: bool = False
    source: str = "nlp_extraction"


@dataclass
class WithdrawalRule:
    amount: Optional[float] = None
    frequency: Optional[str] = None
    month: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_months: Optional[int] = None
    source_priority: Optional[str] = None
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


@dataclass
class LegacyCUSIP:
    cusip: str
    description: str
    treatment: str   # "Hold/Lock" | "Liquidate" | "Tax-Loss Harvest"
    raw_text: str


@dataclass
class IPSProfile:
    """Complete IPS being built during the conversation."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    client_name: Optional[str] = None
    account_type: Optional[ExtractedField] = None
    tax_status: Optional[ExtractedField] = None
    credit_quality: Optional[ExtractedField] = None
    duration_bucket: Optional[ExtractedField] = None
    risk_tolerance: Optional[ExtractedField] = None
    investment_objective: Optional[ExtractedField] = None
    sector_exclusions: list[ExtractedField] = field(default_factory=list)
    esg_mandate: Optional[ExtractedField] = None
    amt_treatment: Optional[ExtractedField] = None
    de_minimis_treatment: Optional[ExtractedField] = None
    withdrawal_rules: list[WithdrawalRule] = field(default_factory=list)
    legacy_cusips: list[LegacyCUSIP] = field(default_factory=list)
    transition_treatment: Optional[ExtractedField] = None
    rebalancing_policy: Optional[ExtractedField] = None
    min_cash_cushion: Optional[float] = None
    capital_gains_budget: Optional[float] = None
    state_muni_split: Optional[dict] = None
    conflicts: list[str] = field(default_factory=list)
    nudges: list[str] = field(default_factory=list)
    conversation_history: list[dict] = field(default_factory=list)

    def completion_score(self) -> float:
        """Returns 0.0–1.0 reflecting how complete the IPS is."""
        required = [
            self.account_type, self.tax_status, self.credit_quality,
            self.duration_bucket, self.risk_tolerance, self.investment_objective,
            self.esg_mandate, self.amt_treatment
        ]
        completed = sum(1 for f in required if f is not None)
        return completed / len(required)

    def get_amber_fields(self) -> list[str]:
        """Fields that need CSR confirmation."""
        amber = []
        all_fields = [
            self.account_type, self.tax_status, self.credit_quality,
            self.duration_bucket, self.risk_tolerance, self.investment_objective,
            self.esg_mandate, self.amt_treatment, self.de_minimis_treatment,
            self.transition_treatment, self.rebalancing_policy
        ]
        for f in all_fields:
            if f and f.confidence == ConfidenceLevel.MEDIUM and not f.confirmed_by_csr:
                amber.append(f.field_name)
        return amber

    def to_perform_payload(self) -> dict:
        """Serialize to Perform-compatible JSON for API staging."""
        def field_val(f):
            return f.mapped_value if f else None

        return {
            "meta": {
                "session_id": self.session_id,
                "client_name": self.client_name,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "completion_score": round(self.completion_score(), 2),
                "amber_fields_pending": self.get_amber_fields()
            },
            "profile": {
                "account_type": field_val(self.account_type),
                "tax_status": field_val(self.tax_status),
                "investment_objective": field_val(self.investment_objective),
                "risk_tolerance": field_val(self.risk_tolerance),
            },
            "fixed_income_constraints": {
                "credit_quality_floor": field_val(self.credit_quality),
                "duration_target": field_val(self.duration_bucket),
                "amt_treatment": field_val(self.amt_treatment),
                "de_minimis_treatment": field_val(self.de_minimis_treatment),
                "min_cash_cushion_usd": self.min_cash_cushion,
                "state_muni_split": self.state_muni_split,
            },
            "restrictions": {
                "sector_exclusions": [f.mapped_value for f in self.sector_exclusions],
                "esg_mandate": field_val(self.esg_mandate),
            },
            "transition": {
                "treatment": field_val(self.transition_treatment),
                "capital_gains_budget_usd": self.capital_gains_budget,
                "legacy_cusips": [
                    {"cusip": c.cusip, "treatment": c.treatment}
                    for c in self.legacy_cusips
                ]
            },
            "cash_management": {
                "withdrawal_rules": [
                    {
                        "amount_usd": w.amount,
                        "frequency": w.frequency,
                        "month": w.month,
                        "start_date": w.start_date,
                        "end_date": w.end_date,
                        "source_priority": w.source_priority
                    } for w in self.withdrawal_rules
                ]
            },
            "operational": {
                "rebalancing_policy": field_val(self.rebalancing_policy)
            }
        }


# ─────────────────────────────────────────────────────────────
# NER — PATTERN BASED EXTRACTION
# Fast, deterministic extraction before Claude is invoked.
# These run on every transcript chunk for low-latency detection.
# ─────────────────────────────────────────────────────────────

def run_pattern_ner(text: str, profile: IPSProfile) -> list[dict]:
    """
    Pattern-based NER for common fixed-income phrases.
    Returns list of detected signals with confidence scores.
    Runs BEFORE Claude to catch high-confidence cases cheaply.
    """
    text_lower = text.lower()
    signals = []

    # ── Account type signals ──────────────────────────────────
    account_patterns = [
        (r'\b(joint|joint account|joint tenants)\b', "Joint Tenants", 0.88),
        (r'\b(revocable trust|rev trust|living trust)\b', "Revocable Trust", 0.92),
        (r'\b(irrevocable trust|irrev trust)\b', "Irrevocable Trust", 0.92),
        (r'\b(ira|individual retirement)\b', "IRA", 0.90),
        (r'\b(roth)\b', "Roth IRA", 0.93),
        (r'\b(personal|individual|my own|my account)\b', "Individual", 0.75),
        (r'\b(corporate|company account|business)\b', "Corporate", 0.82),
        (r'\b(foundation|endowment)\b', "Foundation", 0.88),
    ]
    for pattern, value, score in account_patterns:
        if re.search(pattern, text_lower):
            signals.append({"field": "account_type", "value": value, "score": score, "pattern": True})

    # ── Tax status signals ────────────────────────────────────
    state_map = {
        r'\bnew jersey\b|\b\bnj\b': "NJ", r'\bnew york\b|\bny\b': "NY",
        r'\bcalifornia\b|\bca\b': "CA", r'\bpennsylvania\b|\bpa\b': "PA",
        r'\bconnecticut\b|\bct\b': "CT", r'\bmassachusetts\b|\bma\b': "MA"
    }
    for pattern, state in state_map.items():
        if re.search(pattern, text_lower):
            signals.append({
                "field": "tax_status",
                "value": f"State & Federal Exempt — {state}",
                "score": 0.82,
                "pattern": True,
                "state": state
            })
    if re.search(r'\b(fully taxable|taxable account|no tax preference)\b', text_lower):
        signals.append({"field": "tax_status", "value": "Fully Taxable", "score": 0.90, "pattern": True})
    if re.search(r'\b(amt|alternative minimum tax)\b', text_lower):
        signals.append({"field": "amt_trigger", "value": "DETECTED", "score": 0.95, "pattern": True})

    # ── Credit quality signals ────────────────────────────────
    credit_patterns = [
        (r'\bno junk\b|\bno high.?yield\b|\binvestment grade only\b|\bno below investment grade\b', "Investment Grade Only (BBB-/Baa3 and above)", 0.93),
        (r'\baaa only\b|\bhighest quality\b|\btop rated\b', "Highest Grade Only (AAA/Aaa)", 0.91),
        (r'\baa or better\b|\baa.?rated\b|\bvery high grade\b', "Very High Grade (AA-/Aa3 and above)", 0.88),
        (r'\ba.?rated or better\b|\bsingle.?a\b', "High Grade (A-/A3 and above)", 0.85),
        (r'\bno bbb\b|\babove bbb\b', "High Grade (A-/A3 and above)", 0.82),
        (r'\bno credit restriction\b|\bany rating\b', "No Restriction", 0.88),
    ]
    for pattern, value, score in credit_patterns:
        if re.search(pattern, text_lower):
            signals.append({"field": "credit_quality", "value": value, "score": score, "pattern": True})

    # ── Duration signals ──────────────────────────────────────
    duration_patterns = [
        (r'\b(less than|under|within)\s*(\d+)\s*year', None, 0.0),
        (r'\bshort.?term\b|\b1.?to.?3.?year\b|\bone to three\b', "Short (1–3 years)", 0.87),
        (r'\bintermediate\b|\b3.?to.?7.?year\b|\bthree to seven\b', "Intermediate (3–7 years)", 0.87),
        (r'\blong.?term\b|\b7.?plus\b|\bover.?seven\b', "Long (7–15 years)", 0.85),
        (r'\bunder\s*3\s*year\b|\bless than\s*3\b', "Short (1–3 years)", 0.88),
        (r'\bunder\s*5\s*year\b|\bless than\s*5\b', "Short-Intermediate (2–5 years)", 0.85),
    ]
    for pattern, value, score in duration_patterns:
        if re.search(pattern, text_lower) and value:
            signals.append({"field": "duration_bucket", "value": value, "score": score, "pattern": True})

    # ── Risk tolerance signals ────────────────────────────────
    risk_patterns = [
        (r'\b(conservative|preserve capital|protect principal|safety first)\b', "Conservative — prioritize income, minimal principal risk", 0.88),
        (r'\b(very conservative|capital preservation|can.?t afford to lose|no risk)\b', "Capital Preservation — minimize all risk", 0.91),
        (r'\b(moderate|balanced|middle of the road)\b', "Moderate — balanced income and growth", 0.82),
        (r'\b(aggressive|growth|maximum return)\b', "Aggressive — maximum growth, high volatility tolerance", 0.84),
    ]
    for pattern, value, score in risk_patterns:
        if re.search(pattern, text_lower):
            signals.append({"field": "risk_tolerance", "value": value, "score": score, "pattern": True})

    # ── Withdrawal signals ────────────────────────────────────
    withdrawal_match = re.search(
        r'\$?([\d,]+(?:k|thousand|million)?)\s*(?:every|each|per|a)?\s*(month|quarter|year|annual|august|january|july)',
        text_lower
    )
    if withdrawal_match:
        raw_amount = withdrawal_match.group(1).replace(",", "").replace("k", "000").replace("thousand", "000")
        try:
            amount = float(raw_amount)
            signals.append({
                "field": "withdrawal_amount", "value": amount,
                "raw": withdrawal_match.group(0), "score": 0.80, "pattern": True
            })
        except ValueError:
            pass

    # ── Sector exclusion signals ──────────────────────────────
    exclusion_map = [
        (r'\b(no tobacco|exclude tobacco|tobacco free)\b', "Tobacco (GICS 302020)"),
        (r'\b(no fossil fuel|no oil|no coal|no energy sector|no petroleum)\b', "Energy / Fossil Fuels (GICS 10)"),
        (r'\b(no weapons|no defense|no guns|no arms)\b', "Weapons / Defense (GICS 201010)"),
        (r'\b(no gambling|no gaming|no casino)\b', "Gambling / Gaming (GICS 253120)"),
        (r'\b(no alcohol|no liquor|no beer|no wine)\b', "Alcohol (GICS 302010)"),
        (r'\b(no prison|no private prison|no corrections)\b', "Private Prisons"),
        (r'\b(no nuclear|exclude nuclear power)\b', "Nuclear Power"),
    ]
    for pattern, value in exclusion_map:
        if re.search(pattern, text_lower):
            signals.append({"field": "sector_exclusion", "value": value, "score": 0.88, "pattern": True})

    # ── ESG signals ───────────────────────────────────────────
    if re.search(r'\b(esg|socially responsible|sri|sustainable|green|impact invest)\b', text_lower):
        signals.append({"field": "esg_mandate", "value": "ESG Integration (screen and score)", "score": 0.78, "pattern": True})
    if re.search(r'\b(no esg|esg not required|no social screen|no restriction)\b', text_lower):
        signals.append({"field": "esg_mandate", "value": "No ESG Mandate", "score": 0.90, "pattern": True})

    # ── De minimis trigger ────────────────────────────────────
    if re.search(r'\b(discount bond|deep discount|bought at discount|below par|de minimis)\b', text_lower):
        signals.append({"field": "de_minimis_trigger", "value": "DETECTED", "score": 0.88, "pattern": True})

    # ── CUSIP detection ───────────────────────────────────────
    cusip_matches = re.findall(r'\b([0-9]{3}[A-Z0-9]{6})\b', text.upper())
    for cusip in cusip_matches:
        signals.append({"field": "cusip", "value": cusip, "score": 0.95, "pattern": True})

    # ── Cash cushion ──────────────────────────────────────────
    cash_match = re.search(r'keep\s+(?:at least\s+)?\$?([\d,]+(?:k|thousand)?)\s+in\s+cash', text_lower)
    if cash_match:
        raw = cash_match.group(1).replace(",", "").replace("k", "000").replace("thousand", "000")
        try:
            signals.append({"field": "min_cash_cushion", "value": float(raw), "score": 0.87, "pattern": True})
        except ValueError:
            pass

    return signals


def apply_pattern_signals(signals: list[dict], profile: IPSProfile):
    """Apply pattern NER results to the profile."""
    for sig in signals:
        f = sig["field"]
        val = sig["value"]
        score = sig["score"]
        conf = (ConfidenceLevel.HIGH if score >= 0.90
                else ConfidenceLevel.MEDIUM if score >= 0.70
                else ConfidenceLevel.LOW)

        if f == "account_type" and not profile.account_type:
            profile.account_type = ExtractedField(f, sig.get("raw", val), val, conf, score)
        elif f == "tax_status" and not profile.tax_status:
            profile.tax_status = ExtractedField(f, sig.get("raw", val), val, conf, score)
        elif f == "credit_quality" and not profile.credit_quality:
            profile.credit_quality = ExtractedField(f, sig.get("raw", val), val, conf, score)
        elif f == "duration_bucket" and not profile.duration_bucket:
            profile.duration_bucket = ExtractedField(f, sig.get("raw", val), val, conf, score)
        elif f == "risk_tolerance" and not profile.risk_tolerance:
            profile.risk_tolerance = ExtractedField(f, sig.get("raw", val), val, conf, score)
        elif f == "sector_exclusion":
            existing = [e.mapped_value for e in profile.sector_exclusions]
            if val not in existing:
                profile.sector_exclusions.append(ExtractedField(f, sig.get("raw", val), val, conf, score))
        elif f == "esg_mandate" and not profile.esg_mandate:
            profile.esg_mandate = ExtractedField(f, sig.get("raw", val), val, conf, score)
        elif f == "withdrawal_amount":
            if not profile.withdrawal_rules:
                profile.withdrawal_rules.append(WithdrawalRule(amount=val))
            else:
                profile.withdrawal_rules[-1].amount = val
        elif f == "min_cash_cushion":
            profile.min_cash_cushion = val
        elif f == "amt_trigger":
            if not profile.amt_treatment:
                profile.nudges.append("⚠️  AMT mentioned — confirm: Allow AMT paper or Exclude AMT paper?")
        elif f == "de_minimis_trigger":
            if not profile.de_minimis_treatment:
                profile.nudges.append("⚠️  Discount bond language detected — confirm De Minimis tax treatment.")
        elif f == "cusip":
            if not any(c.cusip == val for c in profile.legacy_cusips):
                profile.legacy_cusips.append(LegacyCUSIP(val, "Legacy holding", "Pending", sig.get("raw", val)))


# ─────────────────────────────────────────────────────────────
# CONFLICT DETECTION
# ─────────────────────────────────────────────────────────────

def detect_conflicts(profile: IPSProfile) -> list[str]:
    """Identify contradictions in captured profile."""
    conflicts = []

    # Risk / credit conflict
    if (profile.risk_tolerance and profile.credit_quality):
        rt = profile.risk_tolerance.mapped_value
        cq = profile.credit_quality.mapped_value
        if "Capital Preservation" in rt and "No Restriction" in cq:
            conflicts.append(
                "⚠️  Conflict: Capital Preservation objective but no credit quality floor set. "
                "Prompt client to confirm minimum rating."
            )
        if "Aggressive" in rt and "Highest Grade Only" in cq:
            conflicts.append(
                "⚠️  Conflict: Aggressive risk tolerance with AAA-only credit restriction. "
                "Clarify whether yield or safety takes priority."
            )

    # Objective / sector conflict
    if (profile.investment_objective and profile.sector_exclusions):
        obj = profile.investment_objective.mapped_value
        exclusions = [e.mapped_value for e in profile.sector_exclusions]
        if "Tax-Exempt Income" in obj and "Energy / Fossil Fuels" in str(exclusions):
            conflicts.append(
                "⚠️  Note: Extensive sector exclusions may limit muni inventory "
                "for tax-exempt income strategy. Consider reviewing."
            )

    # Duration / withdrawal conflict
    if profile.withdrawal_rules and profile.duration_bucket:
        for w in profile.withdrawal_rules:
            if w.frequency == "Annual" and w.duration_months and w.duration_months <= 36:
                if "Long" in profile.duration_bucket.mapped_value:
                    conflicts.append(
                        "⚠️  Conflict: Short-term scheduled withdrawals (≤3 years) with Long duration target. "
                        "Consider Short-Intermediate duration for liquidity alignment."
                    )

    return conflicts


# ─────────────────────────────────────────────────────────────
# AI AGENT — CLAUDE-POWERED EXTRACTION
# Handles nuanced, ambiguous, or complex conversational fragments
# that pattern NER cannot reliably classify.
# ─────────────────────────────────────────────────────────────

class IPSAgent:
    """
    Multi-turn AI agent that processes conversation transcripts,
    extracts IPS parameters, and maintains profile state.
    """

    SYSTEM_PROMPT = """You are an expert IPS (Investment Policy Statement) extraction agent 
specializing in fixed-income separately managed accounts on the Investortools Perform platform.

Your role: analyze client conversation fragments and extract structured IPS parameters.
Always respond in valid JSON. Never invent data not present in the text.

For each field you extract, provide:
- field_name: one of the known Perform schema fields
- mapped_value: exact value from the allowed picklist (provided in context)
- confidence_score: 0.0-1.0
- raw_text: the exact phrase that led to this extraction
- nudge: optional CSR prompt if clarification is needed
- conflict: optional conflict description if contradiction detected

Focus areas for fixed-income SMAs:
- Municipal bond preferences (state-specific, AMT, de minimis)
- Credit quality floors (exact rating thresholds)
- Duration targets
- Tax status (individual state exemptions, dual-state splits)
- ESG/sector exclusions (map to GICS codes)
- Scheduled cash withdrawals (amount, frequency, source priority)
- Legacy portfolio transition (CUSIP-level hold/liquidate/harvest)
- Capital gains budgets for transitions

CRITICAL: Every extraction must map to a value from the Perform schema picklists.
If a client phrase is ambiguous, flag it with confidence_score < 0.85 and provide a nudge."""

    def __init__(self):
        self.client = Anthropic()
        self.profile = IPSProfile()
        self.turn_count = 0

    def process_transcript_chunk(self, text: str, speaker: str = "client") -> dict:
        """
        Process a single transcript chunk (utterance or paragraph).
        Returns extraction results and updated profile state.
        """
        self.turn_count += 1

        # Step 1: Fast pattern NER
        signals = run_pattern_ner(text, self.profile)
        apply_pattern_signals(signals, self.profile)

        # Step 2: Build AI extraction context
        missing_fields = self._get_missing_fields()
        existing_summary = self._get_current_profile_summary()

        # Step 3: Add to conversation history for multi-turn context
        self.profile.conversation_history.append({
            "role": "user",
            "content": f"""[{speaker.upper()}]: {text}

Current IPS State:
{existing_summary}

Fields still needed:
{', '.join(missing_fields) if missing_fields else 'All core fields captured'}

Available Perform schema picklists:
{json.dumps(PERFORM_SCHEMA, indent=2)}

Extract any NEW IPS parameters from this utterance. 
Return JSON with key "extractions" (array) and "nudges" (array of CSR prompts).
Return empty arrays if nothing new to extract."""
        })

        # Step 4: Call Claude for deep extraction
        response = self.client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            system=self.SYSTEM_PROMPT,
            messages=self.profile.conversation_history
        )

        ai_response_text = response.content[0].text

        # Add assistant response to history (trim for context management)
        self.profile.conversation_history.append({
            "role": "assistant",
            "content": ai_response_text
        })

        # Keep history manageable (last 20 turns)
        if len(self.profile.conversation_history) > 40:
            self.profile.conversation_history = self.profile.conversation_history[-40:]

        # Step 5: Parse and apply AI extractions
        ai_extractions = []
        ai_nudges = []
        try:
            # Strip markdown fences if present
            clean = re.sub(r"```json|```", "", ai_response_text).strip()
            parsed = json.loads(clean)
            ai_extractions = parsed.get("extractions", [])
            ai_nudges = parsed.get("nudges", [])
            self._apply_ai_extractions(ai_extractions)
        except (json.JSONDecodeError, KeyError):
            pass  # Pattern NER results still applied

        # Step 6: Add AI nudges to profile
        for nudge in ai_nudges:
            if nudge not in self.profile.nudges:
                self.profile.nudges.append(nudge)

        # Step 7: Conflict detection
        new_conflicts = detect_conflicts(self.profile)
        for c in new_conflicts:
            if c not in self.profile.conflicts:
                self.profile.conflicts.append(c)

        return {
            "turn": self.turn_count,
            "speaker": speaker,
            "text": text,
            "pattern_signals": len(signals),
            "ai_extractions": ai_extractions,
            "nudges": self.profile.nudges.copy(),
            "conflicts": self.profile.conflicts.copy(),
            "completion_score": round(self.profile.completion_score(), 2),
            "amber_fields": self.profile.get_amber_fields(),
            "profile_snapshot": self._get_current_profile_summary()
        }

    def _apply_ai_extractions(self, extractions: list[dict]):
        """Apply Claude's extracted fields to the profile."""
        for ext in extractions:
            field_name = ext.get("field_name", "")
            mapped_value = ext.get("mapped_value", "")
            score = float(ext.get("confidence_score", 0.7))
            raw = ext.get("raw_text", mapped_value)
            conf = (ConfidenceLevel.HIGH if score >= 0.90
                    else ConfidenceLevel.MEDIUM if score >= 0.70
                    else ConfidenceLevel.LOW)
            ef = ExtractedField(field_name, raw, mapped_value, conf, score, source="claude_extraction")

            if field_name == "account_type" and not self.profile.account_type:
                self.profile.account_type = ef
            elif field_name == "tax_status" and not self.profile.tax_status:
                self.profile.tax_status = ef
            elif field_name == "credit_quality" and not self.profile.credit_quality:
                self.profile.credit_quality = ef
            elif field_name == "duration_bucket" and not self.profile.duration_bucket:
                self.profile.duration_bucket = ef
            elif field_name == "risk_tolerance" and not self.profile.risk_tolerance:
                self.profile.risk_tolerance = ef
            elif field_name == "investment_objective" and not self.profile.investment_objective:
                self.profile.investment_objective = ef
            elif field_name == "esg_mandate" and not self.profile.esg_mandate:
                self.profile.esg_mandate = ef
            elif field_name == "amt_treatment" and not self.profile.amt_treatment:
                self.profile.amt_treatment = ef
            elif field_name == "de_minimis_treatment" and not self.profile.de_minimis_treatment:
                self.profile.de_minimis_treatment = ef
            elif field_name == "sector_exclusion":
                existing = [e.mapped_value for e in self.profile.sector_exclusions]
                if mapped_value and mapped_value not in existing:
                    self.profile.sector_exclusions.append(ef)
            elif field_name == "rebalancing_policy" and not self.profile.rebalancing_policy:
                self.profile.rebalancing_policy = ef
            elif field_name == "transition_treatment" and not self.profile.transition_treatment:
                self.profile.transition_treatment = ef

    def _get_missing_fields(self) -> list[str]:
        required_map = {
            "account_type": self.profile.account_type,
            "tax_status": self.profile.tax_status,
            "credit_quality": self.profile.credit_quality,
            "duration_bucket": self.profile.duration_bucket,
            "risk_tolerance": self.profile.risk_tolerance,
            "investment_objective": self.profile.investment_objective,
            "esg_mandate": self.profile.esg_mandate,
            "amt_treatment": self.profile.amt_treatment,
        }
        return [k for k, v in required_map.items() if v is None]

    def _get_current_profile_summary(self) -> str:
        def fval(f): return f"{f.mapped_value} ({f.confidence.value}, {f.confidence_score:.0%})" if f else "NOT CAPTURED"
        lines = [
            f"account_type: {fval(self.profile.account_type)}",
            f"tax_status: {fval(self.profile.tax_status)}",
            f"credit_quality: {fval(self.profile.credit_quality)}",
            f"duration_bucket: {fval(self.profile.duration_bucket)}",
            f"risk_tolerance: {fval(self.profile.risk_tolerance)}",
            f"investment_objective: {fval(self.profile.investment_objective)}",
            f"esg_mandate: {fval(self.profile.esg_mandate)}",
            f"amt_treatment: {fval(self.profile.amt_treatment)}",
            f"sector_exclusions: {[e.mapped_value for e in self.profile.sector_exclusions] or 'NONE'}",
            f"withdrawal_rules: {len(self.profile.withdrawal_rules)} rule(s)",
            f"legacy_cusips: {[c.cusip for c in self.profile.legacy_cusips] or 'NONE'}",
        ]
        return "\n".join(lines)

    def stage_to_perform(self) -> dict:
        """Generate the final Perform-ready payload."""
        payload = self.profile.to_perform_payload()
        audit_narrative = self._generate_audit_narrative()
        payload["audit_trail"] = {
            "narrative": audit_narrative,
            "turns_processed": self.turn_count,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        return payload

    def _generate_audit_narrative(self) -> str:
        p = self.profile
        parts = []
        if p.client_name:
            parts.append(f"Client {p.client_name}")
        if p.account_type:
            parts.append(f"confirmed onboarding of {p.account_type.mapped_value} account")
        if p.investment_objective:
            parts.append(f"with {p.investment_objective.mapped_value} objective")
        if p.tax_status:
            parts.append(f"({p.tax_status.mapped_value})")
        if p.credit_quality:
            parts.append(f"credit floor: {p.credit_quality.mapped_value}")
        if p.duration_bucket:
            parts.append(f"duration: {p.duration_bucket.mapped_value}")
        if p.sector_exclusions:
            exclusions = ", ".join(e.mapped_value for e in p.sector_exclusions)
            parts.append(f"with restrictions on: {exclusions}")
        if p.withdrawal_rules:
            w = p.withdrawal_rules[0]
            if w.amount:
                parts.append(f"scheduled withdrawal of ${w.amount:,.0f} ({w.frequency or 'frequency TBD'})")
        return ". ".join(parts) + "." if parts else "Session in progress — narrative pending completion."

    def confirm_field(self, field_name: str, confirmed_value: str):
        """CSR manually confirms or overrides a field."""
        field_map = {
            "account_type": "account_type", "tax_status": "tax_status",
            "credit_quality": "credit_quality", "duration_bucket": "duration_bucket",
            "risk_tolerance": "risk_tolerance", "investment_objective": "investment_objective",
            "esg_mandate": "esg_mandate", "amt_treatment": "amt_treatment",
            "de_minimis_treatment": "de_minimis_treatment",
            "rebalancing_policy": "rebalancing_policy", "transition_treatment": "transition_treatment"
        }
        if field_name in field_map:
            ef = ExtractedField(field_name, "CSR confirmed", confirmed_value,
                                ConfidenceLevel.HIGH, 1.0, confirmed_by_csr=True, source="csr_override")
            setattr(self.profile, field_map[field_name], ef)
            self.profile.nudges = [n for n in self.profile.nudges if field_name not in n.lower()]
