"""
IPS Agent — Test Cases with Simulated Voice Transcription
==========================================================
Simulates realistic client conversations for three client archetypes.
Each test case plays through a full session, chunk by chunk,
printing real-time agent feedback at each turn.

Test Clients:
  1. NJ High-Net-Worth Individual — muni-focused, dual-state concern, AMT
  2. California Trust — ESG mandate, legacy portfolio transition, capital gains budget
  3. Conservative Retiree — capital preservation, scheduled withdrawals, no restrictions

Run:
  python tests/test_cases.py
  python tests/test_cases.py --case 1
  python tests/test_cases.py --case 2
  python tests/test_cases.py --case 3
"""

import sys
import json
import time
import argparse

# Adjust path for direct execution
sys.path.insert(0, ".")
from agent.ips_agent import IPSAgent, PERFORM_SCHEMA


# ─────────────────────────────────────────────────────────────
# SIMULATED TRANSCRIPTION ENGINE
# In production: replace with Deepgram / AssemblyAI / Azure STT.
# Here: yields pre-written utterances with realistic timing.
# ─────────────────────────────────────────────────────────────

def simulate_voice_transcription(utterances: list[dict], delay: float = 0.3):
    """
    Simulate a streaming diarized transcription feed.

    Each utterance is a dict:
      {"speaker": "CLIENT"|"CSR", "text": "...", "note": "optional context"}

    In production, this generator would be replaced by:
      - Deepgram streaming WebSocket (real-time, diarized)
      - AssemblyAI real-time transcription
      - Azure Cognitive Services Speech SDK
      - AWS Transcribe Medical (if needed)

    The agent processes only CLIENT utterances for IPS extraction.
    CSR utterances are logged for audit but not extracted.
    """
    print("\n" + "─" * 70)
    print("  🎙  SIMULATED TRANSCRIPTION FEED ACTIVE")
    print("  Replace simulate_voice_transcription() with live STT in production")
    print("─" * 70 + "\n")
    time.sleep(0.5)

    for utt in utterances:
        time.sleep(delay)
        yield utt


# ─────────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────

COLORS = {
    "green": "\033[92m", "amber": "\033[93m", "red": "\033[91m",
    "blue": "\033[94m", "purple": "\033[95m", "cyan": "\033[96m",
    "bold": "\033[1m", "reset": "\033[0m", "dim": "\033[2m"
}

def c(color, text): return f"{COLORS.get(color,'')}{text}{COLORS['reset']}"

def print_turn_result(result: dict):
    """Print a formatted real-time analysis for each utterance."""
    print(f"\n{'─'*70}")
    spk = result['speaker'].upper()
    spk_color = "blue" if spk == "CSR" else "cyan"
    print(f"  {c(spk_color, c('bold', spk))}: {c('dim', result['text'][:120])}")

    if result['speaker'] == 'csr':
        return  # Don't show extraction panel for CSR utterances

    # Completion bar
    pct = int(result['completion_score'] * 100)
    bar_filled = int(pct / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    bar_color = "green" if pct >= 80 else "amber" if pct >= 40 else "red"
    print(f"\n  IPS Completion  [{c(bar_color, bar)}] {pct}%")

    # Extractions this turn
    if result['ai_extractions']:
        print(f"\n  {c('green', '✓ Extracted this turn:')}")
        for ext in result['ai_extractions']:
            score_pct = int(float(ext.get('confidence_score', 0)) * 100)
            conf_color = "green" if score_pct >= 90 else "amber" if score_pct >= 70 else "red"
            print(f"    {c(conf_color, '●')} {ext.get('field_name','?'):25s} → {ext.get('mapped_value','?')[:45]} ({score_pct}%)")

    # Amber fields needing confirmation
    if result['amber_fields']:
        print(f"\n  {c('amber', '⚠  Needs CSR confirmation:')}")
        for field in result['amber_fields']:
            print(f"    {c('amber', '◆')} {field}")

    # Nudges
    if result['nudges']:
        print(f"\n  {c('purple', '💬 Agent nudges for CSR:')}")
        for nudge in result['nudges'][-3:]:  # Show last 3
            print(f"    → {nudge[:100]}")

    # Conflicts
    if result['conflicts']:
        print(f"\n  {c('red', '🚨 Conflicts detected:')}")
        for conflict in result['conflicts']:
            print(f"    {conflict[:120]}")

    print()


def print_final_payload(agent: IPSAgent, case_name: str):
    """Print the final Perform staging payload."""
    payload = agent.stage_to_perform()
    print(f"\n{'═'*70}")
    print(c('bold', f"  📋  FINAL PERFORM STAGING PAYLOAD — {case_name}"))
    print(f"{'═'*70}")
    print(json.dumps(payload, indent=2, default=str))
    print(f"\n{'═'*70}")
    print(c('green', c('bold', "  ✅  Ready to push to Perform compliance approval queue")))
    print(f"{'═'*70}\n")


# ─────────────────────────────────────────────────────────────
# TEST CASE 1 — NJ High-Net-Worth Individual
# Muni-focused, dual-state (NJ/FL), AMT concern, no ESG
# ─────────────────────────────────────────────────────────────

TEST_CASE_1 = {
    "name": "NJ High-Net-Worth Individual — Sarah Chen",
    "client_name": "Sarah Chen",
    "description": "High tax bracket NJ resident, splits time with FL, muni-focused, AMT concern",
    "utterances": [
        {
            "speaker": "csr",
            "text": "Good morning Sarah. I wanted to walk through your investment parameters today and make sure we have everything set up properly.",
        },
        {
            "speaker": "client",
            "text": "Sure, happy to do that. This will be my personal account — just my own savings, nothing joint.",
        },
        {
            "speaker": "csr",
            "text": "Great. And in terms of tax situation, I know you're in New Jersey — are you a full-time NJ resident?",
        },
        {
            "speaker": "client",
            "text": "Well, mostly New Jersey, but we spend about four months a year in Florida now. I'm definitely in the highest tax bracket.",
        },
        {
            "speaker": "csr",
            "text": "Got it — so dual state. Are you still paying NJ income tax on the full year?",
        },
        {
            "speaker": "client",
            "text": "Yes, still domiciled in New Jersey so NJ taxes apply. I'd like the portfolio to focus on New Jersey munis, maybe 70% NJ, 30% national.",
        },
        {
            "speaker": "csr",
            "text": "Understood. And your accountant mentioned something about AMT last year — are you subject to the Alternative Minimum Tax?",
        },
        {
            "speaker": "client",
            "text": "Yes actually, I was hit by AMT last year. So please make sure you exclude any AMT paper from the portfolio.",
        },
        {
            "speaker": "csr",
            "text": "Absolutely. In terms of credit quality, any minimum rating you want to stick to?",
        },
        {
            "speaker": "client",
            "text": "I want to be safe. No junk bonds, no high yield — keep it investment grade only. I don't want anything below BBB.",
        },
        {
            "speaker": "csr",
            "text": "And time horizon? When might you need access to a significant portion of this?",
        },
        {
            "speaker": "client",
            "text": "This is long-term money. I won't need it for at least ten years, probably longer. Intermediate to long duration is fine.",
        },
        {
            "speaker": "csr",
            "text": "Any companies or sectors you'd prefer to avoid?",
        },
        {
            "speaker": "client",
            "text": "Yes — no tobacco, no gambling, and nothing related to weapons or defense. I don't have a formal ESG mandate, just those specific exclusions.",
        },
        {
            "speaker": "csr",
            "text": "Understood. And on risk — how would you characterize your overall tolerance?",
        },
        {
            "speaker": "client",
            "text": "I'm conservative. Preserving capital is more important to me than chasing yield. I can't afford to lose principal.",
        },
        {
            "speaker": "csr",
            "text": "Do you need any regular cash distributions from this portfolio?",
        },
        {
            "speaker": "client",
            "text": "Not regularly. Maybe keep $50,000 in cash available at all times for liquidity, but no scheduled withdrawals needed.",
        },
        {
            "speaker": "csr",
            "text": "And how often should we rebalance the portfolio against its targets?",
        },
        {
            "speaker": "client",
            "text": "Quarterly makes sense I think. Let's do calendar-based quarterly rebalancing.",
        },
    ]
}


# ─────────────────────────────────────────────────────────────
# TEST CASE 2 — California Revocable Trust
# ESG mandate, legacy portfolio transition, capital gains budget
# ─────────────────────────────────────────────────────────────

TEST_CASE_2 = {
    "name": "California Revocable Trust — The Martinez Family",
    "client_name": "Robert Martinez",
    "description": "CA revocable trust, strong ESG, legacy bonds to transition, capital gains budget",
    "utterances": [
        {
            "speaker": "csr",
            "text": "Morning Robert. This account is structured as a revocable trust, correct?",
        },
        {
            "speaker": "client",
            "text": "Yes, it's our family revocable trust — California residents. The trust was set up a few years ago.",
        },
        {
            "speaker": "csr",
            "text": "And tax status — are you looking for California tax-exempt income?",
        },
        {
            "speaker": "client",
            "text": "Absolutely. We're in the highest California bracket, so state and federal exempt is the goal. California munis preferred.",
        },
        {
            "speaker": "csr",
            "text": "Great. Now, you mentioned ESG was important to the family — can you tell me more about your preferences?",
        },
        {
            "speaker": "client",
            "text": "Yes, we have a strong ESG mandate. We want full socially responsible investing. No fossil fuels — and that means no oil, no coal, no natural gas. Also no weapons manufacturers, no private prisons, and no tobacco.",
        },
        {
            "speaker": "csr",
            "text": "Got it. Do you want that as a full negative screening mandate or ESG integration scoring?",
        },
        {
            "speaker": "client",
            "text": "Negative screening — we want those sectors completely excluded, not just scored lower.",
        },
        {
            "speaker": "csr",
            "text": "Understood. On credit quality?",
        },
        {
            "speaker": "client",
            "text": "We'd like very high quality — AA or better. We're comfortable going down to single-A in munis if the ESG profile is strong.",
        },
        {
            "speaker": "csr",
            "text": "What about the legacy portfolio? I understand you have some existing bonds coming over.",
        },
        {
            "speaker": "client",
            "text": "Yes, we have about $1.2M in existing bonds. There's a CUSIP — 13063DAA2 — that's a California GO bond we definitely want to keep. And there's some energy sector exposure, maybe 200K worth, we want to liquidate that. The rest we'd like to transition gradually to avoid a huge tax hit.",
        },
        {
            "speaker": "csr",
            "text": "Good. What's your capital gains budget for the transition year?",
        },
        {
            "speaker": "client",
            "text": "We'd like to limit total net realized gains to no more than $100,000 in the first year. And please maximize tax-loss harvesting wherever possible to offset.",
        },
        {
            "speaker": "csr",
            "text": "Duration preferences?",
        },
        {
            "speaker": "client",
            "text": "Intermediate duration — somewhere in the 3 to 7 year range. We don't want to take a lot of interest rate risk.",
        },
        {
            "speaker": "csr",
            "text": "Risk tolerance overall?",
        },
        {
            "speaker": "client",
            "text": "Moderate conservative. Income is the priority, some growth is nice but not at the expense of principal risk.",
        },
        {
            "speaker": "csr",
            "text": "Any scheduled cash needs we should plan around?",
        },
        {
            "speaker": "client",
            "text": "We make a charitable distribution every December — about $75,000. Please make sure there's always enough cash available for that.",
        },
    ]
}


# ─────────────────────────────────────────────────────────────
# TEST CASE 3 — Conservative Retiree
# Capital preservation, monthly withdrawals, discount bond concern
# ─────────────────────────────────────────────────────────────

TEST_CASE_3 = {
    "name": "Conservative Retiree — Frank Deluca",
    "client_name": "Frank Deluca",
    "description": "Retired, needs monthly income withdrawals, discount bond concern, ultra-conservative",
    "utterances": [
        {
            "speaker": "csr",
            "text": "Frank, good to talk today. This is your personal IRA account we're setting up parameters for, right?",
        },
        {
            "speaker": "client",
            "text": "Yes, it's my IRA. I rolled it over from my old employer plan last year.",
        },
        {
            "speaker": "csr",
            "text": "And since it's an IRA, tax status would be fully taxable on distributions — is that your understanding?",
        },
        {
            "speaker": "client",
            "text": "Yes, I know withdrawals get taxed as ordinary income. I'm not in a particularly high bracket now that I'm retired, so taxable is fine.",
        },
        {
            "speaker": "csr",
            "text": "What's most important to you with this money, Frank?",
        },
        {
            "speaker": "client",
            "text": "This is my retirement nest egg. Safety above everything. I absolutely cannot afford to lose this principal — capital preservation is number one.",
        },
        {
            "speaker": "csr",
            "text": "What kind of credit quality floor do you want to set?",
        },
        {
            "speaker": "client",
            "text": "Only the highest quality. I don't want anything below double-A. Preferably triple-A if possible, but AA is fine too.",
        },
        {
            "speaker": "csr",
            "text": "Duration — how long are you comfortable holding bonds?",
        },
        {
            "speaker": "client",
            "text": "Nothing too long. Keep it short to intermediate — I'd say under 5 years, maybe 2 to 5 at most. I don't want interest rate risk.",
        },
        {
            "speaker": "csr",
            "text": "Do you need regular income from this account?",
        },
        {
            "speaker": "client",
            "text": "Yes, I need $4,000 every month — that's my living expense supplement on top of Social Security. I've been counting on that for years now.",
        },
        {
            "speaker": "csr",
            "text": "And how would you like us to source that cash each month — from maturing bonds, or would you like a dedicated cash sleeve?",
        },
        {
            "speaker": "client",
            "text": "I'd rather use the interest and maturity proceeds first. Only sell bonds if absolutely necessary.",
        },
        {
            "speaker": "csr",
            "text": "Any sector restrictions or ESG preferences?",
        },
        {
            "speaker": "client",
            "text": "No specific ESG requirements. Just quality — no high yield, no speculative grade. I don't really care about sectors.",
        },
        {
            "speaker": "csr",
            "text": "One thing I want to flag — sometimes in this rate environment, we come across bonds trading at deep discounts to par. Are you comfortable holding market discount bonds?",
        },
        {
            "speaker": "client",
            "text": "I don't like buying bonds at a deep discount — I understand there's an ordinary income issue when they mature or get sold. Let's just stick to bonds at par or at a premium.",
        },
        {
            "speaker": "csr",
            "text": "Understood, that's a de minimis consideration. Any AMT concerns given your income level?",
        },
        {
            "speaker": "client",
            "text": "No, I'm nowhere near AMT territory at my income. AMT is not a concern.",
        },
        {
            "speaker": "csr",
            "text": "And rebalancing — how often should we review and rebalance against targets?",
        },
        {
            "speaker": "client",
            "text": "Honestly I'd prefer less frequent intervention — annual rebalancing is probably fine for me.",
        },
    ]
}


# ─────────────────────────────────────────────────────────────
# TEST RUNNER
# ─────────────────────────────────────────────────────────────

def run_test_case(test_case: dict, delay: float = 0.2):
    """Run a single test case end-to-end."""
    print(f"\n{'═'*70}")
    print(c('bold', f"  TEST CASE: {test_case['name']}"))
    print(f"  {c('dim', test_case['description'])}")
    print(f"{'═'*70}")

    # Initialize fresh agent
    agent = IPSAgent()
    agent.profile.client_name = test_case["client_name"]

    print(f"\n  {c('green', '▶')} Starting simulated transcription feed...\n")

    # Process each utterance through the simulated transcription
    for utterance in simulate_voice_transcription(test_case["utterances"], delay=delay):
        speaker = utterance["speaker"]
        text = utterance["text"]

        # Show transcript line
        spk_label = c('blue', "CSR") if speaker == "csr" else c('cyan', "CLIENT")
        print(f"  {spk_label}: {text[:100]}{'...' if len(text) > 100 else ''}")

        # Only extract from client utterances
        if speaker == "client":
            result = agent.process_transcript_chunk(text, speaker="client")
            print_turn_result(result)
        else:
            # Still log CSR utterances for audit
            agent.profile.conversation_history.append({
                "role": "user",
                "content": f"[CSR]: {text}"
            })

    # Final payload
    print_final_payload(agent, test_case["name"])
    return agent


def run_all_cases(delay: float = 0.2):
    """Run all three test cases sequentially."""
    cases = [TEST_CASE_1, TEST_CASE_2, TEST_CASE_3]
    agents = []
    for case in cases:
        print(f"\n{'#'*70}")
        agent = run_test_case(case, delay=delay)
        agents.append(agent)
        print(f"\n  Press Enter to continue to next test case...")
        input()
    return agents


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IPS Agent Test Cases")
    parser.add_argument("--case", type=int, choices=[1, 2, 3],
                        help="Run a specific test case (1, 2, or 3). Runs all if omitted.")
    parser.add_argument("--fast", action="store_true",
                        help="Skip delays between utterances (for CI/batch testing)")
    args = parser.parse_args()

    delay = 0.0 if args.fast else 0.2

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║          IPS AGENT — VOICE TRANSCRIPTION TEST HARNESS               ║
║          Investortools Perform Integration Layer                     ║
╚══════════════════════════════════════════════════════════════════════╝

  Three client archetypes:
  [1] NJ HNW Individual    — Dual-state munis, AMT, sector exclusions
  [2] CA Revocable Trust   — ESG mandate, legacy transition, gains budget
  [3] Conservative Retiree — Capital preservation, monthly withdrawals

  Each case runs through a realistic client conversation, showing:
  • Real-time NER extraction per utterance
  • Confidence scoring (green ≥90% / amber 70–89% / red <70%)
  • CSR nudges triggered by detected topics
  • Conflict detection between profile fields
  • Final Perform-ready JSON payload

  In production: replace simulate_voice_transcription() with:
  • Deepgram WebSocket streaming  →  deepgram.com/developers
  • AssemblyAI Real-Time          →  assemblyai.com/docs/real-time
  • Azure Speech SDK              →  aka.ms/speech-sdk
""")

    if args.case == 1:
        run_test_case(TEST_CASE_1, delay=delay)
    elif args.case == 2:
        run_test_case(TEST_CASE_2, delay=delay)
    elif args.case == 3:
        run_test_case(TEST_CASE_3, delay=delay)
    else:
        run_all_cases(delay=delay)
