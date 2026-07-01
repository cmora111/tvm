import json
import pprint
from tkinter import *
from tkinter import messagebox, simpledialog

class VariableManagerWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Variable Manager")
        self.window.geometry("860x520")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(outer, text="Variable Manager", bd=4, width=32, bg="lightgreen", fg="black", relief="raised",).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))

        Button(action_row, text="Save", width=14, bg="darkgreen", fg="white", command=self.save_variable).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Delete", width=14, bg="#7f6000", fg="white", command=self.delete_variable).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Refresh", width=14, bg="navy", fg="white", command=self.refresh).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=14, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        left.pack(side=LEFT, fill=BOTH, expand=True)

        right = Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=40, height=22, exportselection=False)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        row = 0

        Label(form, text="Name:", width=12, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.name_var = StringVar()
        Entry(form, textvariable=self.name_var, width=50).grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        Label(form, text="Value:", width=12, anchor="nw").grid(row=row, column=0, sticky="nw", pady=3)
        self.value_text = Text(form, height=5, width=60, wrap="word")
        self.value_text.grid(row=row, column=1, sticky="nsew", pady=3)
        row += 1

        form.columnconfigure(1, weight=1)

        self.preview = Text(right, wrap="word", height=12)
        self.preview.pack(fill=BOTH, expand=True, pady=(10, 0))

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.refresh()

    def refresh(self):
        variables = self.app.get_variables()
        self.snapshot = []

        self.listbox.delete(0, END)

        for name in sorted(variables.keys()):
            value = variables.get(name, "")
            self.snapshot.append((name, value))
            self.listbox.insert(END, f"${{{name}}} = {value}")

        self.preview.delete("1.0", END)
        self.preview.insert(
            "1.0",
            "Use variables in commands, chains, and schedules:\n\n"
            "  cd ${repo}\n"
            "  ssh ${server}\n"
            "  source ${venv}/bin/activate\n"
        )

    def selected_name(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None
        return self.snapshot[idxs[0]][0]

    def on_select(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return

        name, value = self.snapshot[idxs[0]]

        self.name_var.set(name)
        self.value_text.delete("1.0", END)
        self.value_text.insert("1.0", str(value))

        self.preview.delete("1.0", END)
        self.preview.insert(
            "1.0",
            f"Selected variable:\n\n"
            f"Name: {name}\n"
            f"Use as: ${{{name}}}\n\n"
            f"Value:\n{value}"
        )

    def save_variable(self):
        name = self.name_var.get().strip()
        value = self.value_text.get("1.0", END).strip()

        try:
            self.app.set_variable(name, value)
        except Exception as exc:
            self.app.show_traceback_window("Save Variable Failed", exc)
            return

        self.app.set_status(f"Saved variable: {name}")
        self.refresh()

    def delete_variable(self):
        name = self.name_var.get().strip() or self.selected_name()

        if not name:
            messagebox.showerror("Variable Manager", "Select or enter a variable first.")
            return

        if not messagebox.askokcancel("Delete Variable", f"Delete variable '{name}'?"):
            return

        try:
            self.app.set_variable(name, "")
        except Exception as exc:
            self.app.show_traceback_window("Delete Variable Failed", exc)
            return

        self.name_var.set("")
        self.value_text.delete("1.0", END)
        self.app.set_status(f"Deleted variable: {name}")
        self.refresh()

class EnvironmentTemplateWindow:
    def __init__(self, app):
        self.app = app

        self.window = Toplevel(app.root)
        self.window.title("Environment Templates")
        self.window.geometry("980x620")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8,)
        outer.pack(fill=BOTH, expand=True)

        Label(outer, text="Environment Templates", bd=4, width=36, bg="lightgreen", fg="black", relief="raised",).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))

        Button(action_row, text="Save", width=14, bg="darkgreen", fg="white", command=self.save_template,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Delete", width=14, bg="#7f6000", fg="white", command=self.delete_template,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Activate", width=14, bg="#2f5597", fg="white", command=self.activate_template,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Refresh", width=14, bg="navy", fg="white", command=self.refresh,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=14, bg="red", fg="black", command=self.window.destroy,).pack(side=RIGHT)

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        row = 0

        left = Frame(body)
        left.grid(row=row, column=0, sticky="nsew",)

        right = Frame(body)
        right.grid(row=row, column=1, sticky="nsew", padx=(10, 0),)
        row += 1

        self.listbox = Listbox(left, width=42, height=24, exportselection=False,)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True,)

        scrollbar = Scrollbar(left, command=self.listbox.yview,)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.listbox.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        row = 0

        Label(form, text="Template Name:", width=16, anchor="w",).grid(row=row, column=0, sticky="w", pady=3,)
        self.name_var = StringVar()
        Entry(form, textvariable=self.name_var, width=42,).grid(row=row, column=1, sticky="ew", pady=3,)
        row += 1

        Label(form, text="Variables JSON:", width=16, anchor="nw",).grid(row=row, column=0, sticky="nw", pady=3,)
        self.variables_text = Text(form, height=14, width=60, wrap="word",)
        self.variables_text.grid(row=row, column=1, sticky="nsew", pady=3,)
        row += 1

        form.columnconfigure(1, weight=1)

        self.preview = Text(right, wrap="word", height=12,)
        self.preview.pack(fill=BOTH, expand=True, pady=(10, 0),)

        self.snapshot = []

        self.listbox.bind("<<ListboxSelect>>", self.on_select,)

        self.refresh()

    def refresh(self):
        templates = self.app.get_environment_templates()

        self.snapshot = []

        self.listbox.delete(0, END)

        current = self.app.get_current_environment()

        for name in sorted(templates.keys()):
            vars_dict = templates.get(name, {})

            prefix = "▶ " if name == current else ""

            self.snapshot.append(
                (name, vars_dict)
            )

            self.listbox.insert(
                END,
                f"{prefix}{name} "
                f"({len(vars_dict)} vars)"
            )

        self.preview.delete("1.0", END)

        self.preview.insert(
            "1.0",
            "Environment templates allow reusable "
            "sets of variables.\n\n"
            "Example:\n\n"
            "{\n"
            '    "repo": "/home/mora/project",\n'
            '    "venv": "/home/mora/project/.venv"\n'
            "}\n\n"
            "Use in commands:\n"
            "  cd ${repo}\n"
            "  source ${venv}/bin/activate"
        )

    def on_select(self, _event=None):
        idxs = self.listbox.curselection()

        if not idxs:
            return

        name, variables = self.snapshot[idxs[0]]

        self.name_var.set(name)

        self.variables_text.delete(
            "1.0",
            END,
        )

        self.variables_text.insert(
            "1.0",
            json.dumps(
                variables,
                indent=4,
            ),
        )

        self.preview.delete("1.0", END)

        self.preview.insert(
            "1.0",
            pprint.pformat(
                variables,
                indent=4,
            ),
        )

    def save_template(self):
        name = self.name_var.get().strip()

        if not name:
            messagebox.showerror(
                "Environment Templates",
                "Template name is required.",
            )
            return

        raw = self.variables_text.get(
            "1.0",
            END,
        ).strip()

        try:
            variables = json.loads(raw) if raw else {}
        except Exception as exc:
            messagebox.showerror(
                "Environment Templates",
                f"Invalid JSON:\n\n{exc}",
            )
            return

        try:
            self.app.set_environment_template(
                name,
                variables,
            )
        except Exception as exc:
            self.app.show_traceback_window(
                "Save Environment Template Failed",
                exc,
            )
            return

        self.app.set_status(
            f"Saved environment template: {name}"
        )

        self.refresh()

    def delete_template(self):
        idxs = self.listbox.curselection()

        if not idxs:
            messagebox.showerror(
                "Environment Templates",
                "Select a template first.",
            )
            return

        name, _variables = self.snapshot[idxs[0]]

        if not messagebox.askokcancel(
            "Delete Template",
            f"Delete environment template '{name}'?",
        ):
            return

        self.app.delete_environment_template(name)

        self.refresh()

    def activate_template(self):
        idxs = self.listbox.curselection()

        if not idxs:
            messagebox.showerror(
                "Environment Templates",
                "Select a template first.",
            )
            return

        name, _variables = self.snapshot[idxs[0]]

        try:
            self.app.set_current_environment(name)
        except Exception as exc:
            self.app.show_traceback_window(
                "Activate Environment Failed",
                exc,
            )
            return

        self.refresh()

