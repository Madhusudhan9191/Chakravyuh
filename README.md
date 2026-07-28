# CHAKRA — Decision Intelligence for GST Supply-Chain Compliance

> *"Don't just tell me there's a problem. Help me understand it, replay it,
> simulate the fix, and hand me the paperwork."*

Built for **Build with Gemma — Bengaluru AI Sprint** (Track 2: Financial
Compliance & Risk Triage). Everything runs on one laptop, offline: Gemma 4
via LM Studio reads the paper and writes the paperwork; deterministic
graph + arithmetic decide everything in between.


## Prerequisites

- **Python 3.10+**
- **[LM Studio](https://lmstudio.ai/)** — load `gemma-4-E4B-it`, go to Developer tab → Start Server (port 1234)
- **Tesseract OCR** (required by pytesseract for invoice image reading)
  - **Windows:** Download installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
  - **Mac:** `brew install tesseract`
  - **Linux:** `sudo apt install tesseract-ocr`

## Tech Stack

| Layer | Technology |
|---|---|
| Offline LLM | Gemma 4 via LM Studio (OpenAI-compatible API) |
| Backend | FastAPI + Uvicorn |
| Graph Analysis | NetworkX |
| OCR | Pytesseract + Pillow |
| Compliance Rules | Deterministic Python rule engine |
| UI | Single `index.html` — no build step, works offline |

## Run it (Windows / Mac)

```bash
# 1. LM Studio: load gemma-4-E4B-it, Developer tab → Start Server (port 1234)
# 2. Backend:
cd backend
pip install -r requirements.txt
python smoke_test.py            # 30-second health check
python server.py                # → http://localhost:8000
```

Demo buttons in the sidebar: **Demo ⚡** loads the pre-verified dataset
instantly (rehearsal hotkey); **Demo live** pushes the same 9 invoice photos
through the real Gemma pipeline on stage.

## What the accountant gets

1. **Monday-morning to-do list** — findings ranked by rupees, never by
   confidence score. Two hero numbers: hours of work replaced, ₹ protected.
2. **The alert card** — WHY (graph evidence) · EVIDENCE (invoice pixels +
   the trust-ledger receipts) · EXPOSURE (₹, CGST section) · ACTION
   (Gemma-drafted vendor email, client advisory, payment hold, file note).
3. **Evidence playback** — step-by-step replay of exactly how CHAKRA reached
   a conclusion. No black box.
4. **Counterfactual simulator** — "what if I drop this supplier today?"
   Re-runs the deterministic layer on the modified world and shows ₹ saved.
   *Only possible because the decision layer is pure math — you can re-run
   an algorithm; you cannot re-run an opinion.*
5. **Compliance time machine** — replays the network invoice-by-invoice:
   when the ring formed, which document introduced the exposure.

## Governance (why a CA can act on this)

- Gemma **reads** documents and **writes** paperwork. It never decides.
- Every number crossing from Gemma into the ledger passes a deterministic
  trust layer: GSTIN modulo-36 checksum + position-aware OCR-confusion fix +
  two-pass zoom re-read, and majority-vote arithmetic reconciliation of all
  money fields (Σ line items, CGST/rate, SGST/rate, total−taxes as
  independent witnesses; repairs need ≥2 agreeing witnesses).
- Pre-event validation: 7 live extraction runs, 3 machines, 2 model sizes,
  ~12 distinct model errors — **zero wrong values silently accepted**.
  Every error was either repaired by arithmetic or routed to manual review.

## Prior-work disclosure

The synthetic-invoice generator, the extraction test harness, and the trust
layer (checksum/majority-vote repair logic) were developed and validated
before the event as preparatory testing, and are reused here with this
disclosure. The server, rules engine, exposure propagation, counterfactual
simulator, time machine, action engine and the entire UI were built during
the hackathon. An earlier personal project (GraphRACA) inspired the
retrieval scaffolding approach but no code from it is included.
