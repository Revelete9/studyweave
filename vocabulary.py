"""Vocabulary imports, atomic local storage and resumable recall sessions."""
from __future__ import annotations

import copy
import csv
import io
import json
import shutil
import uuid
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from question_bank import unique_object

FIELDS = {"term", "meaning", "phonetic", "expansion", "sequence"}
ALIASES = {"word": "term", "definition": "meaning", "pronunciation": "phonetic",
           "notes": "expansion", "number": "sequence"}
FORMATS_HELP = """No numbering required. Order is assigned automatically.
Simple: concise: brief and clear
All fields: concise | /kənˈsaɪs/ | brief and clear | a concise explanation
Fields: term | phonetic (pronunciation) | meaning | expansion (notes / examples).
Leave optional fields empty, e.g. concise | | brief and clear |
JSON: [{"term":"concise","phonetic":"/kənˈsaɪs/","meaning":"brief and clear","expansion":"a concise explanation"}]
CSV / TSV / pipe: optional header; without one use 2 columns (term, meaning),
4 (term, phonetic, meaning, expansion), or 5 (sequence first).
Pairs: word = meaning, one per line.
Plain text: word: meaning, optionally numbered (1. word: meaning).
Optional fields: phonetic, expansion, sequence. Header aliases: word,
definition, pronunciation, notes, number. Quote fields containing separators.
Automatic corrections: whitespace, BOM, line endings, field aliases and full-width
pipes. Identical duplicates are skipped. Conflicting definitions are rejected.
Existing words and their records are kept. Spelling and definitions are not guessed.
Limit: 2 MB / 5,000 words. Preview before saving."""


def parse_words(text, kind="auto"):
    if len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("Import limit: 2 MB.")
    notes = []
    clean = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if clean != text:
        notes.append("Normalized whitespace, BOM or line endings.")
    if not clean:
        raise ValueError("Enter words or choose a file.")
    if kind == "auto":
        first = clean.splitlines()[0]
        kind = "json" if clean[0] in "[{" else "tsv" if "\t" in first else "pipe" if any(c in first for c in "|｜") else "pairs" if "=" in first else "plain" if re.search(r"[:：]", first) else "csv"
    canonical = lambda s: ALIASES.get(s.strip().lower(), s.strip().lower())
    if kind == "json":
        data = json.loads(clean, object_pairs_hook=unique_object)
        entries = data.get("words") if isinstance(data, dict) else data
    elif kind in ("pairs", "plain"):
        entries = []
        for i, line in enumerate(clean.splitlines(), 1):
            if not line.strip():
                continue
            if kind == "plain":
                line = re.sub(r"^\s*\d+[.)]\s+", "", line)
                line = line.replace("：", ":", 1)
            term, separator, meaning = line.partition(":" if kind == "plain" else "=")
            if not separator:
                raise ValueError(f"Line {i}: use word {' : ' if kind == 'plain' else ' = '} meaning.")
            entries.append({"term": term, "meaning": meaning})
    elif kind in ("csv", "tsv", "pipe"):
        if kind == "pipe" and "｜" in clean:
            clean = clean.replace("｜", "|")
            notes.append("Normalized full-width pipe separators.")
        try:
            rows = [r for r in csv.reader(io.StringIO(clean), delimiter={"csv": ",", "tsv": "\t", "pipe": "|"}[kind], strict=True, skipinitialspace=True) if any(v.strip() for v in r)]
        except csv.Error as exc:
            raise ValueError(f"Invalid table: {exc}") from exc
        if not rows:
            raise ValueError("No words found.")
        header = [canonical(v) for v in rows[0]]
        named = {"term", "meaning"} <= set(header)
        if named:
            if set(header) - FIELDS or len(set(header)) != len(header):
                raise ValueError("Unknown or duplicate columns.")
            if header != rows[0]:
                notes.append("Normalized column names / aliases.")
        else:
            header = {2: ["term", "meaning"], 4: ["term", "phonetic", "meaning", "expansion"], 5: ["sequence", "term", "phonetic", "meaning", "expansion"]}.get(len(rows[0]))
            if not header:
                raise ValueError("Use a header or 2, 4 or 5 columns.")
        entries = []
        for i, row in enumerate(rows[1:] if named else rows, 2 if named else 1):
            if len(row) != len(header):
                raise ValueError(f"Row {i}: expected {len(header)} columns, got {len(row)}.")
            entries.append(dict(zip(header, row)))
    else:
        raise ValueError("Choose auto, json, csv, tsv, pipe, pairs or plain.")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 5000:
        raise ValueError("Import 1–5,000 words at a time.")
    result, seen, sequences = [], {}, set()
    for i, raw in enumerate(entries, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Entry {i}: expected a word object.")
        row = {}
        for key, value in raw.items():
            k = canonical(key)
            if k not in FIELDS or k in row:
                raise ValueError(f"Entry {i}: unknown or duplicate field {key}.")
            if k != key:
                notes.append(f"Entry {i}: normalized {key}.")
            row[k] = value
        word = {}
        for key in ("term", "meaning", "phonetic", "expansion"):
            value = row.get(key, "")
            if not isinstance(value, str) or len(value) > 30000:
                raise ValueError(f"Entry {i}: {key} must be text (max 30,000 characters).")
            if value != value.strip():
                notes.append(f"Entry {i}: trimmed {key}.")
            word[key] = value.strip()
        if not word["term"] or not word["meaning"]:
            raise ValueError(f"Entry {i}: term and meaning are required.")
        key = word["term"].casefold()
        if key in seen:
            if word != seen[key]:
                raise ValueError(f"Conflicting entries for {word['term']}.")
            notes.append(f"Skipped duplicate: {word['term']}.")
            continue
        seen[key] = dict(word)
        n = row.get("sequence")
        if isinstance(n, str) and n.strip().isdigit():
            n = int(n.strip())
        if type(n) is int and n > 0 and n not in sequences:
            word["sequence"] = n
            sequences.add(n)
        elif n not in (None, ""):
            notes.append(f"Entry {i}: sequence will be assigned automatically.")
        result.append(word)
    next_sequence = 1
    for word in result:
        if "sequence" not in word:
            while next_sequence in sequences:
                next_sequence += 1
            word["sequence"] = next_sequence
            sequences.add(next_sequence)
    return result, notes


def new_word(raw):
    return {**raw, "id": uuid.uuid4().hex, "remembered": 0, "forgotten": 0,
            "streak": 0, "encounters": 0}


def parse_group_clipboard(text):
    """Validate portable group content, never IDs, progress or executable data."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("Clipboard limit: 2 MB.")
    pack = json.loads(text, object_pairs_hook=unique_object)
    if (not isinstance(pack, dict) or pack.get("format") != "sat-study-kit/groups"
            or type(pack.get("version")) is not int or pack["version"] != 1
            or set(pack) != {"format", "version", "groups"}):
        raise ValueError("Use a SAT Study Kit group clipboard (version 1).")
    groups = pack["groups"]
    if not isinstance(groups, list) or not 1 <= len(groups) <= 100:
        raise ValueError("Paste 1–100 groups at a time.")
    parsed, count = [], 0
    for group in groups:
        if (not isinstance(group, dict) or set(group) != {"name", "words"}
                or not isinstance(group["name"], str) or not group["name"].strip()
                or len(group["name"]) > 200 or not isinstance(group["words"], list)):
            raise ValueError("Each copied group needs a name and a list of words.")
        count += len(group["words"])
        if count > 5000:
            raise ValueError("Clipboard limit: 5,000 words in total.")
        words = parse_words(json.dumps(group["words"], ensure_ascii=False))[0] if group["words"] else []
        parsed.append({"name": group["name"].strip(), "words": words})
    return parsed


def make_state(catalog):
    groups = []
    for category in catalog["categories"]:
        # Old catalogs contain provenance metadata, not editable word fields.
        source = [{k: v for k, v in w.items() if k in FIELDS} for w in category["words"]]
        words = [new_word(w) for w in parse_words(json.dumps(source))[0]] if source else []
        groups.append({"id": uuid.uuid4().hex, "name": category["name"], "words": words})
    return {"version": 1, "groups": groups, "sessions": {}}


class VocabularyStore:
    def __init__(self, directory, example):
        self.directory = Path(directory)
        self.path = self.directory / "desktop-vocabulary.json"
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
            self.validate(self.state)
        else:
            source = self.directory / "vocabulary.json"
            if not source.exists():
                source = Path(example)
            self.state = make_state(json.loads(source.read_text(encoding="utf-8-sig")))
            self.validate(self.state)
        if self.state["version"] == 1:
            upgraded = copy.deepcopy(self.state)
            bid = uuid.uuid4().hex
            upgraded.update(version=2, books=[{"id": bid, "name": "My vocabulary"}], book_sessions={})
            for group in upgraded["groups"]:
                group["book_id"] = bid
            # Preserve the old file in a backup before the first v2 write.
            if self.path.exists():
                self.save(upgraded)
            else:
                self.state = upgraded

    @staticmethod
    def validate(state):
        if not isinstance(state, dict) or state.get("version") not in (1, 2) or not isinstance(state.get("groups"), list) or not isinstance(state.get("sessions"), dict):
            raise ValueError("Invalid desktop vocabulary file. Restore a backup; the file has not been overwritten.")
        if state["version"] == 2:
            if not isinstance(state.get("books"), list) or not isinstance(state.get("book_sessions"), dict):
                raise ValueError("Invalid word books.")
            books, names = set(), set()
            for book in state["books"]:
                if not isinstance(book, dict) or not isinstance(book.get("id"), str) or not book["id"] or book["id"] in books or not isinstance(book.get("name"), str) or not book["name"].strip() or book["name"].casefold() in names:
                    raise ValueError("Invalid or duplicate word book.")
                books.add(book["id"])
                names.add(book["name"].casefold())
            for group in state["groups"]:
                if not isinstance(group, dict) or group.get("book_id") not in books:
                    raise ValueError("A word group has no valid book.")
            for bid, plan in state["book_sessions"].items():
                members = {g["id"] for g in state["groups"] if g["book_id"] == bid}
                if bid not in books or not isinstance(plan, dict) or plan.get("mode") not in ("Sequential", "Random") or not isinstance(plan.get("order"), list):
                    raise ValueError("Invalid book learning plan.")
                if any(gid not in members for gid in plan["order"]) or len(set(plan["order"])) != len(plan["order"]) or (plan.get("current") is not None and plan["current"] not in members):
                    raise ValueError("Invalid book group order.")
        groups, ids = set(), set()
        for g in state["groups"]:
            if not isinstance(g, dict) or not g.get("id") or g["id"] in groups or not isinstance(g.get("name"), str) or not g["name"].strip() or not isinstance(g.get("words"), list):
                raise ValueError("Invalid vocabulary group.")
            groups.add(g["id"])
            terms = set()
            for w in g["words"]:
                if not isinstance(w, dict) or not w.get("id") or w["id"] in ids or any(not isinstance(w.get(k), str) for k in ("term", "meaning", "phonetic", "expansion")) or not w["term"].strip() or not w["meaning"].strip():
                    raise ValueError("Invalid word record.")
                if w["term"].casefold() in terms or any(type(w.get(k)) is not int or w[k] < 0 for k in ("remembered", "forgotten", "streak", "encounters")):
                    raise ValueError("Invalid or duplicate word progress.")
                ids.add(w["id"])
                terms.add(w["term"].casefold())
        for gid, session in state["sessions"].items():
            group = next((g for g in state["groups"] if g["id"] == gid), None)
            if group is None or not isinstance(session, dict) or not isinstance(session.get("queue"), list) or type(session.get("cursor")) is not int:
                raise ValueError("Invalid review session.")
            if not 0 <= session["cursor"] <= len(session["queue"]) or any(wid not in {w["id"] for w in group["words"]} for wid in session["queue"]):
                raise ValueError("Invalid review queue.")

    def save(self, candidate, backup=True):
        self.validate(candidate)
        self.directory.mkdir(parents=True, exist_ok=True)
        if backup and self.path.exists():
            folder = self.directory / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            folder.mkdir(parents=True)
            shutil.copy2(self.path, folder / self.path.name)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        self.state = candidate

    def group(self, gid, state=None):
        return next(g for g in (state or self.state)["groups"] if g["id"] == gid)

    def name_group(self, name, gid=None, book_id=None):
        book_id = book_id or (self.group(gid)["book_id"] if gid else self.state["books"][0]["id"])
        name = name.strip()
        if not name:
            raise ValueError("Enter a group name.")
        if any(g["name"].casefold() == name.casefold() and g["id"] != gid and g["book_id"] == book_id for g in self.state["groups"]):
            raise ValueError("That group name already exists.")
        state = copy.deepcopy(self.state)
        if gid:
            self.group(gid, state)["name"] = name
        else:
            gid = uuid.uuid4().hex
            state["groups"].append({"id": gid, "book_id": book_id, "name": name, "words": []})
        self.save(state)
        return gid

    def put_words(self, gid, incoming, edit_id=None):
        # Validate again at the storage boundary, not just in the dialog.
        incoming, _ = parse_words(json.dumps(incoming))
        if edit_id and len(incoming) != 1:
            raise ValueError("Edit exactly one word.")
        state = copy.deepcopy(self.state)
        group = self.group(gid, state)
        known = {w["term"].casefold(): w for w in group["words"]}
        added = skipped = 0
        if edit_id:
            old = next(w for w in group["words"] if w["id"] == edit_id)
            duplicate = known.get(incoming[0]["term"].casefold())
            if duplicate and duplicate["id"] != edit_id:
                raise ValueError("Another word already uses this term.")
            old.update(incoming[0])
        else:
            sequences = {w.get("sequence") for w in group["words"]}
            next_sequence = max((n for n in sequences if type(n) is int), default=0) + 1
            for raw in incoming:
                key = raw["term"].casefold()
                if key in known:
                    skipped += 1
                    continue
                w = new_word(raw)
                if w["sequence"] in sequences:
                    while next_sequence in sequences:
                        next_sequence += 1
                    w["sequence"] = next_sequence
                    next_sequence += 1
                sequences.add(w["sequence"])
                group["words"].append(w)
                known[key] = w
                added += 1
                if gid in state["sessions"]:
                    state["sessions"][gid]["queue"].append(w["id"])
        self.save(state)
        return added, skipped

    def begin(self, gid, restart=False, mode="Sequential"):
        group = self.group(gid)
        if not group["words"]:
            raise ValueError("Add words to this group first.")
        if restart or gid not in self.state["sessions"]:
            state = copy.deepcopy(self.state)
            queue = [w["id"] for w in group["words"]]
            if mode == "Random":
                random.shuffle(queue)
            state["sessions"][gid] = {"queue": queue, "cursor": 0}
            self.save(state)
        return self.state["sessions"][gid]

    def name_book(self, name, bid=None):
        name = name.strip()
        if not name or any(b["name"].casefold() == name.casefold() and b["id"] != bid for b in self.state["books"]):
            raise ValueError("Enter a unique, nonempty book name.")
        state = copy.deepcopy(self.state)
        if bid:
            next(b for b in state["books"] if b["id"] == bid)["name"] = name
        else:
            bid = uuid.uuid4().hex
            state["books"].append({"id": bid, "name": name})
        self.save(state)
        return bid

    def group_status(self, gid):
        session = self.state["sessions"].get(gid)
        if not self.group(gid)["words"]:
            return "Empty"
        if not session:
            return "Not started"
        return "Complete" if session["cursor"] >= len(session["queue"]) else "In progress"

    def begin_book(self, bid, mode="Sequential", restart=False):
        if mode not in ("Sequential", "Random"):
            raise ValueError("Choose Sequential or Random.")
        members = [g["id"] for g in self.state["groups"] if g["book_id"] == bid and g["words"]]
        if not members:
            raise ValueError("Add a nonempty group to this book first.")
        state = copy.deepcopy(self.state)
        prior = state["book_sessions"].get(bid, {})
        if restart:
            for gid in members:
                state["sessions"].pop(gid, None)
        if restart or prior.get("mode") != mode:
            order = list(members)
            if mode == "Random":
                random.shuffle(order)
        else:
            order = [gid for gid in prior["order"] if gid in members]
            extra = [gid for gid in members if gid not in order]
            if mode == "Random":
                random.shuffle(extra)
            order.extend(extra)
        def unfinished(gid):
            s = state["sessions"].get(gid)
            return s is None or s["cursor"] < len(s["queue"])
        current = prior.get("current") if not restart else None
        if current not in members or not unfinished(current):
            current = next((gid for gid in order if unfinished(gid)), None)
        if current and current not in state["sessions"]:
            queue = [w["id"] for w in self.group(current, state)["words"]]
            if mode == "Random":
                random.shuffle(queue)
            state["sessions"][current] = {"queue": queue, "cursor": 0}
        state["book_sessions"][bid] = {"mode": mode, "order": order, "current": current}
        self.save(state, backup=restart)
        return current

    def import_group(self, bid, name, words):
        """Save a parsed group in one transaction; never leave an empty partial group."""
        parsed, _ = parse_words(json.dumps(words))
        name = name.strip()
        if not name or any(g["book_id"] == bid and g["name"].casefold() == name.casefold() for g in self.state["groups"]):
            raise ValueError("Enter a unique group name in this book.")
        state = copy.deepcopy(self.state)
        gid = uuid.uuid4().hex
        state["groups"].append({"id": gid, "book_id": bid, "name": name, "words": [new_word(w) for w in parsed]})
        self.save(state)
        return gid

    def preview_group_paste(self, bid, text):
        if bid not in {b["id"] for b in self.state["books"]}:
            raise ValueError("Choose a destination book first.")
        groups = parse_group_clipboard(text)
        names = {g["name"].casefold() for g in self.state["groups"] if g["book_id"] == bid}
        for group in groups:
            original, name, number = group["name"], group["name"], 1
            while name.casefold() in names:
                name = f"{original} (copy{f' {number}' if number > 1 else ''})"
                number += 1
            group["name"] = name
            names.add(name.casefold())
        return groups

    def paste_groups(self, bid, text):
        """Copy a clipboard snapshot atomically; keep existing groups and progress."""
        groups = self.preview_group_paste(bid, text)
        state, ids = copy.deepcopy(self.state), []
        for group in groups:
            gid = uuid.uuid4().hex
            ids.append(gid)
            state["groups"].append({"id": gid, "book_id": bid, "name": group["name"],
                                    "words": [new_word(w) for w in group["words"]]})
        if bid in state["book_sessions"]:
            state["book_sessions"][bid]["order"].extend(ids)
        self.save(state)
        return ids

    def rate(self, gid, result):
        if result not in ("remembered", "forgotten", "skipped"):
            raise ValueError("Invalid review response.")
        state = copy.deepcopy(self.state)
        s = state["sessions"][gid]
        pos = s["cursor"]
        if pos >= len(s["queue"]):
            return
        word = next(w for w in self.group(gid, state)["words"] if w["id"] == s["queue"][pos])
        word["encounters"] += 1
        word["lastSeen"] = datetime.now(timezone.utc).isoformat()
        if result == "remembered":
            word["remembered"] += 1
            word["streak"] += 1
        elif result == "forgotten":
            word["forgotten"] += 1
            word["streak"] = 0
        if word["forgotten"] > 0 and word["streak"] < 3 and word["id"] not in s["queue"][pos+1:]:
            gap = 4 if word["streak"] == 0 else 9 if word["streak"] == 1 else 21
            s["queue"].insert(min(pos + gap, len(s["queue"])), word["id"])
        s["cursor"] += 1
        self.save(state, backup=False)

    def transfer(self, kind, source, target, item_ids, duplicate=False):
        """Atomically move/copy selected groups or words; reject conflicts as a batch.

        Moves preserve IDs and counters. Copies are independent, unstudied records.
        Word moves remove every source queue occurrence and queue one destination
        review. Whole-group moves preserve the complete group's review session.
        """
        ids = list(dict.fromkeys(item_ids))
        if not ids:
            raise ValueError("Select at least one item.")
        if source == target:
            raise ValueError("Choose a different destination.")
        state = copy.deepcopy(self.state)
        if kind == "group":
            books = {b["id"] for b in state["books"]}
            if source not in books or target not in books:
                raise ValueError("Choose a valid source and destination book.")
            available = {g["id"]: g for g in state["groups"] if g["book_id"] == source}
            if any(gid not in available for gid in ids):
                raise ValueError("The source selection changed. Select the groups again.")
            names = {g["name"].casefold() for g in state["groups"] if g["book_id"] == target}
            for gid in ids:
                group = available[gid]
                if group["name"].casefold() in names:
                    raise ValueError(f"Destination already has a group named {group['name']}. Rename it first; nothing was changed.")
                names.add(group["name"].casefold())
                if duplicate:
                    clone = {"id": uuid.uuid4().hex, "book_id": target, "name": group["name"],
                             "words": [new_word({k: v for k, v in w.items() if k in FIELDS}) for w in group["words"]]}
                    state["groups"].append(clone)
                else:
                    group["book_id"] = target
        elif kind == "word":
            groups = {g["id"]: g for g in state["groups"]}
            if source not in groups or target not in groups:
                raise ValueError("Choose a valid source and destination group.")
            src, dst = groups[source], groups[target]
            available = {w["id"]: w for w in src["words"]}
            if any(wid not in available for wid in ids):
                raise ValueError("The source selection changed. Select the words again.")
            terms = {w["term"].casefold() for w in dst["words"]}
            for wid in ids:
                if available[wid]["term"].casefold() in terms:
                    raise ValueError(f"Destination already contains {available[wid]['term']}. Nothing was changed.")
            next_sequence = max((w.get("sequence", 0) for w in dst["words"]), default=0) + 1
            for wid in ids:
                word = available[wid]
                if duplicate:
                    word = new_word({k: v for k, v in word.items() if k in FIELDS})
                word["sequence"] = next_sequence
                next_sequence += 1
                dst["words"].append(word)
                if target in state["sessions"]:
                    state["sessions"][target]["queue"].append(word["id"])
            if not duplicate:
                src["words"] = [w for w in src["words"] if w["id"] not in ids]
                session = state["sessions"].get(source)
                if session:
                    previous = session["queue"]
                    session["cursor"] = sum(wid not in ids for wid in previous[:session["cursor"]])
                    session["queue"] = [wid for wid in previous if wid not in ids]
        else:
            raise ValueError("Only groups and words can be transferred.")
        # Keep both books' saved plans valid, without reshuffling their existing order.
        for bid, plan in state["book_sessions"].items():
            members = [g["id"] for g in state["groups"] if g["book_id"] == bid]
            plan["order"] = [gid for gid in plan["order"] if gid in members]
            plan["order"].extend(gid for gid in members if gid not in plan["order"])
            if plan["current"] not in members:
                plan["current"] = None
        self.save(state)
        return len(ids)
