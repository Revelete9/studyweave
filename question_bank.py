"""Text-only question formats and local bank storage; no model or network access."""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

FIELDS = {"id", "module", "passage", "question", "options", "answer", "explanation"}
TABLE_FIELDS = {"id", "module", "passage", "question", "a", "b", "c", "d", "answer", "explanation"}
ALIASES = {"prompt": "question", "stem": "question", "text": "passage", "correct": "answer", "rationale": "explanation"}
FORMATS_HELP = """JSON: {"title":"My bank","questions":[{"question":"...","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"A"}]}
An array of question objects also works. Optional fields: id, module (1 or 2), passage, explanation. Answer may be blank/null when unknown.

CSV / TSV: header required: question,A,B,C,D
Optional columns: id,module,passage,answer,explanation. Quote fields containing separators or line breaks. Double any quotation marks inside a quoted field.

Tagged text: Question: ...\nA: ...\nB: ...\nC: ...\nD: ...\nAnswer: A
Optional labels: ID, Module, Passage, Explanation. Separate questions with a line containing ---. Unlabelled following lines continue the previous field. Indent a line to keep label-like text inside a field.

Automatic corrections: BOM, line endings, outer whitespace, header case / aliases, option-label case, full-width or lower-case answer letters, missing IDs. Exact duplicate questions are skipped. Conflicting IDs are reassigned. No spelling, missing options, answers or explanations are invented. An unknown answer stays unknown. Invalid imports are rejected as a whole. Limit: 2 MB / 200 questions.
"""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical(key):
    normalized = key.strip().lower()
    return ALIASES.get(normalized, normalized)


def parse_questions(text: str, format_name="auto", title="Imported bank"):
    if len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("Import limit: 2 MB.")
    corrections = []
    cleaned = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if cleaned != text:
        corrections.append("Normalized BOM, outer whitespace or line endings.")
    if not cleaned:
        raise ValueError("Paste questions or choose a file first.")
    if format_name == "auto":
        format_name = "json" if cleaned[0] in "[{" else "plain" if re.match(r"\d+[.)]\s+", cleaned) else "tagged" if re.match(r"(?i)(question|passage|id|module):", cleaned) else "tsv" if "\t" in cleaned.split("\n")[0] else "csv"
    if format_name == "plain":
        lines, count = [], 0
        for line in cleaned.splitlines():
            start = re.match(r"^\d+[.)]\s+(.+)$", line)
            if start:
                if count:
                    lines.append("---")
                lines.append("Question: " + start[1])
                count += 1
            else:
                # Only explicit labels are normalized; prose/answer keys are not guessed.
                line = re.sub(r"^([A-Da-d])[.)：]\s*", lambda m: m[1].upper() + ": ", line)
                line = re.sub(r"^(Answer|Explanation|Passage|Module)\s*：", r"\1:", line, flags=re.I)
                lines.append(line)
        if not count:
            raise ValueError("Plain text: start each question with 1. or 1), followed by A.–D. options.")
        cleaned = "\n".join(lines)
        format_name = "tagged"
        corrections.append("Converted numbered questions and option labels to tagged text.")
    if format_name == "json":
        def invalid_constant(value):
            raise ValueError(f"Invalid JSON constant: {value}")
        value = json.loads(cleaned, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        if isinstance(value, dict):
            # Read the former local data without mutating it. New exports use schema 1.
            if value.get("schema_version") == 3 and isinstance(value.get("modules"), list):
                entries = []
                for module in value["modules"]:
                    for item in module.get("questions", []):
                        unexpected = set(item) - FIELDS - {"answer_source", "source_ref", "needs_review", "available"}
                        if unexpected:
                            raise ValueError(f"Unsupported fields: {', '.join(unexpected)}")
                        entries.append({key: val for key, val in item.items() if key in FIELDS})
                corrections.append("Read legacy bank fields; the original file was not changed.")
            else:
                if set(value) - {"schema_version", "title", "questions"}:
                    raise ValueError("Bank JSON accepts only schema_version, title and questions.")
                if "schema_version" in value and (type(value["schema_version"]) is not int or value["schema_version"] != 1):
                    raise ValueError("Unsupported bank schema version.")
                entries = value.get("questions")
            title = value.get("title", title)
        else:
            entries = value
    elif format_name in ("csv", "tsv"):
        try:
            rows = list(csv.reader(io.StringIO(cleaned), delimiter="\t" if format_name == "tsv" else ",", strict=True))
        except csv.Error as exc:
            raise ValueError(f"Invalid question table: {exc}") from exc
        rows = [row for row in rows if any(v.strip() for v in row)]
        if not rows:
            raise ValueError("No questions found.")
        header = [_canonical(key) for key in rows[0]]
        if len(set(header)) != len(header) or set(header) - TABLE_FIELDS:
            raise ValueError("Unknown or duplicate table columns.")
        if not {"question", "a", "b", "c", "d"} <= set(header):
            raise ValueError("Table needs question,A,B,C,D headers.")
        if header != rows[0]:
            corrections.append("Normalized column names / aliases.")
        entries = []
        for number, row in enumerate(rows[1:], 2):
            if len(row) != len(header):
                raise ValueError(f"Row {number}: expected {len(header)} columns, got {len(row)}.")
            entries.append(dict(zip(header, row)))
    elif format_name == "tagged":
        entries = []
        for number, block in enumerate(re.split(r"(?m)^\s*---\s*$", cleaned), 1):
            if not block.strip():
                continue
            item, current = {}, None
            for line in block.strip().splitlines():
                match = re.match(r"^([A-Za-z]+)\s*:\s?(.*)$", line)
                key = _canonical(match[1]) if match else None
                if match and key in TABLE_FIELDS:
                    if key in item:
                        raise ValueError(f"Question block {number}: duplicate label {key}.")
                    item[key], current = match[2], key
                elif current is not None:
                    item[current] += "\n" + line
                elif line.strip():
                    raise ValueError(f"Question block {number}: start with a field label.")
            entries.append(item)
    else:
        raise ValueError("Choose auto, json, csv, tsv, tagged or plain.")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 200:
        raise ValueError("Import 1–200 questions at a time.")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Bank title must be nonempty text.")
    questions, used_ids, seen = [], set(), set()
    for number, raw in enumerate(entries, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Question {number}: expected an object.")
        item = {}
        for key, value in raw.items():
            canonical = _canonical(key)
            if canonical in item or canonical not in FIELDS | TABLE_FIELDS:
                raise ValueError(f"Question {number}: unknown or duplicate field {key}.")
            item[canonical] = value
            if canonical != key:
                corrections.append(f"Question {number}: normalized field {key}.")
        if "options" in item and any(key in item for key in "abcd"):
            raise ValueError("Use options or A/B/C/D columns, not both.")
        opts = item.get("options", {k.upper(): item.get(k, "") for k in "abcd"})
        if not isinstance(opts, dict):
            raise ValueError(f"Question {number}: options must be an object.")
        options = {}
        for key, value in opts.items():
            fixed = key.strip().upper()
            if fixed not in "ABCD" or len(fixed) != 1 or fixed in options:
                raise ValueError(f"Question {number}: use exactly A, B, C, D.")
            if fixed != key:
                corrections.append(f"Question {number}: normalized option label {key}.")
            options[fixed] = value
        if set(options) != set("ABCD"):
            raise ValueError(f"Question {number}: all four options are required.")
        def clean(value, field, required=False):
            if not isinstance(value, str) or len(value) > 30_000:
                raise ValueError(f"Question {number}: {field} must be text (max 30,000 characters).")
            if value != value.strip():
                corrections.append(f"Question {number}: trimmed {field}.")
            value = value.strip()
            if required and not value:
                raise ValueError(f"Question {number}: {field} cannot be empty.")
            return value
        q = {key: clean(item.get(key, ""), key, key == "question") for key in ("question", "passage", "explanation")}
        q["options"] = {key: clean(value, key, True) for key, value in options.items()}
        module = item.get("module", 1)
        if isinstance(module, str) and module.strip() in ("1", "2"):
            module = int(module.strip())
        if type(module) is not int or module not in (1, 2):
            raise ValueError(f"Question {number}: module must be 1 or 2.")
        q["module"] = module
        answer = item.get("answer")
        if answer is not None:
            original = answer
            if not isinstance(answer, str):
                raise ValueError(f"Question {number}: answer must be A/B/C/D or blank.")
            answer = answer.strip().translate(str.maketrans("ＡＢＣＤａｂｃｄ", "ABCDabcd")).upper() or None
            if answer is not None and answer not in tuple("ABCD"):
                raise ValueError(f"Question {number}: invalid answer; use A/B/C/D or blank.")
            if answer != original:
                corrections.append(f"Question {number}: normalized answer letter / blank.")
        q["answer"] = answer
        fingerprint = json.dumps(q, sort_keys=True, ensure_ascii=False)
        if fingerprint in seen:
            corrections.append(f"Skipped exact duplicate question {number}.")
            continue
        seen.add(fingerprint)
        identifier = item.get("id", "")
        if not isinstance(identifier, str):
            raise ValueError(f"Question {number}: ID must be text.")
        identifier = identifier.strip()
        if not identifier or identifier in used_ids:
            identifier = f"q-{number}"
            while identifier in used_ids:
                identifier += "-new"
            corrections.append(f"Question {number}: assigned ID {identifier}.")
        used_ids.add(identifier)
        q["id"] = identifier
        questions.append(q)
    return {"schema_version": 1, "title": title.strip(), "questions": questions}, corrections


def append_questions(bank, incoming):
    combined = {"schema_version": 1, "title": bank["title"], "questions": [*bank["questions"], *incoming["questions"]]}
    return parse_questions(json.dumps(combined), "json")


def save_bank(bank, directory: Path, path: Path | None = None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if bank["questions"]:
        bank, _ = parse_questions(json.dumps(bank), "json")
    elif not isinstance(bank.get("title"), str) or not bank["title"].strip():
        raise ValueError("Bank title is required.")
    target = Path(path).resolve() if path else directory / f"{uuid.uuid4().hex}.json"
    if target.parent != directory or target.suffix != ".json":
        raise ValueError("Banks can only be saved inside the local banks directory.")
    if target.exists():
        backup = directory.parent / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup.mkdir(parents=True)
        shutil.copy2(target, backup / target.name)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def read_bank(path):
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError("Bank exceeds 2 MB.")
    text = path.read_text(encoding="utf-8-sig")
    raw = json.loads(text, object_pairs_hook=unique_object)
    if (isinstance(raw, dict) and raw.get("schema_version") == 1 and raw.get("questions") == []
            and isinstance(raw.get("title"), str) and raw["title"].strip()
            and not (set(raw) - {"schema_version", "title", "questions"})):
        return raw
    return parse_questions(text, "json")[0]


def discover_banks(directory):
    directory = Path(directory)
    candidates = sorted((directory / "banks").glob("*.json"))
    if (directory / "questions.json").exists():
        candidates.append(directory / "questions.json")
    candidates.append(Path(__file__).resolve().parent / "examples/questions.json")
    choices, errors, labels = [], [], set()
    for path in candidates:
        try:
            bank = read_bank(path)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        base = f"{bank['title']} ({len(bank['questions'])} questions)"
        name, suffix = base, 2
        while name in labels:
            name, suffix = f"{base} ({suffix})", suffix + 1
        labels.add(name)
        choices.append((name, path))
    return choices, errors
