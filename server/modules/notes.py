"""Quick notes: one scratchpad saved to data/notes.md on the PC, synced live between devices."""
from __future__ import annotations

import time

from ..paths import NOTES_PATH
from .base import ActionError, Module, action

MAX_CHARS = 200_000


class NotesModule(Module):
    name = "notes"

    async def start(self) -> None:
        text = NOTES_PATH.read_text("utf-8") if NOTES_PATH.exists() else ""
        self.state = {"text": text, "rev": 0, "updated": NOTES_PATH.stat().st_mtime if NOTES_PATH.exists() else None, "by": None}
        self.hub.publish("notes", self.state)

    @action
    async def save(self, args, client):
        text = args.get("text")
        if not isinstance(text, str):
            raise ActionError("Notes must be text.")
        if len(text) > MAX_CHARS:
            raise ActionError("Notes are too long (200,000 characters max).")
        tmp = NOTES_PATH.with_suffix(".tmp")
        tmp.write_text(text, "utf-8")
        tmp.replace(NOTES_PATH)
        self.state = {"text": text, "rev": self.state["rev"] + 1, "updated": time.time(), "by": client.device.id}
        self.hub.publish("notes", self.state)
        return {"rev": self.state["rev"], "updated": self.state["updated"]}
