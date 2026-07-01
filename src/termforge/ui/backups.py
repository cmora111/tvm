from tkinter import *
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path
import shutil
from datetime import datetime
import pprint
from ..constants import CONFIG_DIR, CONFIG_FILE, BACKUP_DIR, PROJECT_BACKUP_DIR
from .theme import button_style

class BackupManagerWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Backup Manager")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(outer, text="Backup Manager", bd=4, width=32, bg="lightgreen", fg="black", relief="raised",).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))

        for i in range(3):
            action_row.columnconfigure(i, weight=1)

        row = 0

        Button(action_row, text="Project Snapshot", bg="#2e8b57", fg="white",
               activebackground="#3ca06a", activeforeground="white",
               command=self.create_project_snapshot,).grid(row=row, column=0, sticky="ew", padx=2, pady=2)
        Button(action_row, text="Refresh", command=self.refresh, **button_style("primary"),).grid(row=row, column=1, sticky="ew", padx=2, pady=2)
        Button(action_row, text="Restore", bg="#b8860b", fg="black",
               activebackground="#d4a017", activeforeground="black",
               command=self.restore_selected,).grid(row=row, column=2, sticky="ew", padx=2, pady=2)
        row += 1

        Button( action_row, text="Export", bg="#5b4b8a", fg="white",
               activebackground="#7460aa", activeforeground="white",
               command=self.export_selected,).grid(row=row, column=0, sticky="ew", padx=2, pady=2)
        Button(action_row, text="Close", bg="#b22222", fg="white",
               activebackground="#d63c3c", activeforeground="white",
               command=self.window.destroy,).grid(row=row, column=2, sticky="ew", padx=2, pady=2)
        row += 1

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        left.pack(side=LEFT, fill=BOTH, expand=True)

        right = Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=62, height=24)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.info = Text(right, wrap="word", width=44, height=24)
        self.info.pack(fill=BOTH, expand=True)

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.refresh()

    def collect_backups(self):
        backup_dir = self.app.get_backup_dir()
        files = sorted(backup_dir.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)

        rows = []
        for path in files:
            try:
                stat = path.stat()
                rows.append({
                    "path": path,
                    "name": path.name,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "size": stat.st_size,
                })
            except Exception:
                pass

        return rows

    def refresh(self):
        self.snapshot = []
        self.listbox.delete(0, END)

        try:
            backup_root = CONFIG_DIR / "backups"
            project_dir = backup_root / "project"

            backup_root.mkdir(parents=True, exist_ok=True)
            project_dir.mkdir(parents=True, exist_ok=True)

            files = []

            files.extend(backup_root.glob("*.py"))
            files.extend(project_dir.glob("*.tar.gz"))

            files = sorted(
                files,
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            for path in files:
                self.snapshot.append(path)

                modified = datetime.fromtimestamp(
                    path.stat().st_mtime
                ).strftime("%Y-%m-%d %H:%M:%S")

                size = path.stat().st_size
                kind = "project" if path.suffixes[-2:] == [".tar", ".gz"] else "config"

                self.listbox.insert(
                    END,
                    f"[{kind}] {path.name} — {modified} — {size} bytes",
                )

            self.info.delete("1.0", END)
            self.info.insert(
                "1.0",
                f"Backups found: {len(self.snapshot)}\n\n"
                "Project snapshots are full .tar.gz archives."
            )

        except Exception as exc:
            self.info.delete("1.0", END)
            self.info.insert(
                "1.0",
                f"Could not refresh backups:\n\n{exc}",
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
        idxs = self.listbox.curselection()
        if not idxs:
            return

        index = idxs[0]

        if index < 0 or index >= len(self.snapshot):
            return

        path = self.snapshot[index]

        try:
            modified = datetime.fromtimestamp(
                path.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M:%S")

            size = path.stat().st_size
            kind = "project" if path.suffixes[-2:] == [".tar", ".gz"] else "config"

            details = [
                f"Type: {kind}",
                f"Name: {path.name}",
                f"Path: {path}",
                f"Modified: {modified}",
                f"Size: {size} bytes",
            ]

        except Exception as exc:
            details = [
                f"Path: {path}",
                f"Could not read details: {exc}",
            ]

        self.info.delete("1.0", END)
        self.info.insert("1.0", "\n".join(details))

    def restore_selected(self):
        idxs = self.listbox.curselection()
        if not idxs:
            messagebox.showerror(
                "Backup Manager",
                "Select a backup first.",
            )
            return

        index = idxs[0]

        if index < 0 or index >= len(self.snapshot):
            return

        path = self.snapshot[index]
        kind = "project" if path.suffixes[-2:] == [".tar", ".gz"] else "config"

        if kind == "project":
            messagebox.showinfo(
                "Backup Manager",
                "Project snapshots are full .tar.gz archives.\n\n"
                "Automatic restore is disabled for safety.\n\n"
                f"Archive:\n{path}\n\n"
                "Restore manually from a terminal after reviewing it.",
            )
            return

        if not messagebox.askokcancel(
            "Restore Backup",
            f"Restore this config backup?\n\n{path.name}\n\n"
            "This will overwrite your current config.",
        ):
            return

        try:
            CONFIG_FILE.write_text(
                path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            messagebox.showinfo(
                "Backup Manager",
                "Config backup restored.\n\nRestart TermForge to reload it.",
            )

        except Exception as exc:
            self.app.show_traceback_window(
                "Restore Backup Failed",
                exc,
            )

    def export_selected(self):
        idxs = self.listbox.curselection()
        if not idxs:
            messagebox.showerror(
                "Backup Manager",
                "Select a backup first.",
            )
            return

        index = idxs[0]

        if index < 0 or index >= len(self.snapshot):
            return

        path = self.snapshot[index]

        target = filedialog.asksaveasfilename(
            title="Export Backup",
            initialfile=path.name,
            defaultextension=path.suffix,
            filetypes=[
                ("Backup files", "*.py *.tar.gz"),
                ("All files", "*.*"),
            ],
        )

        if not target:
            return

        try:
            shutil.copy2(path, target)

            messagebox.showinfo(
                "Backup Manager",
                f"Backup exported to:\n\n{target}",
            )

        except Exception as exc:
            self.app.show_traceback_window(
                "Export Backup Failed",
                exc,
            )

    def delete_selected(self):
        item = self.selected_item()
        if not item:
            messagebox.showerror("Backup Manager", "Select a backup first.")
            return

        if not messagebox.askokcancel(
            "Delete Backup",
            f"Delete backup?\n\n{item['name']}",
        ):
            return

        try:
            Path(item["path"]).unlink()
        except Exception as exc:
            self.app.show_traceback_window("Delete Backup Failed", exc)
            return

        self.refresh()

    def open_folder(self):
        backup_dir = self.app.get_backup_dir()

        try:
            subprocess.Popen(["xdg-open", str(backup_dir)])
        except Exception as exc:
            self.app.show_traceback_window("Open Backup Folder Failed", exc)

    def create_project_snapshot(self):
        try:
            path = self.app.create_project_snapshot_backup()
        except Exception as exc:
            self.app.show_traceback_window(
                "Project Snapshot Failed",
                exc,
            )
            return

        messagebox.showinfo(
            "Backup Manager",
            f"Project snapshot created:\n\n{path}",
        )

        self.refresh()

