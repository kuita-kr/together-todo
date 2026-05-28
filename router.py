"""
router.py — the ONE new thing to learn: route -> dispatch.

Two routers live here:
  1. rule_route()   — no API key, pure Python. Run this FIRST to *see* the
                      dispatch loop without any cloud dependency.
  2. gemini_route() — the real thing: the LLM returns structured JSON matching
                      the Action schema (Gemini's `responseSchema`, the same
                      gemini.py-style REST call you already use).

Both produce the SAME Action object, so the dispatch code below doesn't care
which router made it. That interchangeability is the whole point: the channel
(taps/voice/text) and the brain (rules/LLM) are swappable; the tool layer is
fixed. Swap rule_route for gemini_route by setting USE_GEMINI=1 in .env.
"""

from __future__ import annotations
import os, json, re, urllib.request
from pydantic import BaseModel, Field
from typing import Literal, Optional

import board

# --- The Action: the router's structured output ----------------------------
# This is the contract between "the brain" and "the hands". The LLM must fill
# exactly these fields. In your NHS app the equivalent was the classification
# label; here it additionally names arguments for a side-effecting tool.
class Action(BaseModel):
    tool: Literal["register", "start", "complete", "rate", "predict"]
    task: Optional[str] = Field(None, description="Korean task name or id")
    stars: Optional[int] = Field(None, ge=1, le=5)
    choice: Optional[str] = None
    korean: Optional[str] = None   # for register
    english: Optional[str] = None  # for register


# --- The DISPATCH TABLE: tool name -> the real function in board.py ---------
# This dict IS the "router branches to specialist agent" arrows in the
# ElevenLabs diagram. Add a tool? Add a row. Nothing else changes.
def _dispatch(a: Action) -> dict:
    tid = board.resolve_id(a.task) if a.task else None
    if a.tool == "register":
        return board.register_task(a.korean or a.task or "새 할 일",
                                   a.english or "")
    if a.tool == "start":
        return board.start_task(tid)
    if a.tool == "complete":
        return board.complete_task(tid, choice=a.choice)
    if a.tool == "rate":
        return board.rate_task(tid, a.stars or 3)
    if a.tool == "predict":
        return board.predict_tasks()
    return {"ok": False, "error": "unknown tool"}


# --- Router 1: rule-based (offline, study this first) -----------------------
# Crude keyword matching — NOT how you'd ship it, but it makes the route->
# dispatch flow visible with zero setup. Korean + English trigger words.
_RULES = [
    ("complete", ["다 했", "끝났", "완료", "했어", "done", "finished", "complete"]),
    ("start",    ["시작", "하는 중", "하고 있", "start", "begin", "doing"]),
    ("rate",     ["별점", "점", "star", "rate", "좋아", "again"]),
    ("predict",  ["내일", "예측", "추천", "tomorrow", "predict", "suggest"]),
    ("register", ["추가", "등록", "새", "만들", "add", "new", "register", "create"]),
]


def rule_route(utterance: str) -> Action:
    text = utterance.lower()
    tool = "register"
    for name, kws in _RULES:
        if any(k.lower() in text for k in kws):
            tool = name
            break
    # try to pull a known task name out of the utterance. Exact match first,
    # then a 2-char Korean prefix ("숙제" matches the card "숙제하기"). The LLM
    # router handles this far better — that's rather the point of upgrading.
    task = next((c["korean"] for c in board.board.values()
                 if c["korean"] in utterance), None)
    if not task:
        task = next((c["korean"] for c in board.board.values()
                     if c["korean"][:2] and c["korean"][:2] in utterance), None)
    stars = None
    m = re.search(r"([1-5])\s*(점|star|stars|개)", text)
    if m:
        stars, tool = int(m.group(1)), "rate"
    # for register, strip the trigger words so the card name is clean
    korean = None
    if tool == "register" and not task:
        all_kw = sum((kws for _, kws in _RULES), [])
        cleaned = utterance
        for k in all_kw:
            cleaned = re.sub(k, "", cleaned, flags=re.IGNORECASE)
        korean = cleaned.strip(" 해줘을를.!?") or utterance
    return Action(tool=tool, task=task, stars=stars, korean=korean)


# --- Router 2: Gemini structured output (the real router) -------------------
_GEMINI_KEY = os.getenv("GOOGLE_API_KEY", "")
_GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
               "gemini-2.0-flash:generateContent")

# This system instruction is your SINGLE SHARED GUARDRAIL layer — the thing you
# liked about the ElevenLabs demo. Written once, it governs every channel.
_SYSTEM = (
    "You are the router for a bilingual Korean/English children's chore app. "
    "Read the child's message (Korean or English) and choose exactly one tool. "
    "Be warm and encouraging; never scold. Map natural phrases to tools: "
    "finishing -> complete, beginning -> start, scoring -> rate, "
    "asking about tomorrow -> predict, asking for a new task -> register. "
    "Return ONLY the structured Action."
)

# Gemini's response schema = Pydantic-equivalent JSON Schema. Forcing the model
# to fill this is what makes the output safe to json.loads + dispatch.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string",
                 "enum": ["register", "start", "complete", "rate", "predict"]},
        "task": {"type": "string"},
        "stars": {"type": "integer"},
        "choice": {"type": "string"},
        "korean": {"type": "string"},
        "english": {"type": "string"},
    },
    "required": ["tool"],
}


def gemini_route(utterance: str) -> Action:
    body = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"parts": [{"text": utterance}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
        },
    }
    req = urllib.request.Request(
        f"{_GEMINI_URL}?key={_GEMINI_KEY}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    return Action(**json.loads(raw))   # validated by Pydantic — bad JSON raises


# --- The public entry point: route then dispatch ---------------------------
def handle(utterance: str) -> dict:
    """Route the utterance to an Action, then execute the tool. One call does
    the whole 'channel -> router -> tool' journey."""
    use_gemini = os.getenv("USE_GEMINI") == "1" and _GEMINI_KEY
    try:
        action = gemini_route(utterance) if use_gemini else rule_route(utterance)
    except Exception as e:
        # graceful fallback to rules if the LLM call fails mid-demo
        action = rule_route(utterance)
        print(f"[router] gemini failed ({e}); fell back to rules")
    result = _dispatch(action)
    return {"utterance": utterance, "action": action.model_dump(), "result": result}
