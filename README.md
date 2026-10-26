# SAT Study Kit

A free, open-source local vocabulary trainer and Reading and Writing practice tool. Import
your own material in documented formats, inspect the preview, and study. No AI
account, prompt, API key, server account or paid service is required. The software
does not generate questions, guess answers or correct spelling automatically.
One original word and one original question are bundled. This is not affiliated
with the College Board and does not implement official adaptive scoring.

Created by ColoredCloud, derived from personal SAT tools with AI-assisted
refactoring. Original private tools and study data are kept separately.
Released under the [MIT License](LICENSE).

## Start

Unified desktop app (Python 3.11+, Tkinter and pywebview). It reuses the original
React website's typography, cards and colors inside a desktop window. Python
still owns the local files, import validation, review queues and exam launcher.
Nothing is uploaded. On Windows, the window uses the installed Edge WebView2 runtime.

On Windows, double-click **Launch SAT Study Kit.cmd**. It uses a project-local
`.venv`, creates it with `python` if missing, and installs missing dependencies
from `requirements.txt` into that same environment. First setup requires Internet
access and Python 3.11+ with Tkinter. Later launches work offline when dependencies
are already installed. It does not rely on the Codex runtime or change your global
Python packages. `Launch SAT Study Kit.cmd --check` checks setup without opening
a window. If a Python dependency is missing, run this launcher again rather than
installing the unrelated package named `webview`; the package is **pywebview**.

If the interface has not been built yet (Node.js 22.13+ is needed to build it,
not to run it):

```sh
cd web
npm ci
npm run build
cd ..
```

For a manual Windows launch after setup:

```sh
.venv\Scripts\python.exe desktop.py
```

On other platforms, create and activate a Python virtual environment, install
`requirements.txt`, then run `python desktop.py` in that same environment.

- **Word library**: browse **Word books → Groups → Words**. Create books such as SAT,
  CET-4 or CET-6, and groups for a day's study or a category. These are user-created
  books, not bundled official word lists. Open a group to edit, search, paste or export.
  Study one group or choose **Study whole book** with Sequential / Random order.
- **Question Banks**: select or create a bank; rename it; add, edit, search,
  import and export questions.
- **Organize books & groups**: build study plans with two independent panes. Create
  books/groups, paste words, or drag existing material into another container.
  **Back to word library** returns to a single pane. No Send step.
- **Practice**: choose a question group and module durations, then **Start exam**.
  The original realistic simulator opens in a separate window. An already-open
  test is brought forward instead of replacing its answers.

Group creation, renaming, word/question editing and imports stay inside the main
workspace. Save results and validation errors appear inline. Import instructions
can be expanded when needed; previews must match the current input before saving.
**Cancel** and **×** close a paste editor immediately without changing the library;
the in-app clipboard remains available for another paste. Other changed editors
show an inline choice to keep editing or discard changes.
Only file selection/export, startup failures and closing an active exam need native
dialogs. The standalone legacy simulator keeps its original bank-management UI.

Desktop words and review progress are saved in `data/desktop-vocabulary.json`.
The first launch reads the local vocabulary catalog (or bundled example), but
does not migrate or overwrite browser progress. Editing/importing keeps existing
word IDs and recall records. Backups are made before library edits and new rounds;
each rating is saved atomically. **Export full backup** includes books, words and
progress; a group's **Export** includes only word content. Exports are written
into `data/exports`, and the exact path appears in the status message.
Review resumes at the next ungraded card; a completed round offers **Start new round**.

Existing desktop v1 groups are migrated into **My vocabulary** with a backup of
the old file. IDs, counters and unfinished queues are preserved. Whole-book study
resumes its current unfinished group, skips complete/empty groups and continues to
the next unfinished group. Random mode shuffles groups and fresh word queues once,
then saves their order. Changing mode does not reshuffle a partially studied group.
New words added to a completed group make that group unfinished again. New groups
join the book's plan. A new book round resets queues, not lifetime recall counters.

On recall cards, **Space** reveals/hides meaning; **1** remembers, **2** marks forgotten,
**3** skips, **Esc** returns with progress saved, and **? / F1** toggles inline help.
Reveal the meaning before rating 1 or 2. These shortcuts are inactive in library
editors and the separate mock-exam window. The **?** button shows the same help.

## Paste a complete group

### Organize existing material

In **Word library → Organize books & groups**, choose a book in each pane. **All groups**
lists that book's groups; click a group's title or choose it in the second dropdown
to see its words. Search and learning-status filters remain available. Use checkboxes
or Ctrl/Shift-click for multiple items. Words can be sorted by order, errors, error
rate and encounters. Click the same sort again to reverse it.

- Drag groups into the other book's pane to move whole groups (not merge them).
- Drag words into an open group pane, or onto a group row in **All groups**.
- The Move/Copy selector chooses the operation; holding Ctrl during a drag forces
  Copy. The destination is highlighted while dragging; release to save. Escape
  cancels a drag. The lists scroll when dragging near their upper or lower edges.
- Moves keep word IDs and learning counters. Whole-group moves also retain the
  group's queue. Word moves remove their old queue entries and add one review in
  the destination queue if it exists. Other words' completed positions are retained.
- Copies get new IDs and fresh learning progress; source material is unchanged.
- Conflicting group names or word terms reject the entire transfer, without
  overwriting or silently skipping anything. Rename conflicts before retrying.
- Transfers save atomically with backups. **Undo transfer** restores the last
  transfer in this workspace; later library edits invalidate that undo.
- **+ Book / + Group** opens an inline creator. **Paste words** is the only entry
  for adding words, whether one or many. Existing words still have **Edit**, with
  word, meaning, pronunciation and expansion/notes all visible. There is no manual
  word-number field; ordering is assigned internally for sequential study.
  The destination is captured when an editor opens and shown above its fields.
  New containers immediately accept drops.

### Copy and paste existing groups

Select one or more group checkboxes, choose **Copy groups in-app**, open the
destination book, then **Paste group**. Review the preview and confirm. Inside a
group, checked words can be copied individually; with no words checked, Copy
copies the entire group. Paste whole groups at book level, and words inside a group.
Copying works in both single-pane and two-pane layouts. **Ctrl+C / Ctrl+V** use
the active pane and the selected clipboard mode; text fields keep normal text
editing shortcuts.

- **In-app** is the default. It keeps a content snapshot in the current app window
  while navigating between books; it never reads or replaces your system clipboard.
  It is cleared when the window is closed or reloaded.
- **System / share** uses portable JSON text. Choose it in the toolbar, or use the
  separate **Copy to system** button without first changing modes. System copy
  replaces the system clipboard; the in-app copy is kept separately. Switching the
  mode alone does not read or write either clipboard.
- **Read system clipboard** and **Use in-app copy** are available in the paste
  editor. Existing input is not overwritten; clear it before switching its source.
  If clipboard access is unavailable, paste the shared text into the input manually.
  Cross-device transfer requires your own clipboard sync or text/file transfer;
  the app does not connect devices or upload anything.
- Group copies keep names, terms, pronunciation, meanings and notes, but not IDs,
  source paths or study history. They get fresh progress. Existing groups stay intact;
  duplicate names receive a `(copy)` suffix. The preview shows the final names.
- Whole-group pastes are atomic and can be undone with **Undo** in the organizer
  until a later library edit. Limits are 2 MB, 100 groups and 5,000 words per paste.

The older Tk interface is retained with `python desktop.py --classic`; it uses
the same desktop data. Do not edit the same library in both interfaces at once.
The new host detects external changes and rejects stale edits instead of replacing
them. Browser-only vocabulary records are still separate and are not overwritten.

### Paste text

Inside a book choose **Paste group**, enter its name and paste all words. Inside
an existing group choose **Paste words** to append. Click **Preview**, inspect the
parsed contents, then save. The **Example** button fills only an empty input.

```text
concise: brief and clear
obsolete: no longer used
```

For all word properties, use four fields; empty optional fields are allowed:

```text
concise | /kənˈsaɪs/ | brief and clear | a concise explanation
obsolete | | no longer used | obsolete equipment
```

Numbers are unnecessary. Older numbered imports remain supported.

In **Question Banks → Paste questions**, append to the selected group or supply a
title and choose **Save as new bank**. Plain text supports numbered question starts,
A.–D. options, optional `Passage:`, `Module:`, `Answer:` and `Explanation:` labels.
Unknown answers stay unknown; no answer or missing option is invented. Indent
continuation lines that start with a number to distinguish them from a new question.

```text
1. Which word means brief and clear?
A. Concise
B. Obsolete
C. Ambiguous
D. Contradictory
Answer: A

2. Which word means no longer used?
A. Concise
B. Obsolete
C. Ambiguous
D. Contradictory
Answer: B
```

Plain text is a defined format, not arbitrary document/OCR interpretation. Existing
JSON, CSV, TSV, pipe, pairs and tagged formats remain available as applicable below.

Existing web vocabulary trainer (kept separately; Node.js 22.13 or later):

```sh
cd web
npm ci
npm run dev
```

Open http://127.0.0.1:47832. The bundled example works without an import script.
In development, an existing `data/vocabulary.json` is used instead of the
example. Production builds bundle only the example, never the private data
directory. Previous browser records remain in `sat-study-kit.web.v1:<pack_id>`.

Question browser, editor and timed practice (Python 3.11+ with Tkinter):

```sh
python simulator.py
```

No third-party Python packages are required. Choose a bank to practice, or open
**Browse / Edit / Import Question Banks**. Create an empty bank, write questions
with the editor, or import a file. Search and browse questions without starting
a timed test. Edit a selected question and export a bank as JSON. Edits to the
bundled example or old `data/questions.json` create a separate editable bank;
they do not overwrite those sources.

## Vocabulary formats

Use **Word library → Paste group / Paste words** on the desktop, or **Word library**
in the browser-only version, to paste material or upload a UTF-8 `.csv`, `.tsv`,
`.txt` or `.json` file. Select the format if auto-detection picks the wrong separator.
Click **Preview**, inspect the words and expandable format corrections, then save.
Imports append to the selected group, not replace it.

| Format | Specification |
| --- | --- |
| CSV | Comma-separated; optional header. |
| TSV | Tab-separated; optional header, including spreadsheet pastes. |
| Pipe-separated | `word | meaning`, or the longer forms below. |
| Pairs | `word = meaning`, one per line; only the first `=` separates the fields. |
| JSON | Array of word objects, or an object containing a `words` array. |

Without a header, table rows must have exactly one of these layouts:

- 2 columns: `term,meaning`
- 4 columns: `term,phonetic,meaning,expansion`
- 5 columns: `sequence,term,phonetic,meaning,expansion`

With a header, columns can appear in any order. `term` and `meaning` are required;
`phonetic`, `expansion` and `sequence` are optional. Aliases are `word`,
`definition`, `pronunciation`, `notes` and `number`, respectively. Quote an entire
field containing a separator or line break. Inside quoted fields, double `"`.

JSON word shape:

```json
{"term":"concise","meaning":"brief and clear","phonetic":"","expansion":""}
```

### Automatic format corrections

- Remove a leading BOM; normalize CRLF/CR line endings; trim outer field whitespace.
- Normalize header case and the documented aliases.
- In pipe mode, convert full-width `｜` separators to `|`.
- Assign missing, invalid or conflicting sequence numbers without changing existing IDs.
- Skip identical repeated words within an import. Conflicting definitions for the
  same new word are rejected so the author can combine senses explicitly.
- Skip words already present in the destination group, preserving their existing
  content and learning history. Use **Edit** for intentional changes.

Corrections appear in the preview or final import notice. No spell-check guesses,
automatic translations, missing definitions or unsupported image fields are added.
A malformed row rejects the import rather than silently dropping that row.
Limits: 2 MB and 5,000 input entries. Supplied study content is preserved; the
application interface, documentation and generated messages are English.

## Question formats

The manager supports UTF-8 JSON, CSV, TSV and tagged text. Imports require a
preview before **Append to Selected Bank** or **Save as New Bank**. The preview
shows normalized questions, answers and corrections. New banks are stored under
`data/banks/`; bank selection discovers every compatible JSON file there.

JSON accepts an array of questions or this envelope:

```json
{
  "schema_version": 1,
  "title": "My practice",
  "questions": [{
    "id": "q1", "module": 1,
    "passage": "", "question": "Which word means brief and clear?",
    "options": {"A":"Concise","B":"Obsolete","C":"Ambiguous","D":"Contradictory"},
    "answer": "A", "explanation": ""
  }]
}
```

Required: nonempty `question` and all four nonempty options. Optional: `id`,
`module` (default 1; allowed 1 or 2), `passage`, `answer`, `explanation`. A blank
or null answer remains unknown and is not graded. An explanation is never generated.

CSV/TSV require headers. Required columns: `question,A,B,C,D`. Optional columns:
`id,module,passage,answer,explanation`. Headers are case-insensitive. Aliases:
`prompt`/`stem` -> `question`, `text` -> `passage`, `correct` -> `answer`,
`rationale` -> `explanation`. Use standard CSV quoting for multiline text or
embedded separators. Do not change the original option order.

Tagged text:

```text
Module: 1
Passage: Optional passage.
Question: Which word means brief and clear?
A: Concise
B: Obsolete
C: Ambiguous
D: Contradictory
Answer: A
Explanation: Optional explanation.
```

Separate questions with a line containing `---`. Unlabelled lines continue the
previous field. Indent a continuation line if it begins with a field-like label.
The `ID`, `Module`, `Passage`, `Answer` and `Explanation` labels are optional.

Automatic corrections normalize BOM, line endings, whitespace, headers/aliases,
option-label case and lowercase/full-width answer letters. Missing or conflicting
IDs are assigned. Exact duplicate questions (same content, module, answer and
explanation, ignoring ID) are skipped. Conflicting answers are NOT silently merged.
Unknown fields, incomplete options, invalid answer letters and malformed rows are
rejected as a whole. Limits: 2 MB / 200 questions per bank. These are text-only
formats: no OCR, images, audio, remote paths or math rendering.

## Data and practice behavior

- Vocabulary has recall cards, self-rating, groups, editing, searching, statistics,
  export and saved review position. An exported progress backup currently has no
  in-app restore command; it is not a standard word-import file.
- Missed words return until three consecutive successful self-ratings at distinct
  queue positions. When enough cards remain, the gaps are 3, 8 and 20 intervening
  cards. This is a same-session heuristic, not a validated optimal schedule or a
  calendar-based scheduler. No algorithm change is included in this release.
- Timed practice supports one or two modules, custom durations, navigation,
  review marks, option elimination, font controls and a line reader. Module 1 must
  contain a question to start a test. The answer summary shows supplied answers;
  it does not predict a SAT score. Test answers are held in memory, not saved for
  resuming after closing the app.
- Existing editable bank files are copied to `data/backups/<timestamp>/` before
  a save. New bank filenames are generated IDs, never user-supplied paths.
- All imports are local. Materials, generated banks, backups, browser records,
  `.env` files, dependencies and build output must not be published.
- This repository contains only original demonstration material and synthetic test
  fixtures. Personal libraries, study histories, local backups and credentials are
  excluded. Commits use the maintainer's GitHub no-reply address.
- The old AI-specific prompt and command-line study-pack workflow have been removed.
  Legacy local banks are read for continuity; newly saved banks use the plain format.

## Research behind repetition

Repeated retrieval and spacing have support, but a fixed card gap is not a
universal optimum. [Cepeda et al. (2008)](https://laplab.ucsd.edu/articles/Cepeda%20et%20al%202008_psychsci.pdf)
found that useful spacing depends on the target retention interval. Their study
does not validate this app's 3/8/20-card rule.

[Rawson and Dunlosky (2022)](https://journals.sagepub.com/doi/10.1177/09637214221100484)
review successive relearning: reach a recall criterion and revisit the material
in later spaced sessions. They caution against treating one session count as
universally optimal. Three correct self-ratings in this app are therefore not
evidence of permanent mastery. A future scheduling change should distinguish
within-session recovery from between-day retention, with feedback after errors.

## Checks

```sh
python -m unittest discover -s tests -v
cd web
npm test
npm run build
```

## Source guide

| File | Responsibility |
| --- | --- |
| `desktop.py` | Desktop entry point; also retains the optional classic Tk interface. |
| `desktop_host.py` | Local authenticated webview host, state validation and desktop actions. |
| `organizer.py` | Legacy Tk two-pane organizer, retained for `--classic`. |
| `vocabulary.py` | Word parsing, local storage, group edits and resumable recall sessions. |
| `simulator.py` | Bank manager, authoring/import dialogs and timed practice UI. |
| `question_bank.py` | Plain question parsers, validation, deduplication and backed-up storage. |
| `web/src/App.tsx` | Vocabulary UI and browser persistence. |
| `web/src/Desktop.tsx`, `web/src/desktop.css` | Webview desktop pages and styling. |
| `web/src/LibraryWorkspace.tsx` | Library browsing, inline editors, drag/drop and clipboard UI. |
| `web/src/clipboard.ts` | Content-only group/word snapshots and explicit clipboard routing. |
| `web/src/import.ts` | Word-format parsing, corrections and validation. |
| `web/src/library.ts` | Word/group types, statistics and existing-catalog merge. |
| `web/src/review.ts` | Review queue and session recovery. |
| `web/src/styles.css`, `web/src/main.tsx`, `web/index.html` | Appearance and browser entry. |
| `examples/vocabulary.json`, `examples/questions.json` | One original word and question. |
| `tests/test_*.py`, `web/tests/*.test.mts` | Parser, bank-storage and review regression tests. |
| `web/package.json`, `web/package-lock.json`, `web/vite.config.js` | Frontend dependencies and build/server configuration. |
| `.gitignore`, `README.md` | Publication exclusions and usage documentation. |
