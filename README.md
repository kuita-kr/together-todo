# together-todo — a tool-calling agent sandbox

A tiny, runnable reference for the ONE pattern to internalise before the
hackathon: **route → dispatch**. A bilingual Korean/English Kanban where a
child's message (typed, spoken, or tapped) is routed to one of five tools that
actually change the board.

This is the action-world cousin of an adaptive **retrieval** agent: same
classify-then-route skeleton, but the tools have **side effects** (they create
and move cards) instead of just fetching text.

## The mental model (the ElevenLabs "agent solution overview")

```
  CHANNELS            ROUTER                 TOOLS (specialist actions)
  tap  ─┐
  type ─┼─►  router.handle()  ─►  register · start · complete · rate · predict
  voice ┘    (one shared            │
              guardrail layer)      └─ each changes the in-memory board
```

- **Channels** = input surfaces. A button tap, a typed sentence, and a spoken
  phrase all funnel into the *same* `router.handle()`. The channel only changes
  modality; the brain and the tools are shared.
- **Router** = picks ONE tool and its arguments, returned as a structured
  `Action` (Pydantic). Guardrails/tone live here once and apply to every channel.
- **Tools** = the five functions in `board.py`. The `_dispatch` table in
  `router.py` is the "router → specialist" arrows from the diagram.

## Files

| File | What it teaches |
|---|---|
| `board.py` | The five **tools** + in-memory board + a no-ML frequency×recency predictor (the "learns from last week" bit). |
| `router.py` | The new concept. `Action` schema, a **rule-based** router (offline), a **Gemini structured-output** router (real), and the **dispatch table**. |
| `cli.py` | Study `route → dispatch` in the terminal, zero setup. |
| `app.py` | Thin FastAPI layer (matches the NHS-navigator shape). `/act`, `/tap`, `/board`. |
| `static/index.html` | The Kanban + text/voice input + **Korean Web Speech TTS** (free). |

## 20-minute learning path (do this before the team meeting)

1. **See it with no setup** — `pip install pydantic` then `python cli.py`.
   Type `손 씻기 다 했어`, watch `router → complete` move the card. Read
   `router.py` top to bottom; the dispatch table is the whole lesson.
2. **Run the UI** — `pip install -r requirements.txt` then
   `python -m uvicorn app:app --reload` → http://localhost:8000.
   Tap buttons (the "tap channel"), type sentences, press 🎤 to speak Korean,
   tap 🔊 to hear a card read aloud.
3. **Swap the brain** — drop a free [AI Studio key](https://aistudio.google.com/apikey)
   into `.env`, set `USE_GEMINI=1`, restart. Same board, same tools — now the
   LLM does the routing via `responseSchema`. Notice nothing else changed.

## What to bring to the meeting

- The **route → dispatch** split, and *who owns what*: the LLM only chooses an
  Action; **your code** executes side effects. That boundary is what keeps a
  tool-calling agent safe and testable.
- Buttons are pre-resolved Actions — fast and always-correct, so the demo's
  backbone never depends on the LLM (or on hearing a child correctly).
- Where the team plugs in Saturday: add a tool = add a `board.py` function + one
  row in the dispatch table. Swap the in-memory board for MongoDB and the
  architecture is unchanged.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # optional; runs fine without it
python -m uvicorn app:app --reload
```

MIT.
