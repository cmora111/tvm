import json
import pprint
from tkinter import *
from tkinter import messagebox, simpledialog
from ..utils.parsing import (
    parse_command_entry,
)

class HotkeyEditorWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Hotkey Editor")
        self.window.geometry("900x520")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Hotkey Editor",
            bd=4,
            width=32,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        top = Frame(outer)
        top.pack(fill=BOTH, expand=True)

        left = Frame(top)
        left.pack(side=LEFT, fill=Y)

        right = Frame(top)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=40, height=18)
        self.listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        row = 0

        Label(form, text="Hotkey:", width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.hotkey_var = StringVar()
        Entry(form, textvariable=self.hotkey_var, width=42).grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        Label(form, text="Category:", width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.category_var = StringVar()
        self.category_entry = Entry(form, textvariable=self.category_var, width=42)
        self.category_entry.grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        Label(form, text="Command:", width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.command_var = StringVar()
        self.command_entry = Entry(form, textvariable=self.command_var, width=42)
        self.command_entry.grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        form.grid_columnconfigure(1, weight=1)

        help_text = Text(right, wrap="word", height=14, width=60)
        help_text.pack(fill=BOTH, expand=True, pady=(10, 0))
        help_text.insert(
            "1.0",
            "Examples:\n"
            "  <ctrl>+<alt>+d\n"
            "  <ctrl>+<shift>+p\n"
            "  <ctrl>+<alt>+l\n\n"
            "Target format:\n"
            "  Category = a top-level key in Categories\n"
            "  Command = a command name inside that category\n\n"
            "Tip: use the Search UI in the main window to verify category/command names.\n",
        )
        help_text.config(state="disabled")

        button_row = Frame(outer)
        button_row.pack(fill=X, pady=(10, 0))

        Button(button_row, text="Load Selected", width=16, bg="#2f5597", fg="white", command=self.load_selected).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Save Mapping", width=16, bg="darkgreen", fg="white", command=self.save_mapping).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Delete Mapping", width=16, bg="#7f6000", fg="white", command=self.delete_mapping).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Reload Hotkeys", width=16, bg="navy", fg="white", command=self.reload_hotkeys).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Close", width=16, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.refresh()

    def refresh(self):
        self.snapshot.clear()
        self.listbox.delete(0, END)
        hotkeys = self.app.get_hotkeys_dict()
        for hotkey, target in sorted(hotkeys.items()):
            try:
                category, command = self.app._normalize_hotkey_target(target)
            except Exception:
                category, command = "<invalid>", repr(target)
            self.snapshot.append((hotkey, category, command))
            self.listbox.insert(END, f"{hotkey} -> {category} / {command}")

    def on_select(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        index = idxs[0]

        if index < 0 or index >= len(self.snapshot):
            return

        row = self.snapshot[index]

        hotkey, category, command = self.snapshot[idxs[0]]
        self.hotkey_var.set(hotkey)
        self.category_var.set(category)
        self.command_var.set(command)

    def load_selected(self):
        self.on_select()

    def save_mapping(self):
        hotkey = self.hotkey_var.get().strip()
        category = self.category_var.get().strip()
        command = self.command_var.get().strip()

        if not hotkey or not category or not command:
            self.app.show_traceback_window("Hotkey Editor", "Hotkey, category, and command are all required.")
            return

        categories = getattr(self.app.cfg, "Categories", {})
        if category not in categories:
            self.app.show_traceback_window("Hotkey Editor", f"Unknown category: {category}")
            return
        if command not in categories[category]:
            self.app.show_traceback_window("Hotkey Editor", f"Unknown command in {category}: {command}")
            return

        hotkeys = self.app.get_hotkeys_dict()
        hotkeys[hotkey] = [category, command]
        self.app.persist_hotkeys()
        self.app.initialize_hotkeys()
        self.app.set_status(f"Saved hotkey {hotkey} -> {category}/{command}")
        self.refresh()

    def delete_mapping(self):
        hotkey = self.hotkey_var.get().strip()
        if not hotkey:
            self.app.show_traceback_window("Hotkey Editor", "Enter or select a hotkey to delete.")
            return

        hotkeys = self.app.get_hotkeys_dict()
        if hotkey not in hotkeys:
            self.app.show_traceback_window("Hotkey Editor", f"Hotkey not found: {hotkey}")
            return

        del hotkeys[hotkey]
        self.app.persist_hotkeys()
        self.app.initialize_hotkeys()
        self.app.set_status(f"Deleted hotkey {hotkey}")
        self.hotkey_var.set("")
        self.category_var.set("")
        self.command_var.set("")
        self.refresh()

    def reload_hotkeys(self):
        self.app.initialize_hotkeys()
        self.app.set_status("Hotkeys reloaded from config.")
        self.refresh()

class CommandPaletteWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Command Palette")
        self.window.geometry("860x520")
        self.window.transient(app.root)
        self.window.resizable(True, True)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Command Palette",
            bd=4,
            width=28,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        search_row = Frame(outer)
        search_row.pack(fill=X, pady=(0, 8))
        Label(search_row, text="Search:", width=10, anchor="w").pack(side=LEFT)

        self.query_var = StringVar()
        self.search_entry = Entry(search_row, textvariable=self.query_var, width=48)
        self.search_entry.pack(side=LEFT, fill=X, expand=True)

        Button(search_row, text="Run", width=10, bg="darkgreen", fg="white", command=self.run_selected).pack(side=LEFT, padx=(6, 0))
        Button(search_row, text="Close", width=10, bg="red", fg="black", command=self.window.destroy).pack(side=LEFT, padx=(6, 0))

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        left.pack(side=LEFT, fill=BOTH, expand=True)

        self.listbox = Listbox(left, width=48, height=18)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.info = Text(body, wrap="word", width=52, height=18)
        self.info.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.snapshot = []
        self.filtered = []

        self.query_var.trace_add("write", self.refresh)
        self.search_entry.bind("<Return>", lambda _e: self.run_selected())
        self.search_entry.bind("<Down>", self.focus_listbox)
        self.listbox.bind("<<ListboxSelect>>", self.show_selected)
        self.listbox.bind("<Double-Button-1>", lambda _e: self.run_selected())
        self.listbox.bind("<Return>", lambda _e: self.run_selected())
        self.window.bind("<Escape>", lambda _e: self.window.destroy())
        self.window.bind("<Control-e>", self.edit_selected)
        self.window.bind("<Control-E>", self.edit_selected)
        self.listbox.bind("<Control-e>", self.edit_selected)
        self.listbox.bind("<Control-E>", self.edit_selected)
        self.window.bind("<Control-d>", self.duplicate_selected)
        self.window.bind("<Control-D>", self.duplicate_selected)
        self.listbox.bind("<Control-d>", self.duplicate_selected)
        self.listbox.bind("<Control-D>", self.duplicate_selected)
        self.window.bind("<Control-f>", self.toggle_favorite_selected)
        self.window.bind("<Control-F>", self.toggle_favorite_selected)
        self.listbox.bind("<Control-f>", self.toggle_favorite_selected)
        self.listbox.bind("<Control-F>", self.toggle_favorite_selected)
        self.window.bind("<Delete>", self.delete_selected)
        self.listbox.bind("<Delete>", self.delete_selected)
        self.window.bind("<Control-t>", self.edit_tags_selected)
        self.window.bind("<Control-T>", self.edit_tags_selected)
        self.listbox.bind("<Control-t>", self.edit_tags_selected)
        self.listbox.bind("<Control-T>", self.edit_tags_selected)
        self.window.bind("<F2>", self.rename_selected)
        self.listbox.bind("<F2>", self.rename_selected)

        self.refresh()
        self.search_entry.focus_set()


    def edit_tags_selected(self, event=None):
        item = self.selected_item()
        if not item:
            return "break"

        category = item["category"]
        name = item["name"]
        current = " ".join(self.app.get_command_tags(category, name))

        prompt = MultiFieldPrompt(
            self.window,
            "Edit Tags",
            ["tags"],
            defaults={"tags": current},
            heading=f"Tags for {category}/{name}",
        )

        values = prompt.show()
        if values is None:
            return "break"

        self.app.set_command_tags(category, name, values.get("tags", ""))
        self.refresh()
        self.app.set_status(f"Updated tags for {category}/{name}")
        return "break"

    def fuzzy_match_score(self, query: str, text: str):
        query = query.strip().lower()
        text = text.lower()

        if not query:
            return 0

        # best case: exact match
        if query == text:
            return 0

        # very good: prefix match
        if text.startswith(query):
            return 1

        # good: substring match
        idx = text.find(query)
        if idx != -1:
            return 10 + idx

        # fallback: subsequence match
        pos = -1
        gap_penalty = 0
        first_idx = None

        for ch in query:
            idx = text.find(ch, pos + 1)
            if idx == -1:
                return None
            if first_idx is None:
                first_idx = idx
            if pos != -1:
                gap_penalty += idx - pos - 1
            pos = idx

        return 100 + gap_penalty + (first_idx or 0)

    def item_match_score(self, query: str, item: dict):
        query = query.strip().lower()
        if not query:
            return 0

        terms = [term for term in query.split() if term]
        if not terms:
            return 0

        total_score = 0

        for term in terms:
            name_score = self.fuzzy_match_score(term, item["name"])
            tag_score = self.fuzzy_match_score(term, " ".join(item.get("tags", [])))
            category_score = self.fuzzy_match_score(term, item["category"])
            preview_score = self.fuzzy_match_score(term, item["preview"])

            candidates = []

            if name_score is not None:
                candidates.append(name_score)

            if tag_score is not None:
                candidates.append(500 + tag_score)

            if category_score is not None:
                candidates.append(1000 + category_score)

            if preview_score is not None:
                candidates.append(2000 + preview_score)

            if not candidates:
                return None

            total_score += min(candidates)

        return total_score

    def section_label_for_item(self, item):
        if item.get("favorite"):
            return "★ Favorites"
        if item.get("recent"):
            return "⟳ Recent"
        return "All Commands"

    def collect_commands(self):
        items = []
        categories = getattr(self.app.cfg, "Categories", {})
        favorites = set((c, s) for c, s in self.app.get_favorites())
        recent_list = self.app.get_recent()
        recent = {(c, s): i for i, (c, s) in enumerate(recent_list)}
        usage = self.app.get_usage()

        for category in sorted(categories.keys()):
            commands = categories.get(category, {})
            if not isinstance(commands, dict):
                continue

            for name in sorted(commands.keys()):
                entry = commands[name]
                tags = self.app.get_command_tags(category, name)
                tag_text = " ".join(tags)
                try:
                    cmd_type, cmd, options = self.app.parse_command_entry_public(entry)
                except Exception:
                    cmd_type, cmd, options = "?", repr(entry), {}

                preview = cmd if isinstance(cmd, str) else str(cmd)
                is_favorite = (category, name) in favorites
                is_recent = (category, name) in recent
                recent_rank = recent.get((category, name), 999)
                usage_count = int(usage.get(f"{category}/{name}", 0))

                items.append({
                    "category": category,
                    "name": name,
                    "entry": entry,
                    "type": cmd_type,
                    "preview": preview,
                    "options": options,
                    "favorite": is_favorite,
                    "recent": is_recent,
                    "recent_rank": recent_rank,
                    "usage_count": usage_count,
                    "search_blob": f"{category} {name} {preview}".lower(),
                    "tags": tags,
                })

        items.sort(
            key=lambda item: (
                not item["favorite"],
                not item["recent"],
                item["recent_rank"],
                -item["usage_count"],
                item["category"].lower(),
                item["name"].lower(),
            )
        )
        return items

    def refresh(self, *_args):
        query = self.query_var.get().strip().lower()
        self.snapshot = self.collect_commands()

        if query:
            scored = []
            for item in self.snapshot:
                score = self.item_match_score(query, item)
                if score is not None:
                    enriched = dict(item)
                    enriched["match_score"] = score
                    scored.append(enriched)

            scored.sort(
                key=lambda item: (
                    not item.get("favorite", False),
                    not item.get("recent", False),
                    item.get("match_score", 999),
                    item.get("recent_rank", 999),
                    item.get("usage_count", 0),
                    item.get("category", "").lower(),
                    item.get("name", "").lower(),
                )
            )
            self.filtered = scored
        else:
            self.filtered = list(self.snapshot)

        self.listbox.delete(0, END)
        self.list_rows = []

        def add_spacer():
            self.listbox.insert(END, "")
            self.list_rows.append(None)

        def add_header(title: str):
            if self.listbox.size() > 0:
                add_spacer()

            self.listbox.insert(END, title)
            header_index = self.listbox.size() - 1
            self.listbox.itemconfig(header_index, fg="blue", bg="#eeeeee")
            self.list_rows.append(None)

        def add_command(item: dict):
            if item.get("favorite"):
                prefix = "★ "
            elif item.get("recent"):
                prefix = "⟳ "
            else:
                prefix = "  "

            usage = item.get("usage_count", 0)

            if item.get("favorite"):
                suffix = ""
            else:
                suffix = f"  ({usage})" if usage > 0 else ""

            self.listbox.insert(END, f'{prefix}{item["category"]} -> {item["name"]}{suffix}')
            self.list_rows.append(item)

        favorites = [i for i in self.filtered if i.get("favorite")]

        recents = [
            i for i in self.filtered
            if i.get("recent")
            and not i.get("favorite")
            and i.get("usage_count", 0) == 0
        ]

        most_used = sorted(
            [
                i for i in self.filtered
                if i.get("usage_count", 0) > 0
                and not i.get("favorite")
            ],
            key=lambda x: -x.get("usage_count", 0)
        )

        all_items = [
            i for i in self.filtered
            if not i.get("favorite")
            and not i.get("recent")
            and i.get("usage_count", 0) == 0
        ]

        if favorites:
            add_header("★ Favorites")
            for item in favorites:
                add_command(item)

        if recents:
            add_header("⟳ Recent")
            for item in recents:
                add_command(item)

        if most_used:
            add_header("🔥 Most Used")
            for item in most_used[:10]:
                add_command(item)

        if all_items:
            add_header("All Commands")
            for item in all_items:
                add_command(item)

        self.info.delete("1.0", END)

        if not any(row is not None for row in self.list_rows):
            self.info.insert("1.0", "No matching commands found.\n")
            return

        self.select_first_command_row()

    def select_first_command_row(self):
        self.listbox.selection_clear(0, END)

        for index in range(self.listbox.size()):
            if index in getattr(self, "list_index_to_item", {}):
                self.listbox.selection_set(index)
                self.listbox.activate(index)
                self.show_selected()
                return

    def selected_item(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None

        index = idxs[0]

        if not hasattr(self, "list_rows"):
            return None

        if index < 0 or index >= len(self.list_rows):
            return None

        return self.list_rows[index]

    def focus_listbox(self, _event=None):
        if self.listbox.size() > 0:
            self.listbox.focus_set()
            self.select_first_command_row()
        return "break"

    def show_selected(self, _event=None):
        item = self.selected_item()
        self.info.delete("1.0", END)
        if not item:
            return
        lines = [
            f'Category: {item["category"]}',
            f'Command: {item["name"]}',
            f'Type: {item["type"]}',
            "",
            "Preview:",
            item["preview"],
            "",
            "Shortcuts:",
            "  Enter      -> Run command",
            "  Ctrl+E     -> Edit command",
            "  Ctrl+D     -> Duplicate command",
            "  Ctrl+F     -> Toggle favorite",
            "  F2         -> Rename command",
            "  Delete     -> Delete command",
            "  Escape     -> Close palette",
        ]
        self.info.insert("1.0", "\n".join(lines))

    def toggle_favorite_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        category = item["category"]
        name = item["name"]

        if item.get("favorite"):
            self.app.remove_favorite(category, name)
            self.app.set_status(f"Removed favorite {category}/{name}")
        else:
            self.app.add_favorite(category, name)
            self.app.set_status(f"Added favorite {category}/{name}")

        self.app.rebuild_favorites_bar()
        self.refresh()

        return "break"

    def run_selected(self):
        item = self.selected_item()
        if not item:
            return
        self.window.destroy()
        self.app.set_status(f'Palette run: {item["category"]}/{item["name"]}')
        self.app.select_cmd(None, item["category"], item["name"])

    def edit_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        self.window.destroy()

        editor = CommandEditorWindow(self.app)
        editor.load_command(item["category"], item["name"])

        return "break"

    def duplicate_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        self.app.duplicate_command(
            item["category"],
            item["name"]
        )

        self.refresh()
        self.app.set_status(
            f'Duplicated {item["category"]}/{item["name"]}'
        )

        return "break"

    def delete_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        category = item["category"]
        name = item["name"]

        if not messagebox.askokcancel(
            "Delete Command",
            f"Delete command '{category}/{name}'?"
        ):
            return "break"

        self.app.delete_command(category, name)
        self.refresh()
        self.app.set_status(f"Deleted command {category}/{name}")

        return "break"

    def rename_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        category = item["category"]
        old_name = item["name"]

        prompt = MultiFieldPrompt(
            self.window,
            "Rename Command",
            ["new_name"],
            defaults={"new_name": old_name},
            heading=f"Rename {category}/{old_name}",
        )

        values = prompt.show()
        if values is None:
            return "break"

        new_name = values.get("new_name", "").strip()
        if not new_name:
            self.app.show_traceback_window("Rename Command", "New command name is required.")
            return "break"

        self.app.rename_command(category, old_name, new_name)
        self.refresh()
        self.app.set_status(f"Renamed command {category}/{old_name} -> {new_name}")

        return "break"

