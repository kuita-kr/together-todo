"""
app.py — thin web layer (v2). Every endpoint is scoped to a child (`user`).

    python -m uvicorn app:app --reload   ->   http://localhost:8000
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import board
import router

app = FastAPI(title="together-todo")
app.mount("/static", StaticFiles(directory="static"), name="static")


class Utterance(BaseModel):
    text: str
    user: int


@app.get("/")
def home():
    return FileResponse("static/index.html")


class UserIn(BaseModel):
    name: str
    age: int


@app.get("/users")
def get_users():
    return board.list_users()


@app.post("/users")
def create_user(u: UserIn):
    """Parent action: register a new child (name + age)."""
    return board.add_user(u.name, u.age)


@app.patch("/users/{uid}")
def edit_user(uid: int, u: UserIn):
    """Parent action: correct a child's name or age."""
    updated = board.update_user(uid, u.name, u.age)
    if not updated:
        return {"ok": False, "error": f"no user {uid}"}
    return updated


@app.delete("/users/{uid}")
def remove_user(uid: int):
    """Parent action: remove a child and their cards."""
    return {"ok": board.delete_user(uid)}


# --- Parent: task bag (backlog pool) ---------------------------------------
class BagItem(BaseModel):
    subject: str
    english: str = ""
    verb: str = "하다"
    prefix: str = ""
    kind: str = "binary"
    options: list[str] = []
    prefix_options: list[str] = []
    routine: bool = False


@app.get("/bag")
def get_bag():
    return board.bag_list()


@app.post("/bag")
def add_bag(item: BagItem):
    return board.bag_add(**item.model_dump())


@app.delete("/bag/{bid}")
def del_bag(bid: int):
    return {"ok": board.bag_remove(bid)}


@app.post("/bag/{bid}/assign")
def assign_bag(bid: int, payload: dict):
    """Materialize one template into a child's 할 일."""
    res = board.assign_bag(bid, payload.get("user"))
    return {"result": res, "board": board.snapshot(payload.get("user"))}


@app.post("/bag/assign-routine")
def assign_routine(payload: dict):
    """Manual bulk-fill: drop every routine template into a child's 할 일."""
    user = payload.get("user")
    assigned = board.assign_routine(user, auto_only=False)
    return {"assigned": len(assigned), "board": board.snapshot(user)}


# --- Parent: word bag (draggable prefixes) ---------------------------------
@app.get("/words")
def get_words():
    return board.words_list()


@app.post("/words")
def add_word(payload: dict):
    return board.word_add(payload.get("word", ""))


@app.delete("/words/{word}")
def del_word(word: str):
    return board.word_remove(word)


# --- Parent: menu memory + settings + PIN ----------------------------------
@app.get("/notes")
def get_notes():
    return board.menu_notes()


@app.get("/settings")
def get_settings():
    return board.settings


@app.post("/settings")
def set_settings(payload: dict):
    mode = payload.get("routine_mode")
    if mode in ("manual", "auto"):
        board.settings["routine_mode"] = mode
    return board.settings


@app.post("/parent/verify")
def parent_verify(payload: dict):
    return {"ok": board.verify_pin(payload.get("pin", ""))}


@app.post("/parent/pin")
def parent_pin(payload: dict):
    return {"ok": board.set_pin(payload.get("old", ""), payload.get("new", ""))}


@app.get("/board")
def get_board(user: int):
    board.ensure_today(user)          # auto-fill today's routine if mode == "auto"
    return board.snapshot(user)


@app.post("/act")
def act(u: Utterance):
    """Single entry point for every channel (type/voice), scoped to a child."""
    out = router.handle(u.text, u.user)
    out["board"] = board.snapshot(u.user)
    return out


@app.post("/tap")
def tap(payload: dict):
    """Buttons skip the LLM: a pre-resolved Action for one child's card."""
    tool, tid, user = payload.get("tool"), payload.get("task_id"), payload.get("user")
    fn = {
        "start": lambda: board.start_task(tid),
        "complete": lambda: board.complete_task(tid, choice=payload.get("choice")),
        "reverse": lambda: board.reverse_task(tid),
        "rate": lambda: board.rate_task(tid, payload.get("stars", 3)),
        "set_prefix": lambda: board.set_prefix(tid, payload.get("prefix", "")),
        "predict": lambda: board.predict_tasks(user),
    }.get(tool)
    result = fn() if fn else {"ok": False, "error": "unknown tool"}
    return {"result": result, "board": board.snapshot(user)}
