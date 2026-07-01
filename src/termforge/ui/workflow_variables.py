import json
import pprint
from datetime import datetime
from pathlib import Path
from tkinter import *
from tkinter import filedialog, messagebox


class WorkflowVariablesWindow:
    def __init__(self, app):
        self.app = app

        self.window = Toplevel(app.root)
        self.window.title("Workflow Variables")
        self.window.geometry("1000x760")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(outer, text="Workflow Variables", bd=4, width=34, bg="lightgreen", fg="black", relief="raised",).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))

        Button(action_row, text="Refresh", width=14, bg="navy", fg="white", command=self.refresh).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Promote Shared", width=16, bg="#3d6d3d", fg="white", command=self.promote_selected).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Delete Selected", width=16, bg="#7f6000", fg="white", command=self.delete_selected).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Copy", width=14, bg="#2f5597", fg="white", command=self.copy_all).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Export", width=14, bg="#5b4b8a", fg="white", command=self.export).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Clear Runtime", width=14, bg="#7f6000", fg="white", command=self.clear_runtime).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=14, bg="red", fg="black", command=self.window.destroy,).pack(side=LEFT, padx=(0, 6))

        body = PanedWindow(outer, orient=HORIZONTAL, sashrelief=RAISED, sashwidth=6,)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        right = Frame(body)

        body.add(left, minsize=360)
        body.add(right, minsize=420)

        Label(left, text="Variables", bg="#dddddd", relief="raised").pack(fill=X)

        list_frame = Frame(left)
        list_frame.pack(fill=BOTH, expand=True)

        self.listbox = Listbox(list_frame, width=48, exportselection=False,)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)

        scroll = Scrollbar(list_frame, command=self.listbox.yview)
        scroll.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scroll.set)

        Label(right, text="Details", bg="#dddddd", relief="raised").pack(fill=X)

        details_frame = Frame(right)
        details_frame.pack(fill=BOTH, expand=True)

        details_frame.columnconfigure(0, weight=1)
        details_frame.columnconfigure(1, weight=0)
        details_frame.rowconfigure(0, weight=1)

        row = 0

        self.details = Text(details_frame, wrap="none")
        self.details.grid(row=row, column=0, sticky="nsew")

        details_scroll = Scrollbar(details_frame, orient=VERTICAL, command=self.details.yview)
        details_scroll.grid(row=row, column=1, sticky="ns")
        self.details.config(yscrollcommand=details_scroll.set)
        row += 1

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.refresh()

    def collect_variables(self):
        rows = []

        sources = [
            ("runtime", getattr(self.app, "workflow_output_vars", {})),
            ("workflow_vars", getattr(self.app, "workflow_vars", {})),
            ("output_vars", getattr(self.app, "output_vars", {})),
        ]

        state = getattr(self.app, "current_workflow_state", {})
        if isinstance(state, dict):
            sources.append(("current_state", state.get("output_vars", {})))

        for source, data in sources:
            if isinstance(data, dict):
                for name, value in sorted(data.items()):
                    rows.append(
                        {
                            "source": source,
                            "name": str(name),
                            "value": value,
                        }
                    )

        shared = getattr(self.app.cfg, "SharedVariables", {})
        if isinstance(shared, dict):
            for name, value in sorted(shared.items()):
                rows.append(
                    {
                        "source": "shared",
                        "name": str(name),
                        "value": value,
                    }
                )

        return rows

    def refresh(self):
        self.snapshot = self.collect_variables()

        self.listbox.delete(0, END)

        for row in self.snapshot:
            self.listbox.insert(
                END,
                f"[{row.get('source')}] {row.get('name')} = {str(row.get('value'))[:80]}",
            )

        self.details.delete("1.0", END)
        self.details.insert(
            "1.0",
            f"Variables: {len(self.snapshot)}\n\n"
            "Select a variable to inspect it.",
        )

    def selected_item(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None

        index = idxs[0]
        if index < 0 or index >= len(self.snapshot):
            return None

        return self.snapshot[index]

    def on_select(self, _event=None):
        item = self.selected_item()

        self.details.delete("1.0", END)

        if not item:
            return

        lines = [
            f"Source: {item.get('source')}",
            f"Name: {item.get('name')}",
            "",
            "=" * 80,
            "VALUE",
            "=" * 80,
            str(item.get("value")),
            "",
            "=" * 80,
            "RAW",
            "=" * 80,
            pprint.pformat(item, indent=4),
        ]

        self.details.insert("1.0", "\n".join(lines))

    def copy_all(self):
        payload = self.collect_variables()
        text = pprint.pformat(payload, indent=4)

        self.window.clipboard_clear()
        self.window.clipboard_append(text)

        messagebox.showinfo("Workflow Variables", "Variables copied to clipboard.")

    def promote_selected(self):
        item = self.selected_item()

        if not item:
            messagebox.showerror("Workflow Variables", "Select a variable first.")
            return

        name = str(item.get("name", "")).strip()
        value = item.get("value", "")

        if not name:
            return

        shared = getattr(self.app.cfg, "SharedVariables", None)

        if not isinstance(shared, dict):
            shared = {}
            setattr(self.app.cfg, "SharedVariables", shared)

        shared[name] = value

        self.app.persist_full_config()
        self.app.set_status(f"Promoted workflow variable to SharedVariables: {name}")

        self.refresh()


    def delete_selected(self):
        item = self.selected_item()

        if not item:
            messagebox.showerror("Workflow Variables", "Select a variable first.")
            return

        source = item.get("source")
        name = str(item.get("name", "")).strip()

        if not name:
            return

        if source == "runtime":
            data = getattr(self.app, "workflow_output_vars", {})
            if isinstance(data, dict):
                data.pop(name, None)

        elif source == "shared":
            if not messagebox.askokcancel(
                "Delete Shared Variable",
                f"Delete shared variable '{name}' from config?",
            ):
                return

            shared = getattr(self.app.cfg, "SharedVariables", {})
            if isinstance(shared, dict):
                shared.pop(name, None)
                self.app.persist_full_config()

        else:
            messagebox.showerror(
                "Workflow Variables",
                f"Cannot delete variable from source: {source}",
            )
            return

        self.refresh()

    def export(self):
        payload = self.collect_variables()

        default_dir = Path.home() / "Documents" / "termforge-workflows"
        default_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        target = filedialog.asksaveasfilename(
            title="Export Workflow Variables",
            initialdir=str(default_dir),
            initialfile=f"workflow-variables-{timestamp}.json",
            defaultextension=".json",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )

        if not target:
            return

        try:
            Path(target).write_text(
                json.dumps(payload, indent=4, sort_keys=True),
                encoding="utf-8",
            )

            messagebox.showinfo(
                "Workflow Variables",
                f"Exported:\n\n{target}",
            )

        except Exception as exc:
            self.app.show_traceback_window(
                "Export Workflow Variables Failed",
                exc,
            )

    def clear_runtime(self):
        if not messagebox.askokcancel(
            "Clear Runtime Variables",
            "Clear runtime workflow output variables?\n\nSharedVariables will not be changed.",
        ):
            return

        self.app.workflow_output_vars = {}
        self.refresh()
