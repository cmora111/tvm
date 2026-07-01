from tkinter import *
from tkinter import filedialog, messagebox, simpledialog
import pprint

class ProfileManagerWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Profile / Environment Manager")
        self.window.geometry("880x520")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Profile / Environment Manager",
            bd=4,
            width=38,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))

        Button(action_row, text="Save Current Window", width=20, bg="darkgreen", fg="white", command=self.save_current).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Select Profile", width=16, bg="#2f5597", fg="white", command=self.select_profile).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Test Profile", width=14, bg="navy", fg="white", command=self.test_profile).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Delete", width=14, bg="#7f6000", fg="white", command=self.delete_profile).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Refresh", width=14, bg="#555555", fg="white", command=self.refresh).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Validate All", width=14, bg="#555577", fg="white", command=self.validate_all,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=14, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        left.pack(side=LEFT, fill=BOTH, expand=True)

        right = Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=44, height=22, exportselection=False)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        row = 0

        Label(form, text="Profile Name:", width=16, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.name_var = StringVar()
        Entry(form, textvariable=self.name_var, width=42).grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        Label(form, text="Window ID:", width=16, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.window_id_var = StringVar()
        Entry(form, textvariable=self.window_id_var, width=42).grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        Label(form, text="Backend:", width=16, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.backend_var = StringVar(value=self.app.get_backend_name())
        self.backend_menu = OptionMenu(
            form,
            self.backend_var,
            "x11",
            "subprocess",
            "tmux",
        )

        self.backend_menu.config(width=38)
        self.backend_menu.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        Label(form, text="Tmux Session:", width=16, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.tmux_session_var = StringVar(
            value=str(getattr(self.app.cfg, "TmuxSession", "termforge"))
        )
        Entry(form, textvariable=self.tmux_session_var, width=42).grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        Label(form, text="Tmux Pane:", width=16, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.tmux_pane_var = StringVar(value=str(getattr(self.app.cfg, "TmuxPane", "")))
        Entry(form, textvariable=self.tmux_pane_var, width=42).grid(row=row, column=1, sticky="ew", pady=3)
        row += 1

        Label(form, text="Tmux Mode:", width=16, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.tmux_mode_var = StringVar(
            value=str(getattr(self.app.cfg, "TmuxMode", "pane"))
        )
        self.tmux_mode_menu = OptionMenu(form, self.tmux_mode_var, "pane", "job",)
        self.tmux_mode_menu.config(width=38)
        self.tmux_mode_menu.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        form.columnconfigure(1, weight=1)

        self.info = Text(right, wrap="word", height=16)
        self.info.pack(fill=BOTH, expand=True, pady=(10, 0))

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.refresh()

    def refresh(self):
        profiles = self.app.get_window_profiles()
        self.snapshot = []

        self.listbox.delete(0, END)

        for name in sorted(profiles.keys()):
            profile = profiles.get(name, {})

            if isinstance(profile, dict):
                window_id = profile.get("window_id", "")
            else:
                window_id = profile
                profile = {
                    "window_id": window_id,
                    "legacy_format": True,
                }

            validation = self.app.validate_window_profile(name)
            status = validation.get("status", "unknown").upper()

            self.snapshot.append((name, profile, validation))

            backend = profile.get("backend", "")

            self.listbox.insert(
                END,
                f"[{status}] {name} -> {window_id}",
                f"{f'backend:{backend}' if backend else ''}",
            )

        self.info.delete("1.0", END)
        self.info.insert(
            "1.0",
            "Select a profile or save the current selected target window.\n\n"
            "Use this with chain steps like:\n"
            "[\"select_profile\", \"server\"]"
        )

    def validate_all(self):
        results = self.app.validate_all_window_profiles()

        valid = sum(1 for item in results if item.get("valid"))
        stale = sum(1 for item in results if not item.get("valid"))

        self.info.delete("1.0", END)
        self.info.insert(
            "1.0",
            f"Profile Validation\n\n"
            f"Valid: {valid}\n"
            f"Stale/Missing: {stale}\n\n"
            f"{pprint.pformat(results, indent=4)}"
        )

        self.refresh()

    def selected_profile_name(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None

        index = idxs[0]

        if index < 0 or index >= len(self.snapshot):
            return None

        return self.snapshot[index][0]

    def on_select(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return

        index = idxs[0]

        if index < 0 or index >= len(self.snapshot):
            return

        row = self.snapshot[index]

        if len(row) == 3:
            name, profile, validation = row
        else:
            name, profile = row
            validation = self.app.validate_window_profile(name)

        self.name_var.set(name)
        self.window_id_var.set(str(profile.get("window_id", "")))

        if hasattr(self, "backend_var"):
            self.backend_var.set(profile.get("backend", self.app.get_backend_name()))

        if hasattr(self, "tmux_session_var"):
            self.tmux_session_var.set(
                str(profile.get("tmux_session", getattr(self.app.cfg, "TmuxSession", "termforge")))
            )

        if hasattr(self, "tmux_pane_var"):
            self.tmux_pane_var.set(
                str(profile.get("tmux_pane", getattr(self.app.cfg, "TmuxPane", "")))
            )

        if hasattr(self, "tmux_mode_var"):
            self.tmux_mode_var.set(
                str(profile.get("tmux_mode", getattr(self.app.cfg, "TmuxMode", "pane")))
            )

        self.info.delete("1.0", END)
        self.info.insert(
            "1.0",
            pprint.pformat(
                {
                    "profile": profile,
                    "validation": validation,
                },
                indent=4,
            ),
        )

    def save_current(self):
        name = self.name_var.get().strip()

        if not name:
            messagebox.showerror("Profile Manager", "Enter a profile name first.")
            return

        try:
            setattr(self.app.cfg, "Backend", self.backend_var.get().strip() or self.app.get_backend_name())
            setattr(self.app.cfg, "TmuxSession", self.tmux_session_var.get().strip() or "termforge")
            setattr(self.app.cfg, "TmuxPane", self.tmux_pane_var.get().strip())
            setattr(self.app.cfg, "TmuxMode", self.tmux_mode_var.get().strip() or "pane")
            self.app.backend = self.app.create_backend()
            self.app.save_current_window_as_profile(name)
        except Exception as exc:
            self.app.show_traceback_window("Save Profile Failed", exc)
            return

        self.app.set_status(f"Saved profile: {name}")
        self.refresh()

    def select_profile(self):
        name = self.name_var.get().strip() or self.selected_profile_name()

        if not name:
            messagebox.showerror("Profile Manager", "Select a profile first.")
            return

        try:
            self.app.select_window_profile(name)
        except Exception as exc:
            self.app.show_traceback_window("Select Profile Failed", exc)
            return

        self.refresh()

    def test_profile(self):
        name = self.name_var.get().strip() or self.selected_profile_name()

        if not name:
            messagebox.showerror("Profile Manager", "Select a profile first.")
            return

        try:
            self.app.select_window_profile(name)
            self.app.send_to_selected_window("echo TERMFORGE_PROFILE_TEST")
        except Exception as exc:
            self.app.show_traceback_window("Test Profile Failed", exc)
            return

        messagebox.showinfo("Profile Manager", f"Profile tested:\n\n{name}")

    def delete_profile(self):
        name = self.name_var.get().strip() or self.selected_profile_name()

        if not name:
            messagebox.showerror("Profile Manager", "Select a profile first.")
            return

        if not messagebox.askokcancel("Delete Profile", f"Delete profile '{name}'?"):
            return

        profiles = self.app.get_window_profiles()
        profiles.pop(name, None)
        self.app.save_window_profiles()

        self.name_var.set("")
        self.window_id_var.set("")
        self.refresh()

class ConfigHealthCheckWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Config Health Check")
        self.window.geometry("980x620")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Config Health Check",
            bd=4,
            width=32,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))

        Button(
            action_row,
            text="Run Check",
            width=14,
            bg="navy",
            fg="white",
            command=self.refresh,
        ).pack(side=LEFT, padx=(0, 6))

        Button(
            action_row,
            text="Copy Report",
            width=14,
            bg="#2f5597",
            fg="white",
            command=self.copy_report,
        ).pack(side=LEFT, padx=(0, 6))

        Button(
            action_row,
            text="Close",
            width=14,
            bg="red",
            fg="black",
            command=self.window.destroy,
        ).pack(side=RIGHT)

        self.listbox = Listbox(outer, width=120, height=18, exportselection=False)
        self.listbox.pack(fill=BOTH, expand=True)

        self.details = Text(outer, wrap="word", height=12)
        self.details.pack(fill=BOTH, expand=True, pady=(8, 0))

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.refresh()

    def refresh(self):
        self.snapshot = self.app.check_config_health()
        self.listbox.delete(0, END)
        self.details.delete("1.0", END)

        counts = {}

        for issue in self.snapshot:
            counts[issue["level"]] = counts.get(issue["level"], 0) + 1
            self.listbox.insert(
                END,
                f'[{issue["level"].upper()}] '
                f'{issue["area"]}: {issue["message"]}'
            )

        summary = "Config Health Summary\n\n"
        summary += "\n".join(
            f"{level}: {count}"
            for level, count in sorted(counts.items())
        )

        self.details.insert("1.0", summary)

    def on_select(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return

        issue = self.snapshot[idxs[0]]

        self.details.delete("1.0", END)
        self.details.insert(
            "1.0",
            pprint.pformat(issue, indent=4),
        )

    def copy_report(self):
        report = pprint.pformat(self.snapshot, indent=4)

        self.window.clipboard_clear()
        self.window.clipboard_append(report)
        self.window.update()

        messagebox.showinfo("Config Health Check", "Report copied to clipboard.")

