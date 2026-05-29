# together-todo — a tool-calling agent sandbox (v2)

A bilingual Korean/English Kanban where a child's message (typed, spoken, or
tapped) is **routed** to one of six tools that change the board. Built to
internalise one pattern: **route → dispatch**.

## What's new in v2

| Feature | Where it lives | The idea |
|---|---|---|
| **Usernames + multiple children** | `board.py` users (with age) | Every card has an `owner`. Two kids (민준 8, 서연 4) seeded with age-appropriate cards. The active child is **context we pass in** — the LLM never picks the child. |
| **Reverse / examine tool** | `reverse_task` + one dispatch row | Parent assessment: "숙제 아직 안 했어" sends a card **back** a column. Adding it was *one function + one enum value + one dispatch row* — exactly the lesson from the architecture diagram. |
| **House glossary** | `GLOSSARY` in `board.py` | Casual phrasing maps to a card. "양치질 했어?" and "양치 했어?" both hit the `양치` card. Extend the dict with your family's terms. |
| **Composable cards (verb recycling + tense)** | `VERBS` table + `parts()` | A card = `prefix + subject + verb`. The verb **conjugates by column**, teaching tense as the card moves: 양치 **하기** → 양치 **하는 중** → 양치 **했어!**. `하다` is recycled across 양치/숙제/정리; the prefix (`저녁`/`아침`) is recycled across 메뉴. Reversing a card rewinds its tense too. |
| **iPad-optimised UI** | `static/index.html` | 48px touch targets, 16px inputs (no iOS zoom), safe-area insets, `viewport-fit=cover`, 3-column landscape grid, horizontal snap-scroll in portrait. Card parts render as coloured **chips** so the recycled pieces and the changing tense are visible. |
| **Korean voice** | Web Speech API | 🔊 reads each card in the **correct tense** for its column; 🎤 voice input is one more channel into the same router. |

## The mental model (unchanged — that's the point)

```
  CHANNELS              ROUTER                  TOOLS
  tap  ─┐
  type ─┼─► router.handle(text, child) ─► register · start · complete
  voice ┘     (shared guardrails)             reverse · rate · predict
```

Add a tool = one `board.py` function + one row in `router._dispatch`. Swap the
brain (`rule_route` ↔ `gemini_route`) or the store (in-memory → MongoDB) and
nothing else changes.

## Files

| File | Role |
|---|---|
| `board.py` | Users, the six **tools**, `VERBS` conjugation table, `GLOSSARY`, parts→display/spoken composition, no-ML predictor. |
| `router.py` | `Action` schema, **rule_route** (offline), **gemini_route** (structured output), the **dispatch table**. |
| `cli.py` | Study route→dispatch in the terminal (pick a child, type, watch tense change). |
| `app.py` | FastAPI: `/users`, `/board?user=`, `/act`, `/tap`. |
| `static/index.html` | iPad-first board + voice + child switcher. |

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python cli.py                      # offline, no key — fastest way to learn
uvicorn app:app --reload           # http://localhost:8000
```

Switch the brain to the LLM: put a free [AI Studio key](https://aistudio.google.com/apikey)
in `.env`, set `USE_GEMINI=1`, restart. Same board, same tools.

## Try it

As **서연 (4)**: `양치 했어` · `손 씻을게` · `장난감 정리했어`
As **민준 (8)**: `숙제 다 했어` → then as a **parent**: `숙제 아직 안 했어` (reverse)
Either child: `내일 뭐 할까?` (per-child prediction)

MIT.
