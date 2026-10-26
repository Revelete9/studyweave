"""Two-pane vocabulary organization: explicit destinations and atomic transfers."""
import copy
import tkinter as tk
from tkinter import ttk


class Organizer:
    def __init__(self, parent, store, notify, button, label, colors, initial_book=None, initial_group=None):
        self.store, self.notify, self.button, self.label = store, notify, button, label
        self.bg, self.paper, self.ink, self.muted, self.line, self.accent = colors
        self.parent = parent
        self.drag = None
        self.undo_before = self.undo_after = None
        self.mode = tk.StringVar(value="Move")
        toolbar = tk.Frame(parent, bg=self.bg)
        toolbar.pack(fill=tk.X, pady=(0, 12))
        label(toolbar, "Drag to the other pane. Ctrl-drag copies.", 11, self.muted).pack(side=tk.LEFT)
        self.undo_button = button(toolbar, "Undo transfer", self.undo)
        self.undo_button.pack(side=tk.RIGHT)
        self.undo_button.configure(state="disabled")
        ttk.Combobox(toolbar, values=("Move", "Copy"), state="readonly", textvariable=self.mode, width=9).pack(side=tk.RIGHT, padx=12)
        split = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True)
        self.panes = []
        books = store.state["books"]
        default = books[0]["id"] if books else None
        for i in range(2):
            frame = tk.Frame(split, bg=self.paper, padx=12, pady=12, highlightthickness=2, highlightbackground=self.line)
            split.add(frame, weight=1)
            pane = {"frame": frame, "bid": initial_book if i == 0 and initial_book else default,
                    "gid": initial_group if i == 0 else None}
            self.panes.append(pane)
            self.build_pane(pane, i)
        self.refresh()

    def build_pane(self, pane, index):
        frame = pane["frame"]
        self.label(frame, "Left workspace" if index == 0 else "Right workspace", 16, serif=True).pack(anchor="w", pady=(0, 12))
        self.label(frame, "Book", 10, self.muted).pack(anchor="w")
        pane["book"] = ttk.Combobox(frame, state="readonly", width=16)
        pane["book"].pack(fill=tk.X, pady=(5, 10))
        pane["book"].bind("<<ComboboxSelected>>", lambda _e: self.select_book(pane))
        self.label(frame, "View groups or open a group", 10, self.muted).pack(anchor="w")
        pane["group"] = ttk.Combobox(frame, state="readonly", width=16)
        pane["group"].pack(fill=tk.X, pady=(5, 10))
        pane["group"].bind("<<ComboboxSelected>>", lambda _e: self.select_group(pane))
        actions = tk.Frame(frame, bg=self.paper)
        actions.pack(fill=tk.X, pady=(0, 10))
        self.button(actions, "New…", lambda: self.toggle_creator(pane)).pack(side=tk.LEFT)
        pane["search"] = tk.StringVar()
        ttk.Entry(frame, textvariable=pane["search"]).pack(fill=tk.X, pady=(0, 8))
        pane["search"].trace_add("write", lambda *_: self.refresh_table(pane))
        # Reserve the inline creator below the list; the opposite pane stays usable.
        pane["create"] = tk.Frame(frame, bg=self.paper)
        pane["create_kind"] = tk.StringVar(value="Group")
        pane["create_name"] = tk.StringVar()
        pane["create_meaning"] = tk.StringVar()
        pane["create_target"] = None
        pane["create_caption"] = self.label(pane["create"], "", 10, self.muted, wraplength=310)
        pane["create_caption"].pack(anchor="w", pady=(0, 6))
        kind = ttk.Combobox(pane["create"], values=("Book", "Group", "Word"), textvariable=pane["create_kind"], state="readonly", width=10)
        kind.pack(fill=tk.X)
        kind.bind("<<ComboboxSelected>>", lambda _e: self.creator_fields(pane))
        self.label(pane["create"], "Name / word", 10, self.muted).pack(anchor="w", pady=(7, 3))
        ttk.Entry(pane["create"], textvariable=pane["create_name"]).pack(fill=tk.X)
        pane["meaning_row"] = tk.Frame(pane["create"], bg=self.paper)
        self.label(pane["meaning_row"], "Meaning", 10, self.muted).pack(anchor="w", pady=(7, 3))
        ttk.Entry(pane["meaning_row"], textvariable=pane["create_meaning"]).pack(fill=tk.X)
        pane["create_buttons"] = tk.Frame(pane["create"], bg=self.paper)
        pane["create_buttons"].pack(fill=tk.X, pady=(8, 0))
        self.button(pane["create_buttons"], "Create", lambda: self.create(pane), True).pack(side=tk.RIGHT)
        self.button(pane["create_buttons"], "Hide", lambda: pane["create"].pack_forget()).pack(side=tk.LEFT)
        pane["count"] = self.label(frame, "", 10, self.muted)
        pane["count"].pack(side=tk.BOTTOM, anchor="w", pady=(8, 0))
        table_frame = tk.Frame(frame, bg=self.paper)
        table_frame.pack(fill=tk.BOTH, expand=True)
        table = ttk.Treeview(table_frame, columns=("name", "detail"), show="headings", selectmode="extended", height=5)
        table.heading("name", text="Group / word")
        table.heading("detail", text="Contents")
        table.column("name", width=150, minwidth=90)
        table.column("detail", width=160, minwidth=80)
        scroll = ttk.Scrollbar(table_frame, command=table.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        table.configure(yscrollcommand=scroll.set)
        table.pack(fill=tk.BOTH, expand=True)
        pane["table"] = table
        table.tag_configure("drop", background="#E0EADB")
        table.bind("<Double-1>", lambda e: self.open_group(pane, e))
        table.bind("<ButtonPress-1>", lambda e: self.press(pane, e))
        table.bind("<B1-Motion>", self.motion)
        table.bind("<ButtonRelease-1>", self.release)
        table.bind("<Escape>", lambda _e: self.cancel_drag())
        table.bind("<<TreeviewSelect>>", lambda _e: self.count(pane))

    def draft(self):
        return tuple((p["create_name"].get(), p["create_meaning"].get()) for p in self.panes)

    def refresh(self):
        books = self.store.state["books"]
        for pane in self.panes:
            pane["books"] = books
            if pane["bid"] not in {b["id"] for b in books}:
                pane["bid"] = books[0]["id"] if books else None
            pane["book"].configure(values=[b["name"] for b in books])
            if pane["bid"]:
                pane["book"].current(next(i for i, b in enumerate(books) if b["id"] == pane["bid"]))
            groups = [g for g in self.store.state["groups"] if g["book_id"] == pane["bid"]]
            pane["groups"] = groups
            if pane["gid"] not in {g["id"] for g in groups}:
                pane["gid"] = None
            pane["group"].configure(values=["All groups"] + [g["name"] for g in groups])
            pane["group"].current(next((i + 1 for i, g in enumerate(groups) if g["id"] == pane["gid"]), 0))
            self.refresh_table(pane)

    def refresh_table(self, pane):
        if "table" not in pane:
            return
        table = pane["table"]
        selected = table.selection()
        table.delete(*table.get_children())
        query = pane["search"].get().casefold()
        pane["kind"] = "word" if pane["gid"] else "group"
        items = self.store.group(pane["gid"])["words"] if pane["gid"] else pane.get("groups", [])
        for item in items:
            name = item["term"] if pane["gid"] else item["name"]
            detail = item["meaning"] if pane["gid"] else f"{len(item['words'])} words · {self.store.group_status(item['id'])}"
            if query in (name + " " + detail).casefold():
                table.insert("", "end", iid=item["id"], values=(name, detail.replace("\n", " ")))
        table.selection_set([iid for iid in selected if table.exists(iid)])
        self.count(pane)

    def count(self, pane):
        table = pane["table"]
        pane["count"].configure(text=f"{len(table.get_children())} shown · {len(table.selection())} selected")

    def select_book(self, pane):
        pane["bid"] = pane["books"][pane["book"].current()]["id"]
        pane["gid"] = None
        pane["search"].set("")
        self.refresh()

    def select_group(self, pane):
        i = pane["group"].current()
        pane["gid"] = pane["groups"][i - 1]["id"] if i > 0 else None
        pane["search"].set("")
        self.refresh_table(pane)

    def open_group(self, pane, event):
        row = pane["table"].identify_row(event.y)
        if not pane["gid"] and row:
            self.cancel_drag()
            pane["gid"] = row
            self.refresh()

    def toggle_creator(self, pane):
        if pane["create"].winfo_manager():
            pane["create"].pack_forget()
            return
        pane["create_target"] = (pane["bid"], pane["gid"])
        pane["create_kind"].set("Word" if pane["gid"] else "Group")
        book = next((b["name"] for b in pane["books"] if b["id"] == pane["bid"]), "No book")
        group = self.store.group(pane["gid"])["name"] if pane["gid"] else "All groups"
        pane["create_caption"].configure(text=f"Create in: {book} / {group}")
        pane["create"].pack(side=tk.BOTTOM, fill=tk.X, pady=(12, 0))
        self.creator_fields(pane)

    def creator_fields(self, pane):
        if pane["create_kind"].get() == "Word":
            pane["meaning_row"].pack(fill=tk.X, before=pane["create_buttons"])
        else:
            pane["meaning_row"].pack_forget()

    def create(self, pane):
        bid, gid = pane["create_target"]
        kind, name = pane["create_kind"].get(), pane["create_name"].get()
        try:
            if kind == "Book":
                pane["bid"] = self.store.name_book(name)
                pane["gid"] = None
            elif kind == "Group":
                if not bid:
                    raise ValueError("Choose a book before creating a group.")
                pane["bid"] = bid
                pane["gid"] = self.store.name_group(name, book_id=bid)
            else:
                if not gid:
                    raise ValueError("Open a group before creating a word.")
                _, skipped = self.store.put_words(gid, [{"term": name, "meaning": pane["create_meaning"].get()}])
                if skipped:
                    raise ValueError("That word already exists; it was not overwritten.")
                pane["bid"], pane["gid"] = bid, gid
            pane["create_name"].set("")
            pane["create_meaning"].set("")
            pane["create"].pack_forget()
            self.undo_before = self.undo_after = None
            self.undo_button.configure(state="disabled")
            self.refresh()
            self.notify(f"{kind} created. Drag items from the other pane to fill it.")
        except (ValueError, OSError) as exc:
            self.notify(str(exc), True)

    def press(self, pane, event):
        row = pane["table"].identify_row(event.y)
        self.drag = None
        if not row:
            return
        pane["table"].focus_set()
        self.drag = {"pane": pane, "row": row, "x": event.x_root, "y": event.y_root, "active": False}
        if row in pane["table"].selection() and not event.state & 5:
            return "break"  # Preserve multi-selection when starting a plain drag.

    def destination(self, source, x, y):
        for pane in self.panes:
            frame = pane["frame"]
            if not (frame.winfo_rootx() <= x < frame.winfo_rootx() + frame.winfo_width() and frame.winfo_rooty() <= y < frame.winfo_rooty() + frame.winfo_height()):
                continue
            if source["kind"] == "group":
                return pane, pane["bid"]
            if pane["gid"]:
                return pane, pane["gid"]
            table = pane["table"]
            if table.winfo_rootx() <= x < table.winfo_rootx() + table.winfo_width():
                row = table.identify_row(y - table.winfo_rooty())
                if row:
                    return pane, row
            return pane, None
        return None, None

    def motion(self, event):
        if not self.drag:
            return
        if abs(event.x_root - self.drag["x"]) + abs(event.y_root - self.drag["y"]) < 8:
            return
        self.drag["active"] = True
        source = self.drag["pane"]
        source["table"].configure(cursor="fleur")
        pane, target = self.destination(source, event.x_root, event.y_root)
        for p in self.panes:
            p["frame"].configure(highlightbackground=self.accent if p is pane and target else self.line)
            for iid in p["table"].get_children():
                p["table"].item(iid, tags=("drop",) if p is pane and iid == target else ())
        if pane:
            table = pane["table"]
            y = event.y_root - table.winfo_rooty()
            if 0 <= y < 25:
                table.yview_scroll(-1, "units")
            elif table.winfo_height() - 25 < y < table.winfo_height():
                table.yview_scroll(1, "units")
        mode = "Copy" if event.state & 4 or self.mode.get() == "Copy" else "Move"
        self.notify(f"{mode} {len(source['table'].selection())} {source['kind']}(s)" + (" — release to transfer." if target else " — drop on a group or open group pane."))
        return "break"

    def release(self, event):
        drag = self.drag
        if not drag or not drag["active"]:
            self.drag = None
            return
        source = drag["pane"]
        _, target = self.destination(source, event.x_root, event.y_root)
        duplicate = bool(event.state & 4) or self.mode.get() == "Copy"
        self.cancel_drag()
        if not target:
            self.notify("Nothing changed. Drop groups into a book; drop words into a group.")
            return "break"
        self.transfer(source, target, duplicate)
        return "break"

    def transfer(self, source, target, duplicate):
        before = copy.deepcopy(self.store.state)
        try:
            count = self.store.transfer(source["kind"], source["gid"] or source["bid"], target, source["table"].selection(), duplicate)
            self.undo_before, self.undo_after = before, copy.deepcopy(self.store.state)
            self.undo_button.configure(state="normal")
            self.refresh()
            self.notify(f"{'Copied' if duplicate else 'Moved'} {count} item(s). " + ("Copies start with fresh progress." if duplicate else "Learning records were preserved.") + " Undo is available.")
        except (ValueError, OSError) as exc:
            self.notify(str(exc), True)

    def undo(self):
        if self.undo_before is None:
            return
        if self.store.state != self.undo_after:
            self.notify("The library changed after that transfer; undo was not applied.", True)
            return
        try:
            self.store.save(self.undo_before)
            self.undo_before = self.undo_after = None
            self.undo_button.configure(state="disabled")
            self.refresh()
            self.notify("Transfer undone.")
        except (ValueError, OSError) as exc:
            self.notify(str(exc), True)

    def cancel_drag(self):
        self.drag = None
        for p in self.panes:
            p["frame"].configure(highlightbackground=self.line)
            p["table"].configure(cursor="")
            for iid in p["table"].get_children():
                p["table"].item(iid, tags=())
        return "break"
