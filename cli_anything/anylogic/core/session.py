"""Persistent CLI session: current model, live-API connection, undo/redo.

State lives in ``~/.cli-anything-anylogic/`` (override with the env var
``CLI_ANYTHING_ANYLOGIC_HOME``). Every mutation snapshots the .alp file
first, so ``session undo`` restores the exact previous bytes.
"""

import json
import os
import shutil
import time

MAX_HISTORY = 50


def state_dir() -> str:
    d = os.environ.get("CLI_ANYTHING_ANYLOGIC_HOME") or os.path.join(
        os.path.expanduser("~"), ".cli-anything-anylogic")
    os.makedirs(os.path.join(d, "snapshots"), exist_ok=True)
    return d


def _locked_save_json(path, data, **dump_kwargs) -> None:
    """Write JSON with exclusive file locking (see guides/session-locking.md)."""
    try:
        f = open(path, "r+")
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        f = open(path, "w")
    with f:
        _locked = False
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            _locked = True
        except (ImportError, OSError):
            pass
        try:
            f.seek(0)
            f.truncate()
            json.dump(data, f, **dump_kwargs)
            f.flush()
        finally:
            if _locked:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class Session:
    def __init__(self):
        self.dir = state_dir()
        self.path = os.path.join(self.dir, "session.json")
        self.data = {"project_path": None, "live": {}, "undo": [], "redo": []}
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (ValueError, OSError):
                pass

    def save(self):
        _locked_save_json(self.path, self.data, indent=2)

    # ── current model ────────────────────────────────────────────────
    @property
    def project_path(self):
        return self.data.get("project_path")

    def set_project(self, path):
        path = os.path.abspath(path) if path else None
        if path != self.project_path:
            self._drop(self.data["undo"] + self.data["redo"])
            self.data["undo"], self.data["redo"] = [], []
        self.data["project_path"] = path
        self.save()

    # ── AnyLogic edition ─────────────────────────────────────────────
    @property
    def edition(self):
        return self.data.get("edition")

    def set_edition(self, edition):
        self.data["edition"] = edition
        self.save()

    # ── live API ─────────────────────────────────────────────────────
    @property
    def live(self) -> dict:
        return self.data.setdefault("live", {})

    def set_live(self, token=None, port=None, model=None):
        if token is not None:
            self.live["token"] = token
        if port is not None:
            self.live["port"] = int(port)
        if model is not None:
            self.live["model"] = model
        self.save()

    def clear_live(self):
        self.data["live"] = {}
        self.save()

    # ── undo / redo ──────────────────────────────────────────────────
    def snapshot(self, alp_path: str, label: str):
        """Store the current bytes of ``alp_path`` before a mutation."""
        snap = os.path.join(self.dir, "snapshots", f"{time.time_ns()}.alp")
        shutil.copyfile(alp_path, snap)
        self.data["undo"].append({"file": snap, "target": os.path.abspath(alp_path), "label": label,
                                  "at": time.strftime("%Y-%m-%d %H:%M:%S")})
        self._drop(self.data["redo"])
        self.data["redo"] = []
        while len(self.data["undo"]) > MAX_HISTORY:
            self._drop([self.data["undo"].pop(0)])
        self.save()

    def _swap(self, from_key, to_key):
        stack = self.data[from_key]
        if not stack:
            raise RuntimeError(f"Nothing to {from_key}")
        entry = stack.pop()
        target = entry["target"]
        back = os.path.join(self.dir, "snapshots", f"{time.time_ns()}.alp")
        shutil.copyfile(target, back)
        self.data[to_key].append({**entry, "file": back})
        shutil.copyfile(entry["file"], target)
        os.remove(entry["file"])
        self.save()
        return {"action": from_key, "label": entry["label"], "file": target}

    def undo(self):
        return self._swap("undo", "redo")

    def redo(self):
        return self._swap("redo", "undo")

    def history(self) -> list:
        return [{"label": e["label"], "at": e.get("at"), "file": e["target"]} for e in self.data["undo"]]

    @staticmethod
    def _drop(entries):
        for e in entries:
            try:
                os.remove(e["file"])
            except OSError:
                pass

    def status(self) -> dict:
        live = dict(self.live)
        if live.get("token"):
            live["token"] = live["token"][:4] + "..."  # never echo the full token
        return {"project_path": self.project_path, "undo_depth": len(self.data["undo"]),
                "redo_depth": len(self.data["redo"]), "live": live, "state_dir": self.dir}
