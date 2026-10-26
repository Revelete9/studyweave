"""Python desktop workspace for vocabulary, question banks and timed practice."""
from __future__ import annotations

import json
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk, filedialog

from question_bank import read_bank, discover_banks, save_bank, parse_questions, append_questions
from question_bank import FORMATS_HELP as QUESTION_FORMATS_HELP
from simulator import SATReadingSimulator
from vocabulary import VocabularyStore, parse_words, FORMATS_HELP
from organizer import Organizer

ROOT = Path(__file__).resolve().parent
BG, PAPER, INK = "#F3EFE6", "#FFFDF7", "#283E32"
GREEN, SELECTED, ORANGE = "#293E33", "#3D5547", "#CD7656"
MUTED, LINE, PALE = "#778177", "#E6E1D6", "#E9EEE5"
SANS, SERIF = "Segoe UI", "Georgia"


def label(parent, text, size=11, color=INK, serif=False, bold=False, **kwargs):
    return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                    font=(SERIF if serif else SANS, size, "bold" if bold else "normal"),
                    justify="left", **kwargs)


def button(parent, text, command, primary=False):
    return tk.Button(parent, text=text, command=command, font=(SANS, 11),
                     bg="#52775E" if primary else PALE, fg=PAPER if primary else INK,
                     activebackground=SELECTED if primary else PALE,
                     activeforeground=PAPER if primary else INK,
                     relief="flat", bd=0, padx=17, pady=10, cursor="hand2",
                     highlightthickness=0, highlightbackground=LINE,
                     highlightcolor=ORANGE)


def icon(parent, kind, background, foreground, size=28):
    """Small code-drawn line icons; no external artwork or icon font required."""
    c = tk.Canvas(parent, width=size, height=size, bg=background,
                  highlightthickness=0, bd=0)
    s = size / 28
    def line(*points):
        c.create_line(*(v*s for v in points), fill=foreground, width=1.6*s,
                      capstyle=tk.ROUND, joinstyle=tk.ROUND)
    if kind == "book":
        line(3, 5, 11, 5, 14, 8, 17, 5, 25, 5, 25, 23, 17, 23, 14, 25, 11, 23, 3, 23, 3, 5)
        line(14, 8, 14, 25)
    elif kind == "practice":
        c.create_oval(4*s, 4*s, 24*s, 24*s, outline=foreground, width=1.6*s)
        line(14, 8, 14, 14, 19, 17)
    else:
        line(5, 4, 23, 4, 23, 24, 5, 24, 5, 4)
        for y in (9, 14, 19):
            line(9, y, 19, y)
    return c


class DesktopApp:
    def __init__(self, root, data_dir=None):
        self.root = root
        self.data_dir = Path(data_dir) if data_dir else ROOT / "data"
        self.store = VocabularyStore(self.data_dir, ROOT / "examples/vocabulary.json")
        self.book_id = self.group_id = None
        self.book_review = False
        self.review_active = False
        self.review_key_down = set()
        self.review_key_time = 0
        self.review_help = False
        self.study_order = tk.StringVar(value="Sequential")
        root.title("SAT Study Kit")
        root.geometry("1180x790")
        root.minsize(1060, 740)
        root.configure(bg=BG)
        # Native title-bar icon, drawn using the same book motif as the sidebar.
        self.app_icon = tk.PhotoImage(width=32, height=32)
        self.app_icon.put(GREEN, to=(0, 0, 32, 32))
        for box in ((5, 7, 14, 25), (17, 7, 26, 25)):
            self.app_icon.put(PAPER, to=box)
        self.app_icon.put(ORANGE, to=(13, 6, 17, 27))
        root.iconphoto(True, self.app_icon)
        self.page = "Vocabulary"
        self.revealed = False
        self.exam_window = None
        self.exam_app = None
        self.bank_path = None
        self.form_snapshot = None
        self.nav = {}
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Treeview", background=PAPER, fieldbackground=PAPER, foreground=INK, rowheight=40, borderwidth=0, font=(SANS, 11))
        style.configure("Treeview.Heading", background=PAPER, foreground=MUTED, relief="flat", font=(SANS, 10))
        style.map("Treeview", background=[("selected", "#DEE8DA")], foreground=[("selected", INK)])
        style.configure("TCombobox", padding=9, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, arrowsize=13)
        style.map("TCombobox", fieldbackground=[("readonly", PAPER)], foreground=[("readonly", INK)])
        style.configure("TEntry", padding=8, fieldbackground=PAPER, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        self.build_shell()
        self.show("Vocabulary")
        root.protocol("WM_DELETE_WINDOW", self.close)
        # A dedicated first bindtag avoids Space also invoking a focused button.
        self.review_bindtag = f"StudyReview{id(self)}"
        root.bind_class(self.review_bindtag, "<KeyPress>", self.review_key)
        root.bind_class(self.review_bindtag, "<KeyRelease>", lambda e: self.review_key_down.discard(e.keysym.lower()))
        root.bindtags((self.review_bindtag,) + root.bindtags())
        root.bind("<FocusOut>", lambda e: self.review_key_down.clear() if e.widget == root else None)

    def build_shell(self):
        side = tk.Frame(self.root, bg=GREEN, width=228)
        side.pack(side=tk.LEFT, fill=tk.Y)
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=GREEN)
        brand.pack(fill=tk.X, padx=24, pady=(35, 38))
        icon(brand, "book", GREEN, ORANGE, 38).pack(side=tk.LEFT, padx=(0, 13))
        label(brand, "Study Kit", 21, PAPER, serif=True).pack(anchor="w")
        for name, glyph in (("Vocabulary", "book"), ("Organize", "banks"), ("Practice", "practice"), ("Question Banks", "banks")):
            row = tk.Frame(side, bg=GREEN)
            row.pack(fill=tk.X, padx=13, pady=4)
            stripe = tk.Frame(row, bg=GREEN, width=3)
            stripe.pack(side=tk.LEFT, fill=tk.Y)
            pic = icon(row, glyph, GREEN, PAPER, 23)
            pic.pack(side=tk.LEFT, padx=(13, 9))
            nav_button = tk.Button(row, text=name, command=lambda n=name: self.show(n),
                                   bg=GREEN, fg=PAPER, activebackground=SELECTED,
                                   activeforeground=PAPER, bd=0, relief="flat", anchor="w",
                                   font=(SANS, 11), pady=14, cursor="hand2",
                                   highlightthickness=1, highlightbackground=GREEN,
                                   highlightcolor=ORANGE)
            nav_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
            pic.bind("<Button-1>", lambda _e, n=name: self.show(n))
            self.nav[name] = row, stripe, pic, nav_button
        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=38, pady=28)
        self.content = tk.Frame(self.main, bg=BG)
        self.content.pack(fill=tk.BOTH, expand=True)
        self.feedback = tk.Frame(self.main, bg=BG)
        self.feedback.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

    def notice(self, text, error=False):
        for child in self.feedback.winfo_children():
            child.destroy()
        label(self.feedback, text, 11, "#A44F35" if error else MUTED, wraplength=760).pack(anchor="w")

    def leave_form(self, action):
        if self.form_snapshot and self.form_snapshot() != self.form_initial:
            self.notice("You have unsaved changes.")
            row = tk.Frame(self.feedback, bg=BG)
            row.pack(anchor="w", pady=(6, 0))
            def discard():
                self.form_snapshot = None
                action()
            button(row, "Discard changes", discard).pack(side=tk.LEFT, padx=(0, 8))
            button(row, "Keep editing", lambda: self.notice("")).pack(side=tk.LEFT)
            return False
        return True

    def show(self, page, force=False):
        if not force and not self.leave_form(lambda: self.show(page, True)):
            return
        self.form_snapshot = None
        self.review_active = False
        self.review_help = False
        self.notice("")
        self.page = page
        for name, (row, stripe, pic, nav_button) in self.nav.items():
            active = name == page
            color = SELECTED if active else GREEN
            row.configure(bg=color)
            stripe.configure(bg=ORANGE if active else GREEN)
            pic.configure(bg=color)
            nav_button.configure(bg=color, highlightbackground=color)
        for widget in self.content.winfo_children():
            widget.destroy()
        {"Vocabulary": self.vocabulary, "Practice": self.practice,
         "Question Banks": self.question_banks, "Organize": self.organize}[page]()

    def organize(self):
        self.heading("Organize vocabulary")
        self.organizer = Organizer(self.content, self.store, self.notice, button, label,
                                   (BG, PAPER, INK, MUTED, LINE, ORANGE), self.book_id, self.group_id)
        self.form_snapshot = self.organizer.draft
        self.form_initial = self.organizer.draft()

    def open_organizer(self, create_kind=None):
        self.show("Organize")
        if self.page != "Organize":
            return
        if create_kind:
            pane = self.organizer.panes[1]
            pane["bid"], pane["gid"] = self.book_id or pane["bid"], self.group_id
            self.organizer.refresh()
            self.organizer.toggle_creator(pane)
            pane["create_kind"].set(create_kind)
            self.organizer.creator_fields(pane)

    def heading(self, title):
        label(self.content, title, 30, serif=True).pack(anchor="w", pady=(8, 26))

    def panel(self, parent):
        return tk.Frame(parent, bg=PAPER, highlightthickness=0)

    def form(self, title):
        """An in-page editor with a fixed footer and a scrollable body."""
        self.review_active = False
        for child in self.content.winfo_children():
            child.destroy()
        self.notice("")
        self.heading(title)
        footer = tk.Frame(self.content, bg=BG)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(16, 0))
        button(footer, "Cancel", lambda: self.show(self.page)).pack(side=tk.LEFT)
        card = self.panel(self.content)
        card.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(card, bg=PAPER, highlightthickness=0)
        scroll = ttk.Scrollbar(card, command=canvas.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(canvas, bg=PAPER, padx=24, pady=18)
        window = canvas.create_window(0, 0, window=body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        # Bind only this editor's descendants, never the separate exam window.
        def bind_wheel(widget):
            def wheel(event):
                canvas.yview_scroll(-int(event.delta / 120), "units")
                return "break"
            if not isinstance(widget, tk.Text):
                widget.bind("<MouseWheel>", wheel)
            for child in widget.winfo_children():
                bind_wheel(child)
        body.after_idle(lambda: bind_wheel(card) if card.winfo_exists() else None)
        return body, footer

    def field(self, parent, title, value="", height=1):
        label(parent, title, 11, MUTED).pack(anchor="w", pady=(10, 7))
        if height == 1:
            control = ttk.Entry(parent, font=(SANS, 12))
            control.insert(0, value)
        else:
            control = tk.Text(parent, height=height, wrap="word", font=(SANS, 12),
                              bg="#F8F7F1", fg=INK, bd=0, padx=12, pady=10,
                              highlightthickness=1, highlightbackground=LINE, highlightcolor=ORANGE)
            control.insert("1.0", value)
        control.pack(fill=tk.X, pady=(0, 6))
        return control

    @staticmethod
    def field_value(control):
        return control.get("1.0", "end-1c") if isinstance(control, tk.Text) else control.get()

    def watch_form(self, controls):
        self.form_snapshot = lambda: tuple(self.field_value(c) for c in controls)
        self.form_initial = self.form_snapshot()

    def saved(self, message):
        self.show(self.page, force=True)
        self.notice(message)

    def vocabulary(self):
        if self.group_id:
            group = next((g for g in self.store.state["groups"] if g["id"] == self.group_id), None)
            if group:
                self.book_id = group["book_id"]
            else:
                self.group_id = None
        if self.book_id is None:
            return self.books_page()
        if self.group_id is None:
            return self.groups_page()
        book = next(b for b in self.store.state["books"] if b["id"] == self.book_id)
        crumbs = tk.Frame(self.content, bg=BG)
        crumbs.pack(fill=tk.X, pady=(0, 8))
        button(crumbs, "Books", lambda: self.browse()).pack(side=tk.LEFT)
        button(crumbs, book["name"], lambda: self.browse(self.book_id)).pack(side=tk.LEFT, padx=8)
        self.heading(self.store.group(self.group_id)["name"])
        self.group_choices = [g for g in self.store.state["groups"] if g["book_id"] == self.book_id]
        row = tk.Frame(self.content, bg=BG)
        row.pack(fill=tk.X, pady=(0, 14))
        label(row, "Word group", 12).pack(side=tk.LEFT, padx=(0, 12))
        selector = ttk.Combobox(row, values=[g["name"] for g in self.group_choices], state="readonly", width=24)
        selector.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if self.group_choices:
            index = next((i for i, g in enumerate(self.group_choices) if g["id"] == self.group_id), 0)
            self.group_id = self.group_choices[index]["id"]
            selector.current(index)
        def select(_event):
            self.group_id = self.group_choices[selector.current()]["id"]
            self.refresh_words()
        selector.bind("<<ComboboxSelected>>", select)
        button(row, "New group", self.new_group).pack(side=tk.LEFT, padx=8)
        button(row, "Rename", self.rename_group).pack(side=tk.LEFT)
        actions = tk.Frame(self.content, bg=BG)
        actions.pack(fill=tk.X, pady=(0, 14))
        for title, action in (("Add word", self.edit_word), ("Edit word", lambda: self.edit_word(True)), ("Paste words", self.import_words), ("Export", self.export_words)):
            button(actions, title, action).pack(side=tk.LEFT, padx=(0, 6))
        button(actions, "Start / Resume", self.start_review, True).pack(side=tk.RIGHT)
        self.search = tk.StringVar()
        query = tk.Frame(self.content, bg=BG)
        query.pack(fill=tk.X, pady=(0, 14))
        label(query, "Search", 12).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Entry(query, textvariable=self.search, font=(SANS, 12)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        table = tk.Frame(self.content, bg=PAPER)
        table.pack(fill=tk.BOTH, expand=True)
        self.word_list = ttk.Treeview(table, columns=("term", "meaning", "errors", "streak"), show="headings", selectmode="browse")
        for key, title, width in (("term", "Word", 140), ("meaning", "Meaning", 360), ("errors", "Errors", 65), ("streak", "Streak", 65)):
            self.word_list.heading(key, text=title)
            self.word_list.column(key, width=width, minwidth=50, stretch=key in ("term", "meaning"))
        scroll = ttk.Scrollbar(table, command=self.word_list.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.word_list.configure(yscrollcommand=scroll.set)
        self.word_list.pack(fill=tk.BOTH, expand=True)
        self.word_list.bind("<Double-1>", lambda _e: self.edit_word(True))
        self.word_count = label(self.content, "", 11, MUTED)
        self.word_count.pack(anchor="w", pady=(12, 0))
        self.search.trace_add("write", lambda *_: self.refresh_words())
        self.refresh_words()

    def browse(self, bid=None, gid=None):
        self.book_id, self.group_id = bid, gid
        self.show("Vocabulary")

    def book_form(self, bid=None):
        body, footer = self.form("Rename book" if bid else "New word book")
        name = self.field(body, "Book name (e.g. SAT, CET-4, CET-6)", next((b["name"] for b in self.store.state["books"] if b["id"] == bid), ""))
        self.watch_form([name])
        def save():
            try:
                self.book_id = self.store.name_book(name.get(), bid)
                self.group_id = None
                self.saved("Book saved.")
            except (OSError, ValueError) as exc:
                self.notice(str(exc), True)
        button(footer, "Save book", save, True).pack(side=tk.RIGHT)

    def library_table(self, columns):
        frame = self.panel(self.content)
        frame.pack(fill=tk.BOTH, expand=True, pady=16)
        table = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for key, title, width in columns:
            table.heading(key, text=title)
            table.column(key, width=width)
        scroll = ttk.Scrollbar(frame, command=table.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        table.configure(yscrollcommand=scroll.set)
        table.pack(fill=tk.BOTH, expand=True)
        return table

    def books_page(self):
        self.heading("Word books")
        row = tk.Frame(self.content, bg=BG)
        row.pack(fill=tk.X)
        button(row, "New book", lambda: self.open_organizer("Book")).pack(side=tk.LEFT)
        button(row, "Organize", self.open_organizer).pack(side=tk.RIGHT)
        table = self.library_table((("name", "Book", 300), ("groups", "Groups", 100), ("words", "Words", 100), ("done", "Completed groups", 140)))
        for book in self.store.state["books"]:
            groups = [g for g in self.store.state["groups"] if g["book_id"] == book["id"]]
            done = sum(self.store.group_status(g["id"]) == "Complete" for g in groups)
            table.insert("", "end", iid=book["id"], values=(book["name"], len(groups), sum(len(g["words"]) for g in groups), done))
        def chosen(action):
            selected = table.selection()
            if not selected:
                self.notice("Choose a book first.")
                return
            action(selected[0])
        button(row, "Open book", lambda: chosen(lambda bid: self.browse(bid)), True).pack(side=tk.LEFT, padx=8)
        button(row, "Rename", lambda: chosen(self.book_form)).pack(side=tk.LEFT)
        table.bind("<Double-1>", lambda _e: chosen(lambda bid: self.browse(bid)))

    def groups_page(self):
        book = next(b for b in self.store.state["books"] if b["id"] == self.book_id)
        self.study_order.set(self.store.state["book_sessions"].get(self.book_id, {}).get("mode", "Sequential"))
        button(self.content, "Books", lambda: self.browse()).pack(anchor="w", pady=(0, 8))
        self.heading(book["name"])
        row = tk.Frame(self.content, bg=BG)
        row.pack(fill=tk.X)
        button(row, "New group", self.new_group).pack(side=tk.LEFT)
        button(row, "Paste a group", lambda: self.import_form(new_words=True)).pack(side=tk.LEFT, padx=8)
        ttk.Combobox(row, values=("Sequential", "Random"), textvariable=self.study_order, state="readonly", width=12).pack(side=tk.RIGHT)
        button(row, "Study whole book", self.start_book, True).pack(side=tk.RIGHT, padx=8)
        table = self.library_table((("name", "Group / study plan", 320), ("words", "Words", 80), ("status", "Progress", 150)))
        for group in self.store.state["groups"]:
            if group["book_id"] == self.book_id:
                table.insert("", "end", iid=group["id"], values=(group["name"], len(group["words"]), self.store.group_status(group["id"])))
        def chosen(study=False):
            selected = table.selection()
            if not selected:
                self.notice("Choose a group first.")
                return
            self.group_id = selected[0]
            self.start_review() if study else self.show("Vocabulary")
        bottom = tk.Frame(self.content, bg=BG)
        bottom.pack(fill=tk.X)
        button(bottom, "Open group", chosen).pack(side=tk.LEFT)
        button(bottom, "Study selected group", lambda: chosen(True), True).pack(side=tk.RIGHT)
        table.bind("<Double-1>", lambda _e: chosen())

    def refresh_words(self):
        self.word_list.delete(*self.word_list.get_children())
        words = self.store.group(self.group_id)["words"] if self.group_id else []
        query = self.search.get().casefold()
        shown = [w for w in words if query in (w["term"] + " " + w["meaning"]).casefold()]
        for w in shown:
            self.word_list.insert("", "end", iid=w["id"], values=(w["term"], w["meaning"].replace("\n", " "), w["forgotten"], w["streak"]))
        self.word_count.configure(text=f"{len(shown)} / {len(words)} words")

    def new_group(self):
        self.open_organizer("Group")

    def rename_group(self):
        if not self.group_id:
            return
        self.group_form(self.group_id)

    def group_form(self, gid=None):
        body, footer = self.form("Rename word group" if gid else "New word group")
        name = self.field(body, "Group name", self.store.group(gid)["name"] if gid else "")
        self.watch_form([name])
        def save():
            try:
                self.group_id = self.store.name_group(name.get(), gid, self.book_id)
                self.saved("Word group saved.")
            except (ValueError, OSError) as exc:
                self.notice(str(exc), True)
        button(footer, "Save group", save, True).pack(side=tk.RIGHT)
        name.focus_set()

    def edit_word(self, editing=False):
        if not self.group_id:
            self.notice("Create a word group first.")
            return
        if not editing:
            self.open_organizer("Word")
            return
        gid, old = self.group_id, None
        if editing:
            selected = self.word_list.selection()
            if not selected:
                self.notice("Choose a word to edit.")
                return
            old = next(w for w in self.store.group(gid)["words"] if w["id"] == selected[0])
        body, footer = self.form("Edit word" if editing else "Add word")
        controls = {}
        for key, title, height in (("term", "Word", 1), ("phonetic", "Pronunciation", 1), ("meaning", "Meaning", 3), ("expansion", "Notes / example", 3)):
            controls[key] = self.field(body, title, (old or {}).get(key, ""), height)
        self.watch_form(controls.values())
        def save():
            try:
                raw = {key: self.field_value(field) for key, field in controls.items()}
                if old and "sequence" in old:
                    raw["sequence"] = old["sequence"]
                added, skipped = self.store.put_words(gid, [raw], old["id"] if old else None)
                if skipped:
                    self.notice("This word already exists. Use Edit word to change it.", True)
                    return
                self.saved("Word saved.")
            except (ValueError, OSError) as exc:
                self.notice(str(exc), True)
        button(footer, "Save word", save, True).pack(side=tk.RIGHT)
        controls["term"].focus_set()

    def import_words(self):
        if not self.group_id:
            self.notice("Create a word group first.")
            return
        self.import_form()

    def import_form(self, questions=False, new_words=False):
        gid, path = self.group_id, self.bank_path
        body, footer = self.form("Paste questions" if questions else "Paste a word group" if new_words else "Paste words")
        title = self.field(body, "New bank title (only for Save as new bank)" if questions else "New group name") if questions or new_words else None
        top = tk.Frame(body, bg=PAPER)
        top.pack(fill=tk.X, pady=(10, 12))
        kind = tk.StringVar(value="auto")
        formats = ("auto", "plain", "json", "csv", "tsv", "tagged") if questions else ("auto", "plain", "json", "csv", "tsv", "pipe", "pairs")
        select = ttk.Combobox(top, textvariable=kind, values=formats, state="readonly", width=12)
        select.pack(side=tk.LEFT)
        source = self.field(body, "Paste material", height=7)
        example = "1. Which word means brief and clear?\nA. Concise\nB. Obsolete\nC. Ambiguous\nD. Contradictory\nAnswer: A\n\n2. Which word means no longer used?\nA. Concise\nB. Obsolete\nC. Ambiguous\nD. Contradictory\nAnswer: B" if questions else "1. concise: brief and clear\n2. obsolete: no longer used"
        label(body, "Number each question; label options A.–D. and Answer:." if questions else "One word per line: word: meaning (or word = meaning).", 11, MUTED).pack(anchor="w", pady=5)
        def choose_file():
            file = filedialog.askopenfilename(parent=self.root, filetypes=[("Study files", "*.json *.csv *.tsv *.txt")])
            if file:
                try:
                    if Path(file).stat().st_size > 2_000_000:
                        raise ValueError("Import limit: 2 MB.")
                    text = Path(file).read_text(encoding="utf-8-sig")
                    source.delete("1.0", "end")
                    source.insert("1.0", text)
                except (OSError, ValueError) as exc:
                    self.notice(str(exc), True)
        button(top, "Open file", choose_file).pack(side=tk.RIGHT)
        def insert_example():
            if source.get("1.0", "end-1c").strip():
                self.notice("The example only fills an empty input; your text was kept.")
                return
            source.insert("1.0", example)
        button(top, "Example", insert_example).pack(side=tk.RIGHT, padx=8)
        help_slot = tk.Frame(body, bg=PAPER)
        help_slot.pack(fill=tk.X)
        help_box = tk.Text(help_slot, height=10, wrap="word", bg=PAPER, fg=MUTED, font=(SANS, 11), bd=0)
        help_box.insert("1.0", ("Plain text: numbered questions (1. or 1)), A.–D. options, optional Answer: and Explanation:. Separate questions with their next number. Indent continuation lines that begin with a number.\n\n" + QUESTION_FORMATS_HELP) if questions else FORMATS_HELP)
        help_box.configure(state="disabled")
        def toggle_help():
            if help_box.winfo_manager():
                help_box.pack_forget()
            else:
                help_box.pack(fill=tk.X, pady=10)
        button(top, "Formats & corrections", toggle_help).pack(side=tk.LEFT, padx=8)
        result = self.field(body, "Preview", height=7)
        result.configure(state="disabled")
        self.watch_form([source, select] + ([title] if title is not None else []))
        preview = {}
        def inspect():
            preview.clear()
            try:
                text = source.get("1.0", "end-1c")
                data, notes = (parse_questions if questions else parse_words)(text, kind.get())
                preview.update(text=text, kind=kind.get(), data=data)
                summary = "\n".join(notes) + "\n\n" + json.dumps(data, ensure_ascii=False, indent=2)
                self.notice("Preview ready. Review it before saving.")
            except ValueError as exc:
                summary = str(exc)
            result.configure(state="normal")
            result.delete("1.0", "end")
            result.insert("1.0", summary)
            result.configure(state="disabled")
        def save(new=False):
            if not preview or preview["text"] != source.get("1.0", "end-1c") or preview["kind"] != kind.get():
                self.notice("Preview the current input first.", True)
                return
            try:
                if questions:
                    if new:
                        if not title.get().strip():
                            raise ValueError("Enter a new bank title.")
                        bank, notes = {**preview["data"], "title": title.get().strip()}, []
                    else:
                        if not path:
                            raise ValueError("Select a question bank first.")
                        bank, notes = append_questions(read_bank(path), preview["data"])
                    self.persist_bank(bank, None if new else path)
                    self.saved("Questions saved. " + " ".join(notes))
                elif new_words:
                    self.group_id = self.store.import_group(self.book_id, title.get(), preview["data"])
                    self.saved("New word group saved.")
                else:
                    added, skipped = self.store.put_words(gid, preview["data"])
                    self.saved(f"Added {added} words; skipped {skipped} existing words.")
            except (ValueError, OSError) as exc:
                self.notice(str(exc), True)
        button(footer, "Preview", inspect).pack(side=tk.LEFT, padx=8)
        button(footer, "Save new group" if new_words else "Add to group", save, True).pack(side=tk.RIGHT)
        if questions:
            button(footer, "Save as new bank", lambda: save(True)).pack(side=tk.RIGHT, padx=8)

    def export_words(self):
        if not self.group_id:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Export vocabulary", defaultextension=".json", initialfile="vocabulary.json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                group = self.store.group(self.group_id)
                words = [{k: w[k] for k in ("term", "meaning", "phonetic", "expansion")} for w in group["words"]]
                Path(path).write_text(json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except OSError as exc:
                self.notice(str(exc), True)

    def start_review(self, restart=False):
        if not self.group_id:
            self.notice("Create a word group first.")
            return
        try:
            self.book_review = False
            self.store.begin(self.group_id, restart, self.study_order.get())
            self.revealed = False
            self.review_card()
        except (ValueError, OSError) as exc:
            self.notice(str(exc), True)

    def start_book(self, restart=False):
        try:
            self.book_review = True
            self.group_id = self.store.begin_book(self.book_id, self.study_order.get(), restart)
            self.revealed = False
            if self.group_id is None:
                for child in self.content.winfo_children():
                    child.destroy()
                self.review_active = False
                self.heading("Book complete")
                button(self.content, "Back to groups", lambda: self.browse(self.book_id)).pack(anchor="w", pady=12)
                button(self.content, "Start new book round", lambda: self.start_book(True), True).pack(anchor="w")
            else:
                self.review_card()
        except (OSError, ValueError) as exc:
            self.notice(str(exc), True)

    def review_key(self, event):
        if not self.review_active or event.widget.winfo_toplevel() != self.root:
            return
        key = event.keysym.lower()
        if key not in ("space", "1", "2", "3", "escape", "question", "f1") or event.state & 0xC:
            return
        if key in self.review_key_down:
            return "break"
        self.review_key_down.add(key)
        if key == "escape":
            self.show("Vocabulary")
        elif key in ("question", "f1"):
            self.toggle_review_help()
        elif key == "space":
            self.revealed = not self.revealed
            self.review_card()
        elif time.monotonic() - self.review_key_time >= .25:
            self.review_key_time = time.monotonic()
            self.rate_review({"1": "remembered", "2": "forgotten", "3": "skipped"}[key])
        return "break"

    def toggle_review_help(self):
        self.review_help = not self.review_help
        self.review_card()

    def rate_review(self, result):
        if result != "skipped" and not self.revealed:
            self.notice("Reveal the meaning with Space before rating.")
            return
        try:
            self.store.rate(self.group_id, result)
            self.notice("")
            self.revealed = False
            if self.book_review and self.store.group_status(self.group_id) == "Complete":
                self.start_book()
            else:
                self.review_card()
        except (OSError, ValueError) as exc:
            self.notice(str(exc), True)

    def review_card(self):
        self.review_active = True
        for child in self.content.winfo_children():
            child.destroy()
        group = self.store.group(self.group_id)
        session = self.store.state["sessions"][self.group_id]
        if self.book_review:
            book = next(b for b in self.store.state["books"] if b["id"] == self.book_id)
            label(self.content, f"{book['name']} / {self.study_order.get()}", 11, MUTED).pack(anchor="w")
        self.heading(group["name"])
        row = tk.Frame(self.content, bg=BG)
        row.pack(fill=tk.X, pady=(0, 14))
        button(row, "Back to words", lambda: self.show("Vocabulary")).pack(side=tk.LEFT)
        button(row, "?", self.toggle_review_help).pack(side=tk.LEFT, padx=8)
        if self.review_help:
            label(self.content, "Space: show / hide meaning   ·   1: remember   ·   2: forgot   ·   3: skip\nEsc: return (progress saved)   ·   ? / F1: help. Reveal before rating. Shortcuts only work here.", 11, MUTED, wraplength=780).pack(anchor="w", pady=(0, 12))
        pos = session["cursor"]
        label(row, f"{min(pos + 1, len(session['queue']))} / {len(session['queue'])}", 12, MUTED).pack(side=tk.RIGHT)
        card = self.panel(self.content)
        card.pack(fill=tk.BOTH, expand=True)
        if pos >= len(session["queue"]):
            self.review_active = False
            label(card, "Round complete", 32, serif=True).pack(pady=(85, 25))
            button(card, "Start new round", lambda: self.start_review(True), True).pack()
            return
        word = next(w for w in group["words"] if w["id"] == session["queue"][pos])
        # Scrollable text keeps long user-supplied terms/definitions accessible.
        actions = tk.Frame(card, bg=PAPER)
        actions.pack(side=tk.BOTTOM, pady=22)
        for title, result in (("Remember", "remembered"), ("Forgot", "forgotten"), ("Skip", "skipped")):
            b = button(actions, title, lambda r=result: self.rate_review(r), result == "remembered")
            b.pack(side=tk.LEFT, padx=6)
            if result != "skipped" and not self.revealed:
                b.configure(state="disabled")
        def reveal():
            self.revealed = not self.revealed
            self.review_card()
        button(card, "Hide meaning" if self.revealed else "Reveal meaning", reveal).pack(side=tk.BOTTOM)
        text = tk.Text(card, bg=PAPER, fg=INK, wrap="word", font=(SANS, 14), bd=0, padx=30, pady=30, height=7)
        scroll = ttk.Scrollbar(card, command=text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill=tk.BOTH, expand=True)
        text.tag_configure("term", font=(SERIF, 40), justify="center", spacing3=22)
        text.tag_configure("body", justify="center", spacing3=18)
        text.insert("end", word["term"] + "\n", "term")
        if word["phonetic"]:
            text.insert("end", word["phonetic"] + "\n", "body")
        if self.revealed:
            text.insert("end", word["meaning"] + "\n\n" + word["expansion"], "body")
        text.configure(state="disabled")
        def tag(widget):
            widget.bindtags((self.review_bindtag,) + tuple(t for t in widget.bindtags() if t != self.review_bindtag))
            for child in widget.winfo_children():
                tag(child)
        tag(self.content)
        self.root.focus_set()

    def practice(self):
        self.heading("Practice")
        card = self.panel(self.content)
        card.pack(fill=tk.BOTH, expand=True)
        center = tk.Frame(card, bg=PAPER)
        center.pack(fill=tk.BOTH, expand=True, padx=30, pady=28)
        label(center, "Question group", 18, serif=True).pack(anchor="w", pady=(0, 12))
        choices, errors = discover_banks(self.data_dir)
        selector = ttk.Combobox(center, values=[name for name, _ in choices], state="readonly", font=(SANS, 12))
        selector.pack(fill=tk.X)
        summary = label(center, "", 12, MUTED)
        summary.pack(anchor="w", pady=16)
        durations = tk.Frame(center, bg=PAPER)
        durations.pack(fill=tk.X, pady=12)
        times = []
        for i in (1, 2):
            col = tk.Frame(durations, bg=PAPER)
            col.pack(side=tk.LEFT, padx=(0, 30))
            label(col, f"Module {i} minutes", 12).pack(anchor="w", pady=(0, 10))
            value = tk.StringVar(value="32")
            ttk.Spinbox(col, from_=1, to=180, textvariable=value, width=10, font=(SANS, 13)).pack(anchor="w")
            times.append(value)
        def selected(_event=None):
            if selector.current() >= 0:
                try:
                    bank = read_bank(choices[selector.current()][1])
                    counts = [sum(q["module"] == n for q in bank["questions"]) for n in (1, 2)]
                    summary.configure(text=f"Module 1: {counts[0]} questions    |    Module 2: {counts[1]} questions")
                except (ValueError, OSError) as exc:
                    summary.configure(text=str(exc))
        selector.bind("<<ComboboxSelected>>", selected)
        if choices:
            selector.current(0)
            selected()
        def start():
            if selector.current() < 0:
                self.notice("Choose a question group first.")
                return
            try:
                minutes = [int(v.get()) for v in times]
                if any(not 1 <= n <= 180 for n in minutes):
                    raise ValueError
            except ValueError:
                self.notice("Enter whole minutes from 1 to 180.", True)
                return
            self.open_exam(choices[selector.current()][1], minutes)
        button(center, "Start exam", start, True).pack(anchor="w", pady=(35, 15))
        button(center, "Manage question groups", lambda: self.show("Question Banks")).pack(anchor="w")
        if errors:
            button(center, "Unreadable bank files", lambda: self.notice("\n".join(errors), True)).pack(anchor="w", pady=12)

    def open_exam(self, path, minutes):
        # Reuse the original exam UI, not a restyled imitation or a second engine.
        if self.exam_window is not None and self.exam_window.winfo_exists():
            self.exam_window.deiconify()
            self.exam_window.lift()
            return
        try:
            bank = read_bank(path)
            if not any(q["module"] == 1 for q in bank["questions"]):
                raise ValueError("This group needs at least one question in Module 1.")
            self.exam_window = tk.Toplevel(self.root)
            self.exam_app = SATReadingSimulator(self.exam_window, self.data_dir)
            self.exam_window.protocol("WM_DELETE_WINDOW", self.close_exam)
            self.exam_app.bank_choices = [(bank["title"], Path(path))]
            self.exam_app.bank_var.set(bank["title"])
            self.exam_app.module_1_time_var.set(str(minutes[0]))
            self.exam_app.module_2_time_var.set(str(minutes[1]))
            self.exam_app.start_exam()
        except (ValueError, OSError) as exc:
            if self.exam_window is not None:
                self.exam_window.destroy()
                self.exam_window = self.exam_app = None
            self.notice(str(exc), True)

    def close_exam(self):
        if self.exam_window is None or not self.exam_window.winfo_exists():
            return True
        if self.exam_app.timer_running and not messagebox.askyesno(
                "Close test", "Close this test and discard its current answers?", parent=self.exam_window):
            return False
        self.exam_app.clear_root()  # Cancel the pending timer before destroying the window.
        self.exam_window.destroy()
        self.exam_window = self.exam_app = None
        return True

    def close(self):
        if not self.leave_form(self.close):
            return
        if self.close_exam():
            self.root.destroy()

    def question_banks(self):
        self.heading("Question banks")
        choices, errors = discover_banks(self.data_dir)
        row = tk.Frame(self.content, bg=BG)
        row.pack(fill=tk.X, pady=(0, 14))
        selector = ttk.Combobox(row, values=[name for name, _ in choices], state="readonly", font=(SANS, 11))
        selector.pack(side=tk.LEFT, fill=tk.X, expand=True)
        button(row, "New group", self.bank_form).pack(side=tk.LEFT, padx=8)
        button(row, "Rename", lambda: self.bank_form(True)).pack(side=tk.LEFT)
        actions = tk.Frame(self.content, bg=BG)
        actions.pack(fill=tk.X, pady=(0, 14))
        for title, command in (("Add question", self.edit_question), ("Edit question", lambda: self.edit_question(True)),
                               ("Paste questions", lambda: self.import_form(True)), ("Export", self.export_bank)):
            button(actions, title, command).pack(side=tk.LEFT, padx=(0, 6))
        search = ttk.Entry(self.content, font=(SANS, 12))
        label(self.content, "Search questions", 11, MUTED).pack(anchor="w", pady=(0, 6))
        search.pack(fill=tk.X, pady=(0, 14))
        card = self.panel(self.content)
        card.pack(fill=tk.BOTH, expand=True)
        self.question_list = ttk.Treeview(card, columns=("module", "question"), show="headings", selectmode="browse", height=5)
        self.question_list.heading("module", text="Module")
        self.question_list.heading("question", text="Question")
        self.question_list.column("module", width=75, stretch=False)
        self.question_list.column("question", width=350)
        scroll = ttk.Scrollbar(card, command=self.question_list.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.question_list.configure(yscrollcommand=scroll.set)
        self.question_list.pack(fill=tk.BOTH, expand=True)
        detail = tk.Text(self.content, height=7, wrap="word", bg=PAPER, fg=INK, bd=0, padx=16, pady=14, font=(SANS, 11), state="disabled")
        detail.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        def show_detail(_event=None):
            selection = self.question_list.selection()
            text = ""
            if selection:
                q = self.current_bank["questions"][int(selection[0])]
                text = f"{q['passage']}\n\n{q['question']}\n\n" + "\n".join(f"{key}. {q['options'][key]}" for key in "ABCD") + f"\n\nAnswer: {q['answer'] or 'Unknown'}\n{q['explanation']}"
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", text.strip())
            detail.configure(state="disabled")
        def refresh(_event=None):
            self.question_list.delete(*self.question_list.get_children())
            query = search.get().casefold()
            for index, q in enumerate((self.current_bank or {}).get("questions", [])):
                if query in (q["question"] + " " + q["passage"]).casefold():
                    self.question_list.insert("", "end", iid=str(index), values=(q["module"], q["question"].replace("\n", " ")))
            show_detail()
        def selected(_event=None):
            if selector.current() < 0:
                return
            try:
                path = choices[selector.current()][1]
                self.current_bank = read_bank(path)
                self.bank_path = path
                refresh()
            except (OSError, ValueError) as exc:
                self.notice(str(exc), True)
        self.current_bank = None
        search.bind("<KeyRelease>", refresh)
        selector.bind("<<ComboboxSelected>>", selected)
        self.question_list.bind("<<TreeviewSelect>>", show_detail)
        self.question_list.bind("<Double-1>", lambda _e: self.edit_question(True))
        if choices:
            selector.current(next((i for i, (_, p) in enumerate(choices) if p == self.bank_path), 0))
            selected()
        if errors:
            self.notice("Some bank files could not be read: " + "; ".join(errors), True)

    def persist_bank(self, bank, path=None):
        directory = self.data_dir / "banks"
        # Examples and legacy banks remain read-only; editing creates a local copy.
        if path and Path(path).resolve().parent != directory.resolve():
            path = None
        self.bank_path = save_bank(bank, directory, path)

    def bank_form(self, rename=False):
        path = self.bank_path if rename else None
        try:
            bank = read_bank(path) if path else {"schema_version": 1, "title": "", "questions": []}
        except (OSError, ValueError) as exc:
            self.notice(str(exc), True)
            return
        body, footer = self.form("Rename question group" if rename else "New question group")
        name = self.field(body, "Group name", bank["title"])
        self.watch_form([name])
        def save():
            try:
                self.persist_bank({**bank, "title": name.get().strip()}, path)
                self.saved("Question group saved.")
            except (OSError, ValueError) as exc:
                self.notice(str(exc), True)
        button(footer, "Save group", save, True).pack(side=tk.RIGHT)
        name.focus_set()

    def edit_question(self, editing=False):
        if not self.current_bank:
            self.notice("Create or choose a question group first.")
            return
        selection = self.question_list.selection()
        if editing and not selection:
            self.notice("Choose a question to edit.")
            return
        index = int(selection[0]) if editing else None
        bank, path = self.current_bank, self.bank_path
        old = bank["questions"][index] if editing else {}
        body, footer = self.form("Edit question" if editing else "Add question")
        controls = {}
        for key in ("module", "passage", "question", "A", "B", "C", "D", "answer", "explanation"):
            value = old.get("options", {}).get(key, "") if key in "ABCD" else old.get(key, "1" if key == "module" else "")
            if key in ("module", "answer"):
                label(body, "Module" if key == "module" else "Answer (blank = unknown)", 11, MUTED).pack(anchor="w", pady=(10, 7))
                control = ttk.Combobox(body, values=("1", "2") if key == "module" else ("", "A", "B", "C", "D"), state="readonly", width=14)
                control.set(str(value or ""))
                control.pack(anchor="w", pady=(0, 6))
            else:
                control = self.field(body, key.capitalize(), value, 3 if key in ("passage", "question", "explanation") else 2)
            controls[key] = control
        self.watch_form(controls.values())
        def save():
            try:
                fields = {key: self.field_value(c) for key, c in controls.items()}
                raw = {key: val for key, val in fields.items() if key not in "ABCD"}
                raw["options"] = {key: fields[key] for key in "ABCD"}
                if old:
                    raw["id"] = old["id"]
                incoming, _ = parse_questions(json.dumps([raw]), "json")
                if editing:
                    items = list(bank["questions"])
                    items[index] = incoming["questions"][0]
                    updated, notes = parse_questions(json.dumps({**bank, "questions": items}), "json")
                else:
                    updated, notes = append_questions(bank, incoming)
                self.persist_bank(updated, path)
                self.saved("Question saved. " + " ".join(notes))
            except (OSError, ValueError) as exc:
                self.notice(str(exc), True)
        button(footer, "Save question", save, True).pack(side=tk.RIGHT)

    def export_bank(self):
        if not self.current_bank:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Export questions", defaultextension=".json", initialfile="question-bank.json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                Path(path).write_text(json.dumps(self.current_bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                self.notice("Question bank exported.")
            except OSError as exc:
                self.notice(str(exc), True)


if __name__ == "__main__":
    import sys
    if "--exam" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--exam", type=Path)
        parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
        parser.add_argument("--minutes", nargs=2, type=int, default=[32, 32])
        args = parser.parse_args()
        window = tk.Tk()
        app = SATReadingSimulator(window, args.data_dir)
        bank = read_bank(args.exam)
        app.bank_choices = [(bank["title"], args.exam)]
        app.bank_var.set(bank["title"])
        app.module_1_time_var.set(str(args.minutes[0]))
        app.module_2_time_var.set(str(args.minutes[1]))
        def close_exam():
            if app.timer_running and not messagebox.askyesno("Close test", "Close this test and discard its current answers?", parent=window):
                return
            app.clear_root()
            window.destroy()
        window.protocol("WM_DELETE_WINDOW", close_exam)
        app.start_exam()
        window.mainloop()
    elif "--classic" in sys.argv:
        window = tk.Tk()
        DesktopApp(window)
        window.mainloop()
    else:
        from desktop_host import main
        try:
            main()
        except Exception as exc:
            # A pythonw launch must not fail invisibly.
            window = tk.Tk()
            window.withdraw()
            messagebox.showerror("Unable to open SAT Study Kit", str(exc), parent=window)
            window.destroy()
            raise
