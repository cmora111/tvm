import pprint
from tkinter import *
from tkinter import messagebox
from tkinter import ttk

class SharedVariableManagerWindow:
    def __init__(self, app):
        self.app = app

        self.window = Toplevel(app.root)
        self.window.title("Shared Variable Manager")
        self.window.geometry("1500x800")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(outer, text="Shared Variable Manager", bd=4, width=38, bg="lightgreen", fg="black", relief="raised",).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))

        Button(action_row, text="Save", width=14, bg="darkgreen", fg="white", command=self.save_variable,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Delete", width=14, bg="#7f6000", fg="white", command=self.delete_variable,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Refresh", width=14, bg="navy", fg="white", command=self.refresh,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=14, bg="red", fg="black", command=self.window.destroy,).pack(side=RIGHT)

        body = PanedWindow(
            outer,
            orient=HORIZONTAL,
            sashrelief=RAISED,
            sashwidth=6,
        )
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        right = Frame(body)

        body.add(left, minsize=320)
        body.add(right, minsize=900)

        self.window.update_idletasks()

        self.tree = ttk.Treeview(
            left,
            columns=("value", "resolved", "status"),
            show="tree headings",
            height=24,
        )

        self.tree.heading("#0", text="Name")
        self.tree.heading("value", text="Value")
        self.tree.heading("resolved", text="Resolved")
        self.tree.heading("status", text="Status")

        self.tree.column("#0", width=150, stretch=True)
        self.tree.column("value", width=180, stretch=True)
        self.tree.column("resolved", width=180, stretch=True)
        self.tree.column("status", width=70, stretch=False)

        self.tree.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = Scrollbar(left, command=self.tree.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.tree.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        row = 0

        Label(form, text="Name:", width=12, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.name_var = StringVar()
        Entry(form, textvariable=self.name_var, width=48).grid(row=row, column=1, sticky="ew", pady=3)
        row+=1

        Label(form, text="Value:", width=12, anchor="nw").grid(row=row, column=0, sticky="nw", pady=3)
        self.value_text = Text(form, height=8, width=58, wrap="word")
        self.value_text.grid(row=row, column=1, sticky="nsew", pady=3)
        row+=1

        self.resolved_var = StringVar()
        self.test_var = StringVar()
        self.test_result_var = StringVar()

        Label(form, text="Resolved:", width=14, anchor="nw").grid(row=row, column=0, sticky="nw", pady=3)

        self.resolved_text = Text(form, height=3, width=60, wrap="none")
        self.resolved_text.grid(row=row, column=1, sticky="ew", pady=3)

        self.resolved_text.config(state="disabled")

        row += 1

        Label(form, text="Test:", width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        Entry(form, textvariable=self.test_var, width=60).grid(row=row, column=1, sticky="ew", pady=3)

        Button(form, text="Test", width=12, command=self.test_expansion,).grid(row=row, column=2, padx=(6, 0), pady=3)
        row += 1

        Label(form, text="Result:", width=14, anchor="nw").grid(row=row, column=0, sticky="nw", pady=3)

        self.test_result_text = Text(form, height=3, width=60, wrap="none")
        self.test_result_text.grid(row=row, column=1, sticky="ew", pady=3)

        self.test_result_text.config(state="disabled")

        row += 1

        form.columnconfigure(1, weight=1)

        self.value_text.bind("<KeyRelease>", lambda _event: self.update_resolved_preview(),)

        self.info = Text(right, wrap="word", height=12)
        self.info.pack(fill=BOTH, expand=True, pady=(10, 0))

        self.snapshot = []
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        self.refresh()

    def refresh(self):
        variables = self.app.get_shared_variables()

        self.snapshot = []

        self.tree.delete(*self.tree.get_children())

        for name in sorted(variables.keys()):
            value = str(variables.get(name, ""))

            if "${prompt:" in value:
                resolved = "<prompt>"
                status = "prompt"
            else:
                try:
                    resolved = self.app.resolve_text_variables(value)
                    status = "ok" if "${" not in resolved else "unresolved"
                except Exception as exc:
                    resolved = str(exc)
                    status = "error"

                self.tree.insert(
                    "",
                    END,
                    iid=name,
                    text=name,
                    values=(value, resolved, status),
                )

        self.info.delete("1.0", END)
        self.info.insert(
            "1.0",
            "Shared variables are persistent and reusable in commands.\n\n"
            "Use syntax:\n"
            "  ${name}\n\n"
            "Example:\n"
            "  project_dir = /home/mora/termforge\n\n"
            "Command:\n"
            "  cd ${project_dir} && pwd\n"
        )

    def get_value_text(self):
        return self.value_text.get("1.0", "end-1c")


    def set_value_text(self, value):
        self.value_text.delete("1.0", END)
        self.value_text.insert("1.0", str(value))

    def set_resolved_text(self, value):
        self.resolved_text.config(state="normal")
        self.resolved_text.delete("1.0", END)
        self.resolved_text.insert("1.0", str(value))
        self.resolved_text.config(state="disabled")


    def set_test_result_text(self, value):
        self.test_result_text.config(state="normal")
        self.test_result_text.delete("1.0", END)
        self.test_result_text.insert("1.0", str(value))
        self.test_result_text.config(state="disabled")

    def update_resolved_preview(self, *_args):
        value = self.get_value_text()

        if "${prompt:" in value:
            self.set_resolved_text(
                "<prompt — click Test to enter a value>"
            )
            return

        try:
            resolved = self.app.resolve_text_variables(value)
            self.set_resolved_text(resolved)
        except Exception as exc:
            self.set_resolved_text(f"[error] {exc}")

    def set_resolved_text(self, value):
        self.resolved_text.config(state="normal")
        self.resolved_text.delete("1.0", END)
        self.resolved_text.insert("1.0", str(value))
        self.resolved_text.config(state="disabled")

    def test_expansion(self):
        self.app.variable_prompt_cache = {}

        text = self.test_var.get().strip()

        if not text:
            self.set_test_result_text("")
            return

        try:
            result = self.app.resolve_text_variables(text)
        except Exception as exc:
            result = f"[error] {exc}"

        self.set_test_result_text(result)

    def selected_item(self):
        selected = self.tree.selection()

        if not selected:
            return None

        return selected[0]

    def save_variable(self):
        name = self.name_var.get().strip()
        value = self.get_value_text().strip()

        if not name:
            messagebox.showerror(
                "Shared Variable",
                "Variable name is required.",
                parent=self.window,
            )
            return

        try:
            self.app.set_shared_variable(name, value)

            self.refresh()

            if self.tree.exists(name):
                self.tree.selection_set(name)
                self.tree.focus(name)
                self.tree.see(name)

            if "${prompt:" in value:
                self.set_resolved_text(
                    "<prompt — use Test to supply a value>"
                )
            else:
                self.set_resolved_text(
                    self.app.resolve_text_variables(value)
                )

            self.app.set_status(f"Saved shared variable: {name}")

        except Exception as exc:
            self.app.show_traceback_window(
                "Save Shared Variable Failed",
                exc,
            )

    def delete_variable(self):
        name = self.selected_item()
        if not name:
            return

        if not messagebox.askokcancel(
            "Delete Shared Variable",
            f"Delete shared variable '{name}'?",
        ):
            return

        self.app.delete_shared_variable(name)

        self.name_var.set("")
        self.set_value_text("")
        self.set_resolved_text("")
        self.set_test_result_text("")

        self.refresh()

    def on_select(self, _event=None):
        name = self.selected_item()
        if not name:
            return

        variables = getattr(self.app.cfg, "SharedVariables", {})
        if not isinstance(variables, dict):
            variables = {}

        value = variables.get(name, "")

        self.name_var.set(name)
        self.set_value_text(value)
        self.update_resolved_preview()        
