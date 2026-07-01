import json
import pprint
from tkinter import *
from tkinter import filedialog, messagebox, simpledialog
from .chain_builder import ChainBuilderWindow
from ..utils.parsing import (
    parse_command_entry,
)


class CategoryEditorWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Category Editor")
        self.window.geometry("860x520")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Category Editor",
            bd=4,
            width=30,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))
        Button(action_row, text="Create Category", width=16, bg="darkgreen", fg="white", command=self.create_category).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Rename Category", width=16, bg="#2f5597", fg="white", command=self.rename_category).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Delete Category", width=16, bg="#7f6000", fg="white", command=self.delete_category).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Refresh", width=16, bg="navy", fg="white", command=self.refresh).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=16, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        left.pack(side=LEFT, fill=Y)

        right = Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=38, height=22)
        self.listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.info = Text(right, wrap="word", width=60, height=22)
        self.info.pack(fill=BOTH, expand=True)

        self.listbox.bind("<<ListboxSelect>>", self.show_selected)
        self.refresh()

    def get_categories(self):
        categories = getattr(self.app.cfg, "Categories", {})
        if not isinstance(categories, dict):
            categories = {}
            setattr(self.app.cfg, "Categories", categories)
        return categories

    def refresh(self):
        self.listbox.delete(0, END)
        categories = self.get_categories()
        self.snapshot = []
        for name in sorted(categories.keys()):
            commands = categories.get(name, {})
            count = len(commands) if isinstance(commands, dict) else 0
            self.snapshot.append((name, count))
            self.listbox.insert(END, f"{name} ({count} command{'s' if count != 1 else ''})")
        self.info.delete("1.0", END)
        self.info.insert("1.0", "Select a category to inspect.\n")

    def selected_item(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None

        index = idxs[0]

        if index < 0 or index >= len(self.snapshot):
            return None

        return self.snapshot[index]

    def show_selected(self, _event=None):
        item = self.selected_item()

        self.info.delete("1.0", END)

        if not item:
            return

        name, count = item
        categories = self.get_categories()
        commands = categories.get(name, {})

        lines = [
            f"Category: {name}",
            f"Commands: {count}",
            "",
            "Command names:",
        ]

        if isinstance(commands, dict):
            for command_name in sorted(commands.keys()):
                lines.append(f"  - {command_name}")
        else:
            lines.append("  Invalid command dictionary.")

        self.info.insert("1.0", "\n".join(lines))

    def selected_category_name(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None
        return self.snapshot[idxs[0]][0]

    def create_category(self):
        name = simpledialog.askstring(
            "Create Category",
            "Category name:",
            parent=self.window,
        )

        if not name:
            return

        name = name.strip()

        if not name:
            return

        categories = self.get_categories()

        if name in categories:
            messagebox.showerror(
                "Create Category",
                f"Category already exists:\n\n{name}",
            )
            return

        categories[name] = {}
        self.app.persist_full_config()
        self.refresh()

    def rename_category(self):
        item = self.selected_item()

        if not item:
            messagebox.showerror(
                "Rename Category",
                "Select a category first.",
            )
            return

        old_name, _count = item

        new_name = simpledialog.askstring(
            "Rename Category",
            f"Rename category:\n\n{old_name}\n\nto:",
            initialvalue=old_name,
            parent=self.window,
        )

        if not new_name:
            return

        new_name = new_name.strip()

        if not new_name:
            return

        categories = self.get_categories()

        if new_name != old_name and new_name in categories:
            messagebox.showerror(
                "Rename Category",
                f"Category already exists:\n\n{new_name}",
            )
            return

        categories[new_name] = categories.pop(old_name)

        self.app.persist_full_config()
        self.refresh()

    def delete_category(self):
        item = self.selected_item()

        if not item:
            messagebox.showerror(
                "Delete Category",
                "Select a category first.",
            )
            return

        name, count = item

        if not messagebox.askokcancel(
            "Delete Category",
            f"Delete category?\n\n{name}\n\n"
            f"This contains {count} command(s).",
        ):
            return

        categories = self.get_categories()
        categories.pop(name, None)

        self.app.persist_full_config()
        self.refresh()

class CommandEditorWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Command / Chain Editor")
        self.window.geometry("1040x700")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Command / Chain Editor",
            bd=4,
            width=34,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))
        Button(action_row, text="Save Entry", width=16, bg="darkgreen", fg="white", command=self.save_entry).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Delete Entry", width=16, bg="#7f6000", fg="white", command=self.delete_entry).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="New / Clear", width=16, bg="#555555", fg="white", command=self.clear_form).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Refresh List", width=16, bg="navy", fg="white", command=self.refresh).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=16, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        top = Frame(outer)
        top.pack(fill=BOTH, expand=True)

        left = Frame(top)
        left.pack(side=LEFT, fill=Y)

        right = Frame(top)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=42, height=26)
        self.listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        row = 0

        Label(form, text="Category:", width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.category_var = StringVar()
        Entry(form, textvariable=self.category_var, width=42).grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        Label(form, text="Command Name:", width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.name_var = StringVar()
        Entry(form, textvariable=self.name_var, width=42).grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        Label(form, text="Type:", width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.type_var = StringVar(value="2")
        self.type_entry = Entry(form, textvariable=self.type_var, width=42)
        self.type_entry.grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        self.command_label = Label(form, text="Command:", width=14, anchor="nw")
        self.command_label.grid(row=row, column=0, sticky="nw", pady=3)
        self.command_text = Text(form, height=14, width=70, wrap="word")
        self.command_text.grid(row=row, column=1, sticky="nsew", pady=3)
        row += 1

        builder_row = Frame(form)
        builder_row.grid(row=row, column=1, sticky="w", pady=(0, 6))
        self.builder_button = Button(builder_row, text="Visual Chain Builder", bg="#2f5597", fg="white", command=self.open_chain_builder)
        self.builder_button.pack(side=LEFT)
        self.chain_hint = Label(builder_row, text="Use this for type = chain", fg="#333333")
        self.chain_hint.pack(side=LEFT, padx=(8, 0))
        row += 1

        Label(form, text="Options JSON:", width=14, anchor="nw").grid(row=row, column=0, sticky="nw", pady=3)
        self.options_text = Text(form, height=5, width=70, wrap="word")
        self.options_text.grid(row=row, column=1, sticky="nsew", pady=3)
        row += 1

        form.grid_columnconfigure(1, weight=1)

        help_box = Text(right, height=11, wrap="word")
        help_box.pack(fill=BOTH, expand=True, pady=(10, 0))
        help_box.insert(
            "1.0",
            "Simple command:\n"
            "  Type: 2\n"
            "  Command: pwd\n\n"
            "Detached command:\n"
            "  Type: 3\n"
            "  Command: code > /dev/null 2>&1 &\n\n"
            "Chain:\n"
            "  Type: chain\n"
            "  Use the Visual Chain Builder button\n\n"
            "Options JSON example:\n"
            "  {\"confirm\": true}\n"
        )
        help_box.config(state="disabled")

        self.type_choices = {
            "Select Window": "0",
            "Spawn Terminal": "1",
            "Send To Window": "2",
            "Detached Command": "3",
            "Chain": "chain",
            "Plugin": "plugin",
        }

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.type_var.trace_add("write", self.update_type_ui)
        self.refresh()
        self.clear_form()

    def update_type_ui(self, *_args):
        cmd_type_raw = self.type_var.get().strip().lower()
        if cmd_type_raw == "chain":
            self.command_label.config(text="Chain JSON:")
            self.builder_button.config(state="normal")
            self.chain_hint.config(text="Build visually or edit JSON directly")
        else:
            self.command_label.config(text="Command:")
            self.builder_button.config(state="disabled")
            self.chain_hint.config(text="Plain text command for normal entries")

    def open_chain_builder(self):
        current = self.command_text.get("1.0", END).strip()
        initial = []

        if current:
            if current.startswith("["):
                try:
                    initial = json.loads(current)
                except Exception as exc:
                    self.app.show_traceback_window(
                        "Chain Builder: Could not parse current chain JSON",
                        exc,
                    )
                    return
            else:
                initial = []

        builder = ChainBuilderWindow(
            self.window,
            self.app,
            initial_steps=initial,
        )

        result = builder.show()

        if result is not None:
            self.command_text.delete("1.0", END)
            self.command_text.insert(
                "1.0",
                json.dumps(result, indent=2),
            )

    def refresh(self):
        self.snapshot.clear()
        self.listbox.delete(0, END)
        categories = getattr(self.app.cfg, "Categories", {})
        for category in sorted(categories.keys()):
            commands = categories.get(category, {})
            if not isinstance(commands, dict):
                continue
            for name in sorted(commands.keys()):
                entry = commands[name]
                self.snapshot.append((category, name, entry))
                self.listbox.insert(END, f"{category} -> {name}")

    def on_select(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        category, name, entry = self.snapshot[idxs[0]]
        self.category_var.set(category)
        self.name_var.set(name)
        cmd_type, cmd, options = self.app.parse_command_entry_public(entry)
        self.type_var.set(str(cmd_type))
        self.command_text.delete("1.0", END)
        if isinstance(cmd, str):
            self.command_text.insert("1.0", cmd)
        else:
            self.command_text.insert("1.0", json.dumps(cmd, indent=2))
        self.options_text.delete("1.0", END)
        self.options_text.insert("1.0", json.dumps(options, indent=2) if options else "{}")
        self.update_type_ui()

    def clear_form(self):
        try:
            self.backend_var.set("")
            self.tmux_session_var.set(str(getattr(self.app.cfg, "TmuxSession", "termforge")))
            self.tmux_pane_var.set(str(getattr(self.app.cfg, "TmuxPane", "")))
            self.tmux_mode_var.set(str(getattr(self.app.cfg, "TmuxMode", "pane")))

            if hasattr(self, "category_choices") and self.category_choices:
                self.category_var.set(self.category_choices[0])
            else:
                self.category_var.set("")

            self.name_var.set("")

            if hasattr(self, "type_var"):
                self.type_var.set("Send To Window")

            if hasattr(self, "command_text") and self.command_text.winfo_exists():
                self.command_text.delete("1.0", END)

            if hasattr(self, "options_text") and self.options_text.winfo_exists():
                self.options_text.delete("1.0", END)
                self.options_text.insert("1.0", "{}")

            self.update_type_ui()
        except Exception:
            pass

    def _parse_form(self):
        category = self.category_var.get().strip()
        name = self.name_var.get().strip()
        cmd_type_raw = self.type_choices.get(self.type_var.get(), self.type_var.get()).strip()
        command_raw = self.command_text.get("1.0", END).strip()
        options_raw = self.options_text.get("1.0", END).strip() or "{}"

        if not category or not name or not cmd_type_raw:
            raise ValueError("Category, command name, and type are required.")

        if cmd_type_raw.lower() == "chain":
            cmd_type = "chain"
            command = json.loads(command_raw) if command_raw else []
            if not isinstance(command, list):
                raise ValueError("Chain JSON must decode to a list.")
        elif cmd_type_raw.lower() == "plugin":
            cmd_type = "plugin"
            command = command_raw
        else:
            try:
                cmd_type = int(cmd_type_raw)
            except ValueError:
                cmd_type = cmd_type_raw
            command = command_raw

        options = json.loads(options_raw) if options_raw else {}
        if not isinstance(options, dict):
            raise ValueError("Options JSON must decode to an object/dict.")
        return category, name, [cmd_type, command, options]

    def save_entry(self):
        try:
            category, name, entry = self._parse_form()
        except Exception as exc:
            self.app.show_traceback_window("Command Editor", str(exc))
            return

        categories = getattr(self.app.cfg, "Categories", None)
        if categories is None or not isinstance(categories, dict):
            categories = {}
            setattr(self.app.cfg, "Categories", categories)

        if category not in categories or not isinstance(categories.get(category), dict):
            categories[category] = {}

        categories[category][name] = entry
        self.app.persist_categories()
        self.app.rebuild_category_buttons()
        self.app.set_status(f"Saved command {category}/{name}")

        try:
            if self.window.winfo_exists():
                if hasattr(self, "listbox") and self.listbox.winfo_exists():
                    self.refresh()
        except Exception:
            pass

    def delete_entry(self):
        category = self.category_var.get().strip()
        name = self.name_var.get().strip()
        categories = getattr(self.app.cfg, "Categories", {})

        if category not in categories or name not in categories[category]:
            self.app.show_traceback_window("Command Editor", "Selected command was not found.")
            return

        del categories[category][name]
        if not categories[category]:
            del categories[category]

        self.app.persist_categories()
        self.app.rebuild_category_buttons()
        self.app.set_status(f"Deleted command {category}/{name}")

        try:
            if self.window.winfo_exists():
                if hasattr(self, "listbox") and self.listbox.winfo_exists():
                    self.refresh()
        except Exception:
            pass

    def load_command(self, category: str, name: str) -> None:
        categories = getattr(self.app.cfg, "Categories", {})

        if category not in categories or name not in categories[category]:
            self.app.show_traceback_window(
                "Command Editor",
                f"Command not found: {category}/{name}"
            )
            return

        entry = categories[category][name]

        self.category_var.set(category)
        self.name_var.set(name)

        cmd_type, cmd, options = self.app.parse_command_entry_public(entry)

        reverse_type_choices = {v: k for k, v in self.type_choices.items()}
        self.type_var.set(reverse_type_choices.get(str(cmd_type), "Send To Window"))

        self.command_text.delete("1.0", END)
        if isinstance(cmd, str):
            self.command_text.insert("1.0", cmd)
        else:
            self.command_text.insert("1.0", json.dumps(cmd, indent=2))

        self.options_text.delete("1.0", END)
        self.options_text.insert("1.0", json.dumps(options, indent=2) if options else "{}")

        self.update_type_ui()



