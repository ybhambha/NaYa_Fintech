# IPS Agent — Investortools Perform Integration Layer

An AI-powered co-pilot for Client Service Representatives at buy-side fixed-income
wealth management firms. Captures client conversations in real time, extracts
structured IPS parameters, and stages clean data to Investortools Perform.

---

## Project Structure

```
ips_agent/
├── agent/
│   └── ips_agent.py          # Core agent: NER, extraction, Perform staging
├── ui/
│   └── csr_interface.html    # Full CSR browser UI (open directly in Chrome)
├── tests/
│   └── test_cases.py         # 3 client test cases with simulated transcription
├── requirements.txt
└── README.md
```

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Run test cases
python tests/test_cases.py              # All three cases
python tests/test_cases.py --case 1    # NJ HNW individual
python tests/test_cases.py --case 2    # CA Revocable Trust (ESG + transition)
python tests/test_cases.py --case 3    # Conservative retiree (withdrawals)
python tests/test_cases.py --fast      # Skip delays (batch/CI mode)

# 4. Open the CSR UI
open ui/csr_interface.html             # macOS
start ui/csr_interface.html            # Windows
```

---

## Architecture

```
Client Voice / Transcript
        │
        ▼
┌───────────────────────────────────────┐
│  Layer 1: Simulated STT               │
│  simulate_voice_transcription()       │
│  → Replace with Deepgram / AssemblyAI │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  Layer 2: Pattern NER (fast, cheap)   │
│  run_pattern_ner()                    │
│  • Regex for credit, duration, state  │
│  • CUSIP detection                    │
│  • Withdrawal amount extraction       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  Layer 3: Claude Extraction (deep)    │
│  IPSAgent.process_transcript_chunk()  │
│  • Handles ambiguous / nuanced text   │
│  • Returns structured JSON            │
│  • Maintains multi-turn context       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  Layer 4: Deterministic Mapping       │
│  _apply_ai_extractions()              │
│  • All values mapped to Perform schema│
│  • Confidence scored (high/amber/low) │
│  • Conflict detection runs            │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  Layer 5: Perform Staging Payload     │
│  IPSAgent.stage_to_perform()          │
│  • Clean JSON / XML for Perform API   │
│  • Audit narrative generated          │
│  • Amber fields flagged for review    │
└───────────────────────────────────────┘
```

---

## Test Cases

### Case 1 — NJ High-Net-Worth Individual (Sarah Chen)
- Dual-state resident (NJ primary / FL secondary)
- AMT subject — AMT paper must be excluded
- Investment grade only, no tobacco/gambling/weapons
- Capital preservation objective
- $50K minimum cash cushion
- Quarterly rebalancing

### Case 2 — California Revocable Trust (Robert Martinez)
- Full SRI/ESG mandate — negative screening
- No fossil fuels, no weapons, no private prisons
- Legacy portfolio: $1.2M — one CUSIP to hold (13063DAA2), energy to liquidate
- Capital gains budget: $100K net gains limit
- Maximize tax-loss harvesting
- Annual $75K charitable withdrawal (December)

### Case 3 — Conservative Retiree (Frank Deluca)
- IRA Rollover account — fully taxable
- Capital preservation above all
- AA or better credit quality
- Short-Intermediate duration (2–5 years)
- Monthly withdrawal: $4,000 from maturing proceeds
- Restrict to par/premium bonds (de minimis concern)
- AMT not applicable
- Annual rebalancing

---

## Replacing Simulated Transcription with Live STT

The `simulate_voice_transcription()` function in `tests/test_cases.py` yields
pre-written utterances. Replace it with a real STT provider:

### Deepgram (recommended for real-time diarization)
```python
from deepgram import DeepgramClient, LiveOptions

dg = DeepgramClient(api_key=DEEPGRAM_API_KEY)
connection = dg.listen.live.v("1")
options = LiveOptions(
    model="nova-2",
    diarize=True,          # Speaker separation
    punctuate=True,
    language="en-US"
)
```

### AssemblyAI
```python
import assemblyai as aai
aai.settings.api_key = ASSEMBLYAI_API_KEY
transcriber = aai.RealtimeTranscriber(
    sample_rate=16_000,
    on_data=lambda t: agent.process_transcript_chunk(t.text, "client")
)
```

### Azure Speech SDK
```python
import azure.cognitiveservices.speech as speechsdk
speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
speech_config.request_word_level_timestamps()
audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
recognizer = speechsdk.SpeechRecognizer(speech_config, audio_config)
```

---

## Perform API Integration

The `stage_to_perform()` method generates a validated JSON payload.
Map this to Investortools Perform's web services endpoint:

```python
import requests

payload = agent.stage_to_perform()
response = requests.post(
    "https://your-perform-instance.investortools.com/api/v1/client-profiles/stage",
    json=payload,
    headers={"Authorization": f"Bearer {PERFORM_API_TOKEN}"}
)
```

Replace the endpoint URL and auth header with your firm's Perform instance details.
Perform's web services documentation covers the exact field names and endpoint paths.

---

## Extending the Agent

### Adding new Perform schema fields
Edit `PERFORM_SCHEMA` in `agent/ips_agent.py` to add new picklists.
Add corresponding patterns to `run_pattern_ner()` for fast detection.

### Adding new conflict rules
Add detection logic to `detect_conflicts()` in `agent/ips_agent.py`.

### Adding new test cases
Add a new dict following the `TEST_CASE_1` structure in `tests/test_cases.py`
and call `run_test_case()` with it.
