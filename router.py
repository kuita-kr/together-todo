"""
router.py — route -> dispatch (v2).

What changed from v1, and WHY it was easy:
  • Added the `reverse` tool. Look how small the change is — one enum value,
    one keyword list, one dispatch row. That is the whole lesson from the
    architecture diagram: "add a tool = one function + one dispatch row."
  • Every call is now scoped to a child (`owner`), because two kids share the
    app. The owner is CONTEXT we pass in — the LLM never picks the child.
  • Name resolution goes through the house GLOSSARY (board.normalize), so
    "양치질 했어?" and "양치 했어?" both land on the 양치 card.
"""

from __future__ import annotations
import os, json, re, urllib.request
from pydantic import BaseModel, Field
from typing import Literal, Optional

import board


class Action(BaseModel):
    tool: Literal["register", "start", "complete", "reverse", "rate", "predict"]
    task: Optional[str] = Field(None, description="Korean task subject or id")
    stars: Optional[int] = Field(None, ge=1, le=5)
    choice: Optional[str] = None
    subject: Optional[str] = None   # for register (also the auto-create fallback)
    english: Optional[str] = None   # for register
    verb: Optional[str] = None      # for register (하다/씻다/...)


# Mutating tools that act on an existing card. If we can't find the card the
# speaker named, they're talking about something new -> create it (see below).
_NEEDS_CARD = ("start", "complete", "reverse")


# --- DISPATCH TABLE: tool name -> board function (now owner-aware) ----------
def _dispatch(a: Action, owner: int) -> dict:
    tid = board.resolve_id(a.task, owner) if a.task else None

    # Bug fix: a child can name a chore the board doesn't have yet — e.g. says
    # "양치 했어" but has no 양치 card. Don't fail with "no card"; add it to
    # 할 일 (To-do) so the suggested phrases always do something useful.
    if a.tool in _NEEDS_CARD and tid is None:
        subject = a.subject or a.task or "새 할 일"
        return board.register_task(owner, subject, a.english or "",
                                   verb=a.verb or board.infer_verb(subject))

    if a.tool == "register":
        subject = a.subject or a.task or "새 할 일"
        return board.register_task(owner, subject, a.english or "",
                                   verb=a.verb or board.infer_verb(subject))
    if a.tool == "start":
        return board.start_task(tid)
    if a.tool == "complete":
        return board.complete_task(tid, choice=a.choice)
    if a.tool == "reverse":
        return board.reverse_task(tid)
    if a.tool == "rate":
        return board.rate_task(tid, a.stars or 3)
    if a.tool == "predict":
        return board.predict_tasks(owner)
    return {"ok": False, "error": "unknown tool"}


# --- Router 1: rule-based (offline) -----------------------------------------
# Order matters: reverse keywords are checked before complete, because
# "숙제 아직 안 했어" contains neither, but "다시 해" should beat a stray "했".
_RULES = [
    ("reverse",  ["아직", "안 했", "안 끝", "다시", "되돌", "안됐", "redo", "not done", "undo", "back"]),
    ("complete", ["다 했", "끝났", "완료", "했어", "done", "finished", "complete"]),
    ("start",    ["시작", "하는 중", "하고 있", "start", "begin", "doing"]),
    ("rate",     ["별점", "star", "rate", "좋아", "again"]),
    ("predict",  ["내일", "예측", "추천", "tomorrow", "predict", "suggest"]),
    ("register", ["추가", "등록", "만들", "add", "new", "register", "create"]),
]


def rule_route(utterance: str, owner: int) -> Action:
    text = utterance.lower()
    tool = "register"
    for name, kws in _RULES:
        if any(k.lower() in text for k in kws):
            tool = name
            break
    # past-tense ending (했어/었어/았어/랐어…) is a strong 'complete' signal,
    # but must NOT override a parent's 'reverse' ("아직 안 했어").
    if tool != "reverse" and re.search(r"(했|었|았|랐|렀|였|왔)\w*어", text):
        tool = "complete"
    # resolve a known card for THIS child, via the house glossary
    norm = board.normalize(utterance)
    task = None
    for c in board.board.values():
        if c["owner"] == int(owner) and c["subject"] in norm:
            task = c["subject"]
            break
    # never 'register' something that already exists — treat it as 'start'
    if task and tool == "register":
        tool = "start"
    stars = None
    m = re.search(r"([1-5])\s*(점|star|stars|개)", text)
    if m:
        stars, tool = int(m.group(1)), "rate"
    # Derive a bare-noun subject + a verb whenever no existing card matched, so
    # both 'register' and the auto-create fallback (e.g. "양치 했어" with no card)
    # land a clean card. Strip rule keywords AND verb conjugations from the noun.
    subject, verb = None, None
    if not task:
        cleaned = board.normalize(utterance)
        noise = sum((kws for _, kws in _RULES), [])
        noise += [forms[col].rstrip("!") for forms in board.VERBS.values()
                  for col in board.COLUMNS]
        for k in sorted(noise, key=len, reverse=True):   # longest first
            cleaned = re.sub(re.escape(k), "", cleaned, flags=re.IGNORECASE)
        subject = cleaned.strip(" 해줘을를.!?") or board.normalize(utterance)
        verb = board.infer_verb(utterance)
    return Action(tool=tool, task=task, stars=stars, subject=subject, verb=verb)


# --- Router 2: Gemini structured output -------------------------------------
_GEMINI_KEY = os.getenv("GOOGLE_API_KEY", "")
_GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
               "gemini-2.0-flash:generateContent")

# SINGLE SHARED GUARDRAIL layer — one prompt governs every channel & child.
_SYSTEM = (
    "You are the router for a bilingual Korean/English children's chore app used "
    "by two children of different ages. Read the message (from a child or a parent) "
    "and choose exactly one tool. Be warm; never scold. "
    "Finishing -> complete. Beginning -> start. Scoring/'again?' -> rate. "
    "Asking about tomorrow -> predict. Asking for a new task -> register. "
    "A PARENT saying a task is not really finished ('아직 안 했어', 'do it again') "
    "-> reverse (send the card back). Return ONLY the structured Action; put the "
    "task's Korean subject in `task`."
)

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string",
                 "enum": ["register", "start", "complete", "reverse", "rate", "predict"]},
        "task": {"type": "string"},
        "stars": {"type": "integer"},
        "choice": {"type": "string"},
        "subject": {"type": "string"},
        "english": {"type": "string"},
        "verb": {"type": "string"},
    },
    "required": ["tool"],
}


def gemini_route(utterance: str, owner: int) -> Action:
    body = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"parts": [{"text": utterance}]}],
        "generationConfig": {"responseMimeType": "application/json",
                             "responseSchema": _RESPONSE_SCHEMA},
    }
    req = urllib.request.Request(f"{_GEMINI_URL}?key={_GEMINI_KEY}",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    return Action(**json.loads(raw))


# --- Public entry point -----------------------------------------------------
def handle(utterance: str, owner: int) -> dict:
    """route the utterance to an Action for THIS child, then run the tool."""
    use_gemini = os.getenv("USE_GEMINI") == "1" and _GEMINI_KEY
    try:
        action = (gemini_route if use_gemini else rule_route)(utterance, owner)
    except Exception as e:
        action = rule_route(utterance, owner)
        print(f"[router] gemini failed ({e}); fell back to rules")
    result = _dispatch(action, owner)
    return {"utterance": utterance, "owner": owner,
            "action": action.model_dump(), "result": result}
