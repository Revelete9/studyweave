from __future__ import annotations

import csv
import json
import tkinter as tk
from pathlib import Path
from tkinter import font, messagebox, ttk, filedialog, simpledialog
from question_bank import FORMATS_HELP, parse_questions, append_questions, read_bank, save_bank, discover_banks

class SATReadingSimulator:
    def __init__(self, root: tk.Tk, data_dir: Path | None = None, start_screen=True):
        self.root = root
        self.data_dir = data_dir or Path(__file__).resolve().parent / "data"
        self.root.title("StudyWeave - SAT Practice")
        self.root.geometry("1024x768")
        self.root.minsize(900, 650)
        self.root.configure(bg="#FFFFFF")
        self.available_fonts = ["Georgia", "Times New Roman", "Arial", "Segoe UI"]
        self.current_passage_font = self.available_fonts[0]
        self.content_font_size = 15
        self.line_reader_enabled = False
        self.bank_data: dict = {}
        self.modules: list[dict] = []
        self.module_times = [32, 32]
        self.current_module_idx = 0
        self.current_idx = 0
        self.answers: dict[tuple[int, int], str] = {}
        self.marked_questions: set[tuple[int, int]] = set()
        self.eliminated_options: set[tuple[int, int, str]] = set()
        self.timer_running = False
        self.timer_hidden = False
        self.timer_job: str | None = None
        self.time_left = 0
        self.selected_option = tk.StringVar(value="")
        self.mark_var = tk.BooleanVar(value=False)
        if start_screen:
            self.show_start_screen()

    def clear_root(self) -> None:
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None
        if hasattr(self, "question_navigator") and self.question_navigator.winfo_exists():
            self.question_navigator.destroy()
        for widget in self.root.winfo_children():
            widget.destroy()

    def discover_banks(self) -> list[tuple[str, Path]]:
        banks, self.bank_errors = discover_banks(self.data_dir)
        return banks

    def show_start_screen(self) -> None:
        self.timer_running = False
        self.clear_root()
        self.root.configure(bg="#F6F7F9")
        card = tk.Frame(self.root, bg="white", bd=1, relief=tk.SOLID)
        card.place(relx=.5, rely=.5, anchor="center", width=680, height=560)
        tk.Label(card, text="StudyWeave - SAT Practice", font=("Segoe UI", 25, "bold"), bg="white").pack(pady=(38, 8))
        tk.Label(card, text="Choose a test and set the time for each module.", font=("Segoe UI", 12), fg="#4B5563", bg="white").pack(pady=(0, 28))
        form = tk.Frame(card, bg="white")
        form.pack(fill=tk.X, padx=55)
        tk.Label(form, text="Question bank", font=("Segoe UI", 11, "bold"), bg="white").grid(row=0, column=0, sticky="w", pady=8)
        self.bank_choices = self.discover_banks()
        labels = [label for label, _ in self.bank_choices]
        self.bank_var = tk.StringVar(value=labels[0] if labels else "")
        ttk.Combobox(form, textvariable=self.bank_var, values=labels, state="readonly", width=48).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 20))
        tk.Label(form, text="Module 1 minutes", font=("Segoe UI", 11, "bold"), bg="white").grid(row=2, column=0, sticky="w", pady=8)
        tk.Label(form, text="Module 2 minutes", font=("Segoe UI", 11, "bold"), bg="white").grid(row=2, column=2, sticky="w", padx=(35, 0), pady=8)
        self.module_1_time_var, self.module_2_time_var = tk.StringVar(value="32"), tk.StringVar(value="32")
        tk.Spinbox(form, from_=1, to=180, textvariable=self.module_1_time_var, font=("Segoe UI", 12), width=8).grid(row=3, column=0, sticky="w")
        tk.Spinbox(form, from_=1, to=180, textvariable=self.module_2_time_var, font=("Segoe UI", 12), width=8).grid(row=3, column=2, sticky="w", padx=(35, 0))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        start_button = tk.Button(card, text="Start Test", command=self.start_exam, font=("Segoe UI", 13, "bold"), bg="#2563EB", fg="white", bd=0, padx=38, pady=12)
        start_button.pack(pady=(24, 10))
        tk.Button(card, text="Browse / Edit / Import Question Banks", command=self.show_bank_manager,
                  font=("Segoe UI", 11), padx=12, pady=8).pack()
        if self.bank_errors:
            tk.Button(card, text=f"{len(self.bank_errors)} bank files need attention", command=lambda: messagebox.showwarning("Unreadable banks", "\n".join(self.bank_errors))).pack(pady=6)
        if not labels:
            start_button.config(state=tk.DISABLED)
            tk.Label(card, text="No compatible JSON question banks were found.", font=("Segoe UI", 10), fg="#B91C1C", bg="white").pack()

    def show_bank_manager(self):
        self.timer_running = False
        self.clear_root()
        self.root.configure(bg="white")
        toolbar = ttk.Frame(self.root, padding=12)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="Back to Test", command=self.show_start_screen).pack(side=tk.RIGHT)
        ttk.Label(toolbar, text="Question Banks", font=("Segoe UI", 20, "bold")).pack(side=tk.LEFT)
        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        left, right = ttk.Frame(body, padding=6), ttk.Frame(body, padding=6)
        body.add(left, weight=1)
        body.add(right, weight=3)
        self.manager_choices = self.discover_banks()
        self.manager_bank = None
        self.manager_path = None
        self.manager_index = None
        self.manager_selector = ttk.Combobox(left, state="readonly", values=[label for label, _ in self.manager_choices], width=34)
        self.manager_selector.pack(fill=tk.X, pady=6)
        self.manager_selector.bind("<<ComboboxSelected>>", self.select_manager_bank)
        ttk.Button(left, text="New Bank", command=self.new_bank).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Rename Bank", command=self.rename_bank).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Import Questions / Bank", command=self.import_questions_dialog).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Export Bank JSON", command=self.export_bank).pack(fill=tk.X, pady=3)
        self.manager_search = tk.StringVar()
        ttk.Label(left, text="Search questions").pack(anchor="w", pady=(12, 0))
        ttk.Entry(left, textvariable=self.manager_search).pack(fill=tk.X)
        self.manager_search.trace_add("write", lambda *_: self.refresh_question_list())
        self.manager_list = tk.Listbox(left, exportselection=False, width=35)
        scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.manager_list.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.manager_list.configure(yscrollcommand=scroll.set)
        self.manager_list.pack(fill=tk.BOTH, expand=True, pady=6)
        self.manager_list.bind("<<ListboxSelect>>", self.select_manager_question)
        buttons = ttk.Frame(right)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Add Question", command=lambda: self.edit_question()).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Edit Selected", command=self.edit_selected_question).pack(side=tk.LEFT, padx=5)
        self.manager_detail = tk.Text(right, wrap=tk.WORD, font=("Segoe UI", 12), padx=12, pady=12, state=tk.DISABLED)
        detail_scroll = ttk.Scrollbar(right, command=self.manager_detail.yview)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.manager_detail.configure(yscrollcommand=detail_scroll.set)
        self.manager_detail.pack(fill=tk.BOTH, expand=True, pady=8)
        ttk.Label(right, text="Changes are saved locally. Existing banks are backed up before changes.\nEdits to the bundled example or old data create an editable copy.").pack(anchor="w")
        if self.manager_choices:
            self.manager_selector.current(0)
            self.select_manager_bank()

    def select_manager_bank(self, _event=None):
        index = self.manager_selector.current()
        if index < 0:
            return
        try:
            self.manager_path = self.manager_choices[index][1]
            self.manager_bank = read_bank(self.manager_path)
            self.manager_index = None
            self.refresh_question_list()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Bank", str(exc))

    def refresh_question_list(self):
        if not hasattr(self, "manager_list"):
            return
        self.manager_list.delete(0, tk.END)
        self.manager_index = None
        self.manager_indices = []
        query = self.manager_search.get().casefold()
        for index, question in enumerate((self.manager_bank or {}).get("questions", [])):
            if query and query not in (question["question"] + " " + question["passage"]).casefold():
                continue
            self.manager_indices.append(index)
            label = question["question"].replace("\n", " ")
            self.manager_list.insert(tk.END, f"{index + 1}. [M{question['module']}] {label[:65]}")
        self.manager_detail.config(state=tk.NORMAL)
        self.manager_detail.delete("1.0", tk.END)
        self.manager_detail.insert(tk.END, "Select a question to read it, or add/import your own questions.")
        self.manager_detail.config(state=tk.DISABLED)

    def select_manager_question(self, _event=None):
        selected = self.manager_list.curselection()
        if not selected or not self.manager_bank:
            return
        self.manager_index = self.manager_indices[selected[0]]
        q = self.manager_bank["questions"][self.manager_index]
        self.manager_detail.config(state=tk.NORMAL)
        self.manager_detail.delete("1.0", tk.END)
        self.manager_detail.insert(tk.END, f"{q['id']} · Module {q['module']}\n\n{q['passage']}\n\n{q['question']}\n\n" + "\n\n".join(f"{k}. {q['options'][k]}" for k in "ABCD") + f"\n\nAnswer: {q['answer'] or 'Unknown'}\n\nExplanation: {q['explanation']}")
        self.manager_detail.config(state=tk.DISABLED)

    def persist_manager_bank(self, bank, new=False):
        directory = self.data_dir / "banks"
        path = self.manager_path if not new else None
        if path and path.resolve().parent != directory.resolve():
            path = None
        target = save_bank(bank, directory, path)
        self.manager_bank, self.manager_path = bank, target
        self.manager_choices = self.discover_banks()
        self.manager_selector.configure(values=[label for label, _ in self.manager_choices])
        self.manager_selector.current(next(i for i, (_, p) in enumerate(self.manager_choices) if p.resolve() == target.resolve()))
        self.refresh_question_list()

    def new_bank(self):
        title = simpledialog.askstring("New Bank", "Bank title:", parent=self.root)
        if title and title.strip():
            try:
                self.persist_manager_bank({"schema_version": 1, "title": title.strip(), "questions": []}, new=True)
            except (OSError, ValueError) as exc:
                messagebox.showerror("Save", str(exc))

    def export_bank(self):
        if not self.manager_bank:
            return
        path = filedialog.asksaveasfilename(title="Export Bank", defaultextension=".json", initialfile="question-bank.json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                Path(path).write_text(json.dumps(self.manager_bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("Export", str(exc))

    def rename_bank(self):
        if not self.manager_bank:
            return
        title = simpledialog.askstring("Rename Bank", "Bank title:", initialvalue=self.manager_bank["title"], parent=self.root)
        if title and title.strip():
            try:
                self.persist_manager_bank({**self.manager_bank, "title": title.strip()})
            except (OSError, ValueError) as exc:
                messagebox.showerror("Save", str(exc))

    def edit_selected_question(self):
        if self.manager_index is None:
            messagebox.showinfo("Select a question", "Choose a question from the list first.")
            return
        self.edit_question(self.manager_index)

    def edit_question(self, index=None):
        if not self.manager_bank:
            messagebox.showinfo("Bank", "Create or choose a bank first.")
            return
        old = self.manager_bank["questions"][index] if index is not None else {}
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Question" if old else "Add Question")
        dialog.geometry("740x730")
        dialog.transient(self.root.winfo_toplevel())
        dialog.grab_set()
        panel = ttk.Frame(dialog, padding=12)
        panel.pack(fill=tk.BOTH, expand=True)
        controls = {}
        for row, key in enumerate(("module", "passage", "question", "A", "B", "C", "D", "answer", "explanation")):
            ttk.Label(panel, text=key.capitalize() + (" (optional)" if key in ("passage", "answer", "explanation") else "")).grid(row=row, column=0, sticky="nw", padx=(0, 10), pady=3)
            value = old.get("options", {}).get(key, "") if key in "ABCD" else old.get(key, 1 if key == "module" else "")
            if key in ("module", "answer"):
                control = ttk.Combobox(panel, state="readonly", values=("1", "2") if key == "module" else ("", "A", "B", "C", "D"))
                control.set(str(value or ""))
            else:
                control = tk.Text(panel, height=4 if key in ("passage", "question", "explanation") else 2, wrap=tk.WORD, font=("Segoe UI", 11))
                control.insert("1.0", value)
                panel.rowconfigure(row, weight=1)
            control.grid(row=row, column=1, sticky="nsew", pady=3)
            controls[key] = control
        panel.columnconfigure(1, weight=1)
        def save():
            try:
                fields = {key: widget.get("1.0", "end-1c") if isinstance(widget, tk.Text) else widget.get() for key, widget in controls.items()}
                raw = {key: val for key, val in fields.items() if key not in "ABCD"}
                raw["options"] = {key: fields[key] for key in "ABCD"}
                if old:
                    raw["id"] = old["id"]
                incoming, _ = parse_questions(json.dumps([raw]), "json")
                if index is None:
                    bank, notes = append_questions(self.manager_bank, incoming)
                else:
                    questions = list(self.manager_bank["questions"])
                    questions[index] = incoming["questions"][0]
                    bank, notes = parse_questions(json.dumps({**self.manager_bank, "questions": questions}), "json")
                if messagebox.askyesno("Save question", f"Save to {bank['title']}?\n" + "\n".join(notes), parent=dialog):
                    self.persist_manager_bank(bank)
                    dialog.destroy()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Question", str(exc), parent=dialog)
        ttk.Button(panel, text="Validate and Save", command=save).grid(row=9, column=1, sticky="e", pady=10)

    def import_questions_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Import Questions")
        dialog.geometry("850x760")
        dialog.transient(self.root.winfo_toplevel())
        dialog.grab_set()
        toolbar = ttk.Frame(dialog, padding=10)
        toolbar.pack(fill=tk.X)
        kind = tk.StringVar(value="auto")
        ttk.Label(toolbar, text="Format").pack(side=tk.LEFT)
        ttk.Combobox(toolbar, textvariable=kind, state="readonly", values=("auto", "json", "csv", "tsv", "tagged"), width=12).pack(side=tk.LEFT, padx=8)
        source = tk.Text(dialog, height=9, wrap=tk.WORD, font=("Consolas", 11))
        source.pack(fill=tk.BOTH, expand=True, padx=10)
        def open_file():
            path = filedialog.askopenfilename(parent=dialog, filetypes=[("Question files", "*.json *.csv *.tsv *.txt"), ("All files", "*.*")])
            if path:
                try:
                    if Path(path).stat().st_size > 2_000_000:
                        raise ValueError("Import limit: 2 MB.")
                    text = Path(path).read_text(encoding="utf-8-sig")
                    source.delete("1.0", tk.END)
                    source.insert("1.0", text)
                except (OSError, ValueError, UnicodeError) as exc:
                    messagebox.showerror("File", str(exc), parent=dialog)
        ttk.Button(toolbar, text="Open File", command=open_file).pack(side=tk.LEFT)
        help_box = tk.Text(dialog, height=9, wrap=tk.WORD, font=("Segoe UI", 10), bg="#F3F4F6")
        help_box.pack(fill=tk.X, padx=10, pady=8)
        help_box.insert("1.0", FORMATS_HELP)
        help_box.config(state=tk.DISABLED)
        result = tk.Text(dialog, height=10, wrap=tk.WORD, font=("Consolas", 10), state=tk.DISABLED)
        result.pack(fill=tk.BOTH, expand=True, padx=10)
        footer = ttk.Frame(dialog, padding=10)
        footer.pack(fill=tk.X)
        state = {}
        def preview():
            try:
                text = source.get("1.0", "end-1c")
                bank, notes = parse_questions(text, kind.get())
                state.update(text=text, format=kind.get(), bank=bank)
                display = f"{len(bank['questions'])} questions\n" + "\n".join(notes) + "\n\n" + json.dumps(bank, ensure_ascii=False, indent=2)
            except (ValueError, csv.Error) as exc:
                state.clear()
                display = str(exc)
            result.config(state=tk.NORMAL)
            result.delete("1.0", tk.END)
            result.insert("1.0", display)
            result.config(state=tk.DISABLED)
        def commit(new):
            if not state or state["text"] != source.get("1.0", "end-1c") or state["format"] != kind.get():
                messagebox.showinfo("Preview required", "Preview the current input before saving.", parent=dialog)
                return
            try:
                if new:
                    title = simpledialog.askstring("New Bank", "Bank title:", initialvalue=state["bank"]["title"], parent=dialog)
                    if not title or not title.strip():
                        return
                    bank, notes = {**state["bank"], "title": title.strip()}, []
                else:
                    if not self.manager_bank:
                        raise ValueError("Choose a bank or use Save as New Bank.")
                    bank, notes = append_questions(self.manager_bank, state["bank"])
                if messagebox.askyesno("Save import", f"Save {len(bank['questions'])} total questions to {bank['title']}?\n" + "\n".join(notes), parent=dialog):
                    self.persist_manager_bank(bank, new=new)
                    dialog.destroy()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Import", str(exc), parent=dialog)
        ttk.Button(footer, text="Preview", command=preview).pack(side=tk.LEFT)
        ttk.Button(footer, text="Append to Selected Bank", command=lambda: commit(False)).pack(side=tk.RIGHT)
        ttk.Button(footer, text="Save as New Bank", command=lambda: commit(True)).pack(side=tk.RIGHT, padx=8)

    def start_exam(self) -> None:
        path = next((path for label, path in self.bank_choices if label == self.bank_var.get()), None)
        if not path:
            messagebox.showerror("Question bank", "Please choose a question bank.")
            return
        try:
            times = [int(self.module_1_time_var.get()), int(self.module_2_time_var.get())]
            if any(value <= 0 for value in times):
                raise ValueError
        except ValueError:
            messagebox.showerror("Time", "Enter a positive whole number of minutes for each module.")
            return
        try:
            self.load_bank(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Question bank", f"Could not load the question bank:\n{exc}")
            return
        self.module_times = times
        self.current_module_idx = self.current_idx = 0
        self.answers.clear()
        self.marked_questions.clear()
        self.eliminated_options.clear()
        self.line_reader_enabled = False
        self.time_left = times[0] * 60
        self.timer_hidden = False
        self.setup_exam_ui()

    def load_bank(self, path: Path) -> None:
        bank = read_bank(path)
        if not bank["questions"]:
            raise ValueError("This bank is empty. Add a question in the bank manager first.")
        numbers = {q["module"] for q in bank["questions"]}
        if 1 not in numbers:
            raise ValueError("For a timed test, put at least one question in Module 1.")
        self.modules = [{"id": n, "title": f"Module {n}", "questions": [q for q in bank["questions"] if q["module"] == n]} for n in (1, 2) if n in numbers]
        self.bank_data = {"title": bank["title"], "section": "Reading and Writing practice"}

    def setup_exam_ui(self) -> None:
        self.clear_root()
        self.root.configure(bg="white")
        self.ui_font_bold = font.Font(family="Segoe UI", size=12, weight="bold")
        self.ui_font_normal = font.Font(family="Segoe UI", size=11)
        self.passage_font = font.Font(family=self.current_passage_font, size=self.content_font_size)
        self.timer_font = font.Font(family="Segoe UI", size=16, weight="bold")
        top = tk.Frame(self.root, bg="white", height=60)
        top.pack(fill=tk.X, pady=(10, 5))
        top_left = tk.Frame(top, bg="white")
        top_left.pack(side=tk.LEFT, fill=tk.Y, padx=20)
        self.section_label = tk.Label(top_left, bg="white", font=self.ui_font_bold)
        self.section_label.pack(side=tk.LEFT)
        tools = tk.Frame(top, bg="white")
        tools.pack(side=tk.RIGHT, fill=tk.Y, padx=20)
        tk.Label(tools, text="Passage Font:", bg="white", font=self.ui_font_normal).pack(side=tk.LEFT)
        self.font_var = tk.StringVar(value=self.current_passage_font)
        font_box = ttk.Combobox(tools, textvariable=self.font_var, values=self.available_fonts, state="readonly", width=15)
        font_box.pack(side=tk.LEFT, padx=5)
        font_box.bind("<<ComboboxSelected>>", self.change_font)
        tk.Button(
            tools, text="A−", command=lambda: self.change_font_size(-1), font=("Segoe UI", 10, "bold"),
            bg="white", bd=1, relief=tk.SOLID, padx=6,
        ).pack(side=tk.LEFT, padx=(4, 2))
        tk.Button(
            tools, text="A+", command=lambda: self.change_font_size(1), font=("Segoe UI", 10, "bold"),
            bg="white", bd=1, relief=tk.SOLID, padx=6,
        ).pack(side=tk.LEFT, padx=2)
        self.line_reader_btn = tk.Button(
            tools, text="Line Reader: Off", command=self.toggle_line_reader,
            font=("Segoe UI", 9, "bold"), bg="white", bd=1, relief=tk.SOLID, padx=7,
        )
        self.line_reader_btn.pack(side=tk.LEFT, padx=(7, 0))
        timer_frame = tk.Frame(top, bg="white")
        timer_frame.pack(expand=True)
        self.timer_label = tk.Label(timer_frame, font=self.timer_font, bg="white")
        self.timer_label.pack()
        self.hide_btn = tk.Button(timer_frame, text="Hide", command=self.toggle_timer, font=("Segoe UI", 9), bg="white", bd=1, relief=tk.SOLID, padx=10)
        self.hide_btn.pack(pady=(2, 0))
        tk.Frame(self.root, bg="#E5E7EB", height=2).pack(fill=tk.X)
        self.content_frame = tk.Frame(self.root, bg="white")
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
        bottom = tk.Frame(self.root, bg="#000000", height=60)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        bottom.pack_propagate(False)
        self.prev_btn = tk.Button(bottom, text="Back", command=self.prev_question, font=self.ui_font_bold, bg="#333333", fg="white", bd=0, width=10)
        self.prev_btn.pack(side=tk.LEFT, padx=20, pady=15)
        self.q_num_label = tk.Label(bottom, font=self.ui_font_bold, bg="#000000", fg="white", cursor="hand2")
        self.q_num_label.pack(side=tk.LEFT, expand=True)
        self.q_num_label.bind("<Button-1>", self.open_question_navigator)
        self.next_btn = tk.Button(bottom, text="Next", command=self.next_question, font=self.ui_font_bold, bg="#2563EB", fg="white", bd=0, width=12)
        self.next_btn.pack(side=tk.RIGHT, padx=20, pady=15)
        self.timer_running = True
        self.load_question()
        self._render_timer()
        self.timer_job = self.root.after(1000, self.update_timer)

    @property
    def current_module(self) -> dict:
        return self.modules[self.current_module_idx]

    @property
    def current_question(self) -> dict:
        return self.current_module["questions"][self.current_idx]

    @property
    def current_key(self) -> tuple[int, int]:
        return self.current_module_idx, self.current_idx

    def load_question(self) -> None:
        module, q_data = self.current_module, self.current_question
        questions = module["questions"]
        title = module.get("title") or f"Module {self.current_module_idx + 1}"
        self.section_label.config(text=f"Section 1, {title}: {self.bank_data.get('section', 'Reading and Writing')}")
        self.q_num_label.config(text=f"Question {self.current_idx + 1} of {len(questions)} ^")
        self.prev_btn.config(state=tk.NORMAL if self.current_idx > 0 else tk.DISABLED)
        self.next_btn.config(text="Submit Module" if self.current_idx == len(questions) - 1 else "Next")
        self.mark_var.set(self.current_key in self.marked_questions)
        self.selected_option.set(self.answers.get(self.current_key, ""))
        self.render_content(q_data)

    def render_content(self, q_data: dict) -> None:
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        missing = not q_data.get("available", True)
        left = tk.Frame(self.content_frame, bg="white", width=480)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 20))
        left.pack_propagate(False)
        tk.Frame(self.content_frame, bg="#E5E7EB", width=2).pack(side=tk.LEFT, fill=tk.Y)
        right_shell = tk.Frame(self.content_frame, bg="white", width=480)
        right_shell.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(20, 0))
        right_shell.pack_propagate(False)
        self.right_canvas = tk.Canvas(right_shell, bg="white", bd=0, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_shell, orient=tk.VERTICAL, command=self.right_canvas.yview)
        self.right_canvas.configure(yscrollcommand=right_scrollbar.set)
        right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = tk.Frame(self.right_canvas, bg="white")
        right_window = self.right_canvas.create_window((0, 0), window=right, anchor="nw")
        right.bind(
            "<Configure>",
            lambda _event: self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all")),
        )
        self.right_canvas.bind(
            "<Configure>",
            lambda event: self.right_canvas.itemconfigure(right_window, width=event.width),
        )
        self.right_canvas.bind("<MouseWheel>", self.scroll_right_panel)

        if missing:
            tk.Label(left, text="Question needs source review", font=("Segoe UI", 18, "bold"), fg="#9A3412", bg="white").pack(pady=(130, 12))
            tk.Label(left, text="Missing content is preserved for review; no replacement was invented.", font=("Segoe UI", 11), fg="#7C2D12", bg="white", wraplength=470).pack()

        if q_data.get("needs_review"):
            tk.Label(left, text="Needs review: " + "; ".join(q_data["needs_review"]),
                     wraplength=440, fg="#9A3412", bg="white").pack(pady=8)

        if not missing:
            passage = tk.Text(left, wrap=tk.WORD, font=self.passage_font, bg="white", bd=0, highlightthickness=0, spacing2=8)
            passage.pack(fill=tk.BOTH, expand=True, pady=10)
            self.passage_widget = passage
            passage_text = q_data.get("passage", "")
            passage.insert(tk.END, passage_text)
            passage.tag_configure("line_reader", background="#FEF3C7")
            passage.bind("<Motion>", self.update_line_reader)
            passage.bind("<Button-1>", self.update_line_reader)
            passage.config(state=tk.DISABLED)
            if self.line_reader_enabled:
                passage.tag_add("line_reader", "1.0", "1.0 lineend")

        question_header = tk.Frame(right, bg="white")
        question_header.pack(fill=tk.X, pady=(10, 15))
        tk.Label(question_header, text=str(self.current_idx + 1), bg="black", fg="white", font=("Segoe UI", 14, "bold"), width=3, height=1).pack(side=tk.LEFT)
        tk.Checkbutton(question_header, text="Mark for Review", variable=self.mark_var, command=self.toggle_mark, bg="white", activebackground="white", font=self.ui_font_normal).pack(side=tk.LEFT, padx=10)
        question_text = "This question has missing content; review the source before practicing." if missing else q_data.get("question", "")
        question = tk.Text(right, font=self.passage_font, bg="white", bd=0, highlightthickness=0, wrap=tk.WORD, height=4)
        question.pack(fill=tk.X, pady=(0, 10))
        question.insert(tk.END, question_text)
        question.config(state=tk.DISABLED)
        question.bind("<MouseWheel>", self.scroll_right_panel)

        options = q_data.get("options") or {}
        self.radio_buttons = []
        self.option_fonts = []
        for letter in "ABCD":
            option_text = str(options.get(letter, "") or "").strip()
            option_frame = tk.Frame(right, bg="white")
            option_frame.pack(fill=tk.X, pady=5)
            eliminated = (*self.current_key, letter) in self.eliminated_options
            option_font = self.passage_font.copy()
            option_font.configure(overstrike=eliminated)
            self.option_fonts.append(option_font)
            eliminate_button = tk.Button(
                option_frame,
                text="↶" if eliminated else "✕",
                command=lambda choice=letter: self.toggle_eliminate(choice),
                font=("Segoe UI", 10, "bold"),
                fg="#6B7280" if eliminated else "#9CA3AF",
                bg="white",
                activebackground="#F3F4F6",
                bd=1,
                relief=tk.SOLID,
                width=2,
                cursor="hand2",
            )
            eliminate_button.pack(side=tk.RIGHT, padx=(6, 0), anchor="n")
            button = tk.Radiobutton(
                option_frame, text=f"{letter}. {option_text}", variable=self.selected_option, value=letter,
                command=self.record_answer, font=option_font, fg="#9CA3AF" if eliminated else "#111827",
                bg="white", activebackground="white", wraplength=385, justify=tk.LEFT, anchor=tk.W,
            )
            button.pack(anchor="nw", side=tk.LEFT, fill=tk.X, expand=True)
            button.bind("<Button-3>", lambda _event, choice=letter: self.toggle_eliminate(choice))
            button.bind("<MouseWheel>", self.scroll_right_panel)
            eliminate_button.bind("<MouseWheel>", self.scroll_right_panel)
            option_frame.bind("<MouseWheel>", self.scroll_right_panel)
            self.radio_buttons.append(button)
            if missing or eliminated:
                button.config(state=tk.DISABLED)
            if missing:
                eliminate_button.config(state=tk.DISABLED)

    def record_answer(self) -> None:
        self.answers[self.current_key] = self.selected_option.get()

    def toggle_eliminate(self, letter: str) -> None:
        key = (*self.current_key, letter)
        if key in self.eliminated_options:
            self.eliminated_options.remove(key)
        else:
            self.eliminated_options.add(key)
            if self.selected_option.get() == letter:
                self.selected_option.set("")
                self.answers.pop(self.current_key, None)
        self.render_content(self.current_question)

    def toggle_mark(self) -> None:
        if self.mark_var.get():
            self.marked_questions.add(self.current_key)
        else:
            self.marked_questions.discard(self.current_key)

    def change_font(self, _event=None) -> None:
        self.current_passage_font = self.font_var.get()
        self.passage_font.configure(family=self.current_passage_font)
        self.render_content(self.current_question)

    def change_font_size(self, amount: int) -> None:
        self.content_font_size = min(20, max(11, self.content_font_size + amount))
        self.passage_font.configure(size=self.content_font_size)
        self.render_content(self.current_question)

    def toggle_line_reader(self) -> None:
        self.line_reader_enabled = not self.line_reader_enabled
        self.line_reader_btn.config(text=f"Line Reader: {'On' if self.line_reader_enabled else 'Off'}")
        passage = getattr(self, "passage_widget", None)
        if not passage or not passage.winfo_exists():
            return
        passage.tag_remove("line_reader", "1.0", tk.END)
        if self.line_reader_enabled:
            first_visible = passage.index("@0,0")
            passage.tag_add(
                "line_reader",
                f"{first_visible} display linestart",
                f"{first_visible} display lineend",
            )

    def update_line_reader(self, event) -> None:
        if not self.line_reader_enabled:
            return
        passage = event.widget
        index = passage.index(f"@{event.x},{event.y}")
        passage.tag_remove("line_reader", "1.0", tk.END)
        passage.tag_add("line_reader", f"{index} display linestart", f"{index} display lineend")

    def scroll_right_panel(self, event) -> str:
        direction = -1 if event.delta > 0 else 1
        self.right_canvas.yview_scroll(direction * 3, "units")
        return "break"

    def open_question_navigator(self, _event=None) -> None:
        if hasattr(self, "question_navigator") and self.question_navigator.winfo_exists():
            self.question_navigator.lift()
            self.question_navigator.focus_force()
            return
        popup = tk.Toplevel(self.root)
        self.question_navigator = popup
        popup.title("Questions")
        popup.transient(self.root)
        popup.resizable(False, False)
        width, height = 430, 265
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + self.root.winfo_height() - height - 80
        popup.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        popup.configure(bg="white")
        title = self.current_module.get("title") or f"Module {self.current_module_idx + 1}"
        tk.Label(popup, text=f"{title} Questions", font=("Segoe UI", 14, "bold"), bg="white").pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(popup, text="Choose a question to jump to.", font=("Segoe UI", 10), fg="#6B7280", bg="white").pack(anchor="w", padx=20, pady=(0, 12))
        grid = tk.Frame(popup, bg="white")
        grid.pack(fill=tk.BOTH, expand=True, padx=18)
        for index, _question in enumerate(self.current_module["questions"]):
            key = self.current_module_idx, index
            if index == self.current_idx:
                bg, fg = "#111827", "white"
            elif key in self.answers:
                bg, fg = "#DBEAFE", "#1E3A8A"
            elif key in self.marked_questions:
                bg, fg = "#FEF3C7", "#92400E"
            else:
                bg, fg = "white", "#111827"
            button = tk.Button(grid, text=str(index + 1), command=lambda target=index: self.jump_to_question(target), font=("Segoe UI", 10, "bold"), bg=bg, fg=fg, activebackground="#BFDBFE", bd=1, relief=tk.SOLID, width=4, height=2)
            button.grid(row=index // 9, column=index % 9, padx=3, pady=3)

    def jump_to_question(self, index: int) -> None:
        if not 0 <= index < len(self.current_module["questions"]):
            return
        if hasattr(self, "question_navigator") and self.question_navigator.winfo_exists():
            self.question_navigator.destroy()
        self.current_idx = index
        self.load_question()

    def prev_question(self) -> None:
        if self.current_idx > 0:
            self.current_idx -= 1
            self.load_question()

    def next_question(self) -> None:
        if self.current_idx < len(self.current_module["questions"]) - 1:
            self.current_idx += 1
            self.load_question()
        else:
            self.finish_current_module()

    def finish_current_module(self, timed_out: bool = False) -> None:
        if not timed_out and not messagebox.askyesno("Submit module", "Submit this module? You cannot return after continuing."):
            return
        self.timer_running = False
        if self.current_module_idx + 1 < len(self.modules):
            self.show_module_break(timed_out)
        else:
            self.show_results()

    def show_module_break(self, timed_out: bool) -> None:
        self.clear_root()
        frame = tk.Frame(self.root, bg="white")
        frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(frame, text="Time is up" if timed_out else "Module submitted", font=("Segoe UI", 26, "bold"), bg="white").pack(pady=(190, 15))
        tk.Label(frame, text="Your Module 1 answers are saved. Start Module 2 when you are ready.", font=("Segoe UI", 13), bg="white", fg="#4B5563").pack()
        tk.Button(frame, text="Start Module 2", command=self.start_next_module, font=("Segoe UI", 13, "bold"), bg="#2563EB", fg="white", bd=0, padx=30, pady=12).pack(pady=35)

    def start_next_module(self) -> None:
        self.current_module_idx += 1
        self.current_idx = 0
        self.time_left = self.module_times[min(self.current_module_idx, len(self.module_times) - 1)] * 60
        self.timer_hidden = False
        self.setup_exam_ui()

    def update_timer(self) -> None:
        if not self.timer_running:
            return
        self.time_left = max(0, self.time_left - 1)
        if not self.timer_hidden:
            self._render_timer()
        if self.time_left == 0:
            self.timer_running = False
            messagebox.showinfo("Time", "Time is up for this module.")
            self.finish_current_module(timed_out=True)
            return
        self.timer_job = self.root.after(1000, self.update_timer)

    def _render_timer(self) -> None:
        minutes, seconds = divmod(self.time_left, 60)
        self.timer_label.config(text=f"{minutes:02d}:{seconds:02d}", fg="#DC2626" if self.time_left <= 300 else "black")

    def toggle_timer(self) -> None:
        self.timer_hidden = not self.timer_hidden
        if self.timer_hidden:
            self.timer_label.config(text="Timer hidden", fg="#6B7280")
            self.hide_btn.config(text="Show")
        else:
            self._render_timer()
            self.hide_btn.config(text="Hide")

    def show_results(self) -> None:
        self.timer_running = False
        self.clear_root()
        frame = tk.Frame(self.root, bg="white")
        frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)
        tk.Label(frame, text="Test Complete", font=("Segoe UI", 24, "bold"), bg="white").pack(anchor="w", pady=(0, 16))
        scroll = tk.Scrollbar(frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        result = tk.Text(frame, font=("Segoe UI", 12), bg="#F9FAFB", yscrollcommand=scroll.set, padx=20, pady=20, bd=1, relief=tk.SOLID)
        result.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=result.yview)
        for module_index, module in enumerate(self.modules):
            result.insert(tk.END, f"{module.get('title', f'Module {module_index + 1}')}\n", "heading")
            for question_index, q_data in enumerate(module["questions"]):
                key = module_index, question_index
                answer = "Source review needed" if not q_data.get("available", True) else self.answers.get(key, "Unanswered")
                marked = "  [Marked]" if key in self.marked_questions else ""
                result.insert(tk.END, f"Question {question_index + 1}: {answer}{marked}\n")
                supplied = q_data.get("answer")
                if supplied:
                    result.insert(tk.END, f"  Bank answer: {supplied}\n")
                else:
                    result.insert(tk.END, "  Bank answer: unknown (not graded)\n")
                if q_data.get("explanation"):
                    result.insert(tk.END, f"  Explanation: {q_data['explanation']}\n")
                if q_data.get("needs_review"):
                    result.insert(tk.END, "  Needs review: " + "; ".join(q_data["needs_review"]) + "\n")
            result.insert(tk.END, "\n")
        result.tag_configure("heading", font=("Segoe UI", 14, "bold"), spacing1=10, spacing3=6)
        result.config(state=tk.DISABLED)
        tk.Button(self.root, text="Back to Start", command=self.show_start_screen, font=("Segoe UI", 11, "bold"), bg="#2563EB", fg="white", bd=0, padx=18, pady=9).place(relx=.89, rely=.035, anchor="center")

    def confirm_exit(self) -> None:
        if messagebox.askyesno("Exit test", "Return to the start screen? Current answers will be discarded."):
            self.show_start_screen()


if __name__ == "__main__":
    root = tk.Tk()
    SATReadingSimulator(root)
    root.mainloop()
