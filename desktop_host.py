"""Local desktop host: the original web design, backed by the Python stores.

No cloud account or browser-storage migration. The HTTP bridge is loopback-only,
authenticated with a per-launch token, and serializes writes with revision checks.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import mimetypes
import secrets
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

from vocabulary import VocabularyStore, parse_words, FORMATS_HELP
from question_bank import (discover_banks, read_bank, save_bank, parse_questions,
                           append_questions, FORMATS_HELP as QUESTION_HELP)

ROOT = Path(__file__).resolve().parent


class Workspace:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.store = VocabularyStore(self.directory, ROOT / "examples/vocabulary.json")
        self.lock = threading.RLock()
        self.undo_before = self.undo_after = None
        self.exam = None
        self.file_stamp = self.stamp()

    def stamp(self):
        return hashlib.sha256(self.store.path.read_bytes()).hexdigest() if self.store.path.exists() else None

    def revision(self):
        return hashlib.sha256(json.dumps(self.store.state, sort_keys=True).encode()).hexdigest()

    def snapshot(self):
        choices, errors = discover_banks(self.directory)
        banks = [{"id": str(path.resolve()), **read_bank(path)} for _, path in choices]
        return {"state": copy.deepcopy(self.store.state), "revision": self.revision(),
                "canUndo": self.undo_after == self.store.state and self.undo_before is not None,
                "banks": banks, "bankErrors": errors,
                "wordFormats": FORMATS_HELP, "questionFormats": QUESTION_HELP}

    def bank_path(self, bank_id):
        choices, _ = discover_banks(self.directory)
        found = next((p for _, p in choices if str(p.resolve()) == bank_id), None)
        if found is None:
            raise ValueError("That bank is no longer available. Reload the library.")
        return found

    def dispatch(self, action, args):
        with self.lock:
            # Another running version must never be silently overwritten.
            if self.stamp() != self.file_stamp:
                self.store = VocabularyStore(self.directory, ROOT / "examples/vocabulary.json")
                self.file_stamp = self.stamp()
                self.undo_before = self.undo_after = None
                if action != "load":
                    raise ValueError("The library changed in another window. Reload before editing.")
            if action not in ("load", "preview", "preview_groups", "export", "exam") and args.get("revision") != self.revision():
                raise ValueError("The library changed. Reload before applying this edit.")
            result, message = {}, ""
            try:
                if action == "load":
                    pass
                elif action == "book":
                    result["id"] = self.store.name_book(args["name"], args.get("id"))
                    message = "Book saved."
                elif action == "group":
                    result["id"] = self.store.name_group(args["name"], args.get("id"), args["book_id"])
                    message = "Group saved."
                elif action == "word":
                    self.store.put_words(args["group_id"], [args["word"]], args.get("id"))
                    message = "Word saved."
                elif action == "preview":
                    items, notes = (parse_questions if args.get("questions") else parse_words)(args["text"], args.get("format", "auto"))
                    result.update(preview=items, corrections=notes)
                elif action == "preview_groups":
                    result["group_preview"] = self.store.preview_group_paste(args["book_id"], args["text"])
                elif action == "paste_groups":
                    before = copy.deepcopy(self.store.state)
                    result["group_ids"] = self.store.paste_groups(args["book_id"], args["text"])
                    self.undo_before, self.undo_after = before, copy.deepcopy(self.store.state)
                    message = f"Pasted {len(result['group_ids'])} group(s). Source groups and existing progress were kept."
                elif action == "import":
                    words, notes = parse_words(args["text"], args.get("format", "auto"))
                    if args.get("name"):
                        result["id"] = self.store.import_group(args["book_id"], args["name"], words)
                        message = f"Created a group with {len(words)} words."
                    else:
                        added, skipped = self.store.put_words(args["group_id"], words)
                        message = f"Added {added} words; kept {skipped} existing words."
                elif action == "transfer":
                    before = copy.deepcopy(self.store.state)
                    count = self.store.transfer(args["kind"], args["source"], args["target"], args["ids"], args.get("copy", False))
                    self.undo_before, self.undo_after = before, copy.deepcopy(self.store.state)
                    message = f"{'Copied' if args.get('copy') else 'Moved'} {count} item(s). Undo is available."
                elif action == "undo":
                    if self.undo_before is None or self.undo_after != self.store.state:
                        raise ValueError("Cannot undo: the library has changed since that transfer.")
                    self.store.save(self.undo_before)
                    self.undo_before = self.undo_after = None
                    message = "Transfer undone."
                elif action == "begin":
                    if args.get("book_id"):
                        result["group_id"] = self.store.begin_book(args["book_id"], args.get("order", "Sequential"), args.get("restart", False))
                    else:
                        self.store.begin(args["group_id"], args.get("restart", False), args.get("order", "Sequential"))
                        result["group_id"] = args["group_id"]
                elif action == "rate":
                    session = self.store.state["sessions"][args["group_id"]]
                    if args.get("cursor") != session["cursor"]:
                        raise ValueError("This card was already answered.")
                    self.store.rate(args["group_id"], args["result"])
                    result["group_id"] = args["group_id"]
                    if args.get("book_id") and self.store.group_status(args["group_id"]) == "Complete":
                        result["group_id"] = self.store.begin_book(args["book_id"], args.get("order", "Sequential"))
                elif action == "bank":
                    path = self.bank_path(args["id"]) if args.get("id") else None
                    bank = read_bank(path) if path else {"schema_version": 1, "title": "", "questions": []}
                    # Prevent stale question editors from replacing a newer bank.
                    if path and args.get("original") != bank:
                        raise ValueError("This question bank changed. Reopen it before saving.")
                    bank["title"] = args.get("name", bank["title"])
                    if args.get("text"):
                        incoming, _ = parse_questions(args["text"], args.get("format", "auto"))
                        bank, _ = append_questions(bank, incoming)
                    if args.get("question"):
                        incoming, _ = parse_questions(json.dumps([args["question"]]), "json")
                        question = incoming["questions"][0]
                        if args.get("question_id"):
                            index = next(i for i, q in enumerate(bank["questions"]) if q["id"] == args["question_id"])
                            question["id"] = args["question_id"]
                            bank["questions"][index] = question
                        else:
                            bank, _ = append_questions(bank, {"questions": [question]})
                    directory = self.directory / "banks"
                    editable = path if path and path.resolve().parent == directory.resolve() else None
                    result["id"] = str(save_bank(bank, directory, editable))
                    message = "Question bank saved."
                elif action == "export":
                    if args.get("bank_id"):
                        payload = read_bank(self.bank_path(args["bank_id"]))
                    elif args.get("group_id"):
                        fields = ("term", "meaning", "phonetic", "expansion", "sequence")
                        payload = [{k: w[k] for k in fields} for w in self.store.group(args["group_id"])["words"]]
                    else:
                        payload = self.store.state
                    folder = self.directory / "exports"
                    folder.mkdir(parents=True, exist_ok=True)
                    path = folder / ("study-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    message = f"Saved to {path}"
                elif action == "exam":
                    path = self.bank_path(args["bank_id"])
                    minutes = args.get("minutes", [32, 32])
                    if len(minutes) != 2 or any(type(n) is not int or not 1 <= n <= 180 for n in minutes):
                        raise ValueError("Enter whole minutes from 1 to 180.")
                    if not any(q["module"] == 1 for q in read_bank(path)["questions"]):
                        raise ValueError("Add at least one Module 1 question first.")
                    if self.exam and self.exam.poll() is None:
                        message = "Your test is already open in its own window; its answers were not replaced."
                    else:
                        self.exam = subprocess.Popen([sys.executable, str(ROOT / "desktop.py"), "--exam", str(path), "--data-dir", str(self.directory), "--minutes", *map(str, minutes)])
                        message = "Opened the original exam window."
                else:
                    raise ValueError("Unknown workspace action.")
            finally:
                self.file_stamp = self.stamp()
            return {**self.snapshot(), **result, "message": message}


def make_server(workspace, port=0):
    token = secrets.token_urlsafe(32)
    assets = (ROOT / "web/dist").resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, status, content, mime="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            route = unquote(urlsplit(self.path).path)
            path = (assets / ("index.html" if route == "/" else route.lstrip("/"))).resolve()
            if not path.is_relative_to(assets) or not path.is_file():
                self.send(404, b"Not found", "text/plain")
                return
            self.send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")

        def do_POST(self):
            if self.path != "/api" or self.headers.get("Authorization") != f"Bearer {token}":
                self.send(403, b'{"error":"Not authorized"}')
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4_000_000:
                    raise ValueError("Request too large or empty.")
                request = json.loads(self.rfile.read(size))
                response = workspace.dispatch(request["action"], request.get("args", {}))
                self.send(200, json.dumps(response).encode())
            except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
                self.send(400, json.dumps({"error": str(exc) or "This item no longer exists. Reload the workspace."}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server, f"http://127.0.0.1:{server.server_port}/?desktop=1#{token}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--serve", action="store_true", help="Serve only, for local browser testing")
    parser.add_argument("--port", type=int, default=0)
    options = parser.parse_args()
    if not (ROOT / "web/dist/index.html").exists():
        raise RuntimeError("Build the interface first: cd web && npm ci && npm run build")
    if not options.serve:
        try:
            import webview
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "A desktop dependency is missing in this Python environment.\n\n"
                "On Windows, open 'Launch SAT Study Kit.cmd' to set up and use "
                "the project's own environment.\n\n"
                f"For this interpreter instead, run:\n\"{sys.executable}\" "
                "-m pip install -r requirements.txt"
            ) from exc
    workspace = Workspace(options.data_dir)
    server, url = make_server(workspace, options.port)
    if options.serve:
        print(url, flush=True)
        server.serve_forever()
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webview.create_window("SAT Study Kit", url, width=1380, height=920,
                          min_size=(1080, 700), background_color="#f3efe6")
    try:
        webview.start()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
