import shutil
import pprint
from tkinter import *
from tkinter import messagebox

from ..backends import X11Backend, SubprocessBackend, TmuxBackend

class BackendManagerWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Backend Manager")
        self.window.geometry("840x480")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(outer, text="Backend Manager", bd=4, width=32, bg="lightgreen", fg="black", relief="raised",).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))

        Button(action_row, text="Auto-detect", width=14, bg="#555577", fg="white", command=self.auto_detect_backend,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Apply Backend", width=16, bg="darkgreen", fg="white", command=self.apply_backend,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Test Backend", width=14, bg="#2f5597", fg="white", command=self.test_backend,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Pick Tmux Target", width=18, bg="#555577", fg="white", command=self.pick_tmux_target,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Attach Tmux", width=14, bg="#3d6d3d", fg="white", command=self.attach_tmux,).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=14, bg="red", fg="black", command=self.window.destroy,).pack(side=RIGHT)

        self.backend_var = StringVar(value=app.get_backend_name())

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        Label(body, text="Backend:", width=14, anchor="w",).pack(anchor="w")

        self.backend_menu = OptionMenu(body, self.backend_var, "x11", "subprocess", "tmux",)

        tmux_frame = Frame(body)
        tmux_frame.pack(fill=X, pady=(8, 8))

        row = 0

        Label(tmux_frame, text="Tmux Session:", width=14, anchor="w",).grid(row=row, column=0, sticky="w", pady=3)

        self.tmux_session_var = StringVar(value=str(getattr(app.cfg, "TmuxSession", "termforge")))

        Entry(tmux_frame, textvariable=self.tmux_session_var, width=32,).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        Label(tmux_frame, text="Tmux Pane:", width=14, anchor="w",).grid(row=row, column=0, sticky="w", pady=3)

        self.tmux_pane_var = StringVar(value=str(getattr(app.cfg, "TmuxPane", "")))

        Entry(tmux_frame, textvariable=self.tmux_pane_var, width=32,).grid(row=row, column=1, sticky="w", pady=3)

        self.backend_menu.config(width=32)
        self.backend_menu.pack(anchor="w", pady=(0, 8))

        self.info = Text(body, wrap="word", height=18)
        self.info.pack(fill=BOTH, expand=True)

        try:
            if self.window.winfo_exists():
                self.refresh_info()
        except Exception:
            pass

    def refresh_info(self):
        report = self.app.backend_health_report()

        x11 = X11Backend(self.app)
        subprocess_backend = SubprocessBackend(self.app)
        tmux_backend = TmuxBackend(self.app)

        warning = report.get("warning", "")

        lines = [
            "Backend Health Check",
            "",
            f"Session type: {report.get('session')}",
            f"Current backend: {report.get('current_backend')}",
            f"Recommended backend: {report.get('recommended_backend')}",
            "",
            "Environment:",
            f"  DISPLAY: {report.get('DISPLAY') or '(empty)'}",
            f"  WAYLAND_DISPLAY: {report.get('WAYLAND_DISPLAY') or '(empty)'}",
            "",
            "Availability:",
            f"  xdotool: {report.get('xdotool_available')}",
            f"  subprocess: True",
            "",
        ]

        if warning:
            lines.extend([
                "Warning:",
                f"  {warning}",
                "",
            ])

        lines.extend([
            "Available backends:",
            "",
            "x11:",
            f"  Label: {x11.label}",
            f"  Available: {x11.is_available()}",
            f"  Description: {x11.description}",
            "",
            "subprocess:",
            f"  Label: {subprocess_backend.label}",
            f"  Available: {subprocess_backend.is_available()}",
            f"  Description: {subprocess_backend.description}",
            "",
            "tmux:",
            f"  Label: {tmux_backend.label}",
            f"  Available: {tmux_backend.is_available()}",
            f"  Description: {tmux_backend.description}",
            f"  Session: {getattr(self.app.cfg, 'TmuxSession', 'termforge')}",
            f"  Pane: {getattr(self.app.cfg, 'TmuxPane', '') or '(session default)'}",
        ])

        self.info.delete("1.0", END)
        self.info.insert("1.0", "\n".join(lines))

    def auto_detect_backend(self):
        try:
            self.app.auto_select_backend()
            self.backend_var.set(self.app.get_backend_name())
        except Exception as exc:
            self.app.show_traceback_window("Auto-detect Backend Failed", exc)
            return

        try:
            if self.window.winfo_exists():
                self.refresh_info()
        except Exception:
            pass

    def pick_tmux_target(self):
        try:
            picker = TmuxTargetPickerWindow(self.app, self)
            picker.window.wait_window()
        except Exception as exc:
            self.app.show_traceback_window("Tmux Target Picker Failed", exc)

        try:
            if self.window.winfo_exists():
                self.refresh_info()
        except Exception:
            pass

    def apply_backend(self):
        name = self.backend_var.get().strip().lower()

        try:
            setattr(
                self.app.cfg,
                "TmuxSession",
                self.tmux_session_var.get().strip() or "termforge",
            )
            setattr(
                self.app.cfg,
                "TmuxPane",
                self.tmux_pane_var.get().strip(),
            )

            self.app.set_backend_name(name)
            if name == "tmux":
                self.app.backend.attach_to_selected_window()

            selected = self.app.get_selected_window_id()

            if selected:
                self.app.set_status(
                    f"Backend selected: {name}; using existing selected window {selected}"
                )
            else:
                self.app.backend.select_target()

        except Exception as exc:
            self.app.show_traceback_window("Apply Backend Failed", exc)
            return

        try:
            if self.window.winfo_exists():
                self.refresh_info()
        except Exception:
            pass

    def attach_tmux(self):
        try:
            setattr(
                self.app.cfg,
                "TmuxSession",
                self.tmux_session_var.get().strip() or "termforge",
            )

            if self.app.get_backend_name() != "tmux":
                self.app.set_backend_name("tmux")

            if not hasattr(self.app.backend, "attach"):
                raise TermForgeError("Current backend does not support attach.")

            self.app.backend.attach()

        except Exception as exc:
            self.app.show_traceback_window("Attach Tmux Failed", exc)

    def test_backend(self):
        name = self.backend_var.get().strip().lower()

        try:
            if name == "subprocess":
                self.app.set_backend_name("subprocess")

                self.app.backend.run_detached(
                    "echo TERMFORGE_BACKEND_TEST >> /tmp/termforge-backend-test.log",
                    record_history=True,
                )

                messagebox.showinfo(
                    "Backend Test",
                    "Subprocess backend test launched.\n\n"
                    "Check:\n/tmp/termforge-backend-test.log",
                )
                return

            elif name == "tmux":
                if shutil.which("tmux") is None:
                    messagebox.showerror(
                        "Backend Test",
                        "tmux is not installed.\n\nInstall it with:\n\nsudo apt install tmux",
                    )
                    return

                setattr(
                    self.app.cfg,
                    "TmuxSession",
                    self.tmux_session_var.get().strip() or "termforge",
                )
                setattr(
                    self.app.cfg,
                    "TmuxPane",
                    self.tmux_pane_var.get().strip(),
                )

                self.app.set_backend_name("tmux")

                self.app.backend.send_text(
                    "echo TERMFORGE_TMUX_BACKEND_TEST",
                    record_history=True,
                )

                messagebox.showinfo(
                    "Backend Test",
                    "Tmux backend test sent.\n\n"
                    "Attach with:\n"
                    f"tmux attach -t {self.tmux_session_var.get().strip() or 'termforge'}",
                )
                return

            elif name == "x11":
                self.app.set_backend_name("x11")
                self.app.backend.select_target()

                messagebox.showinfo(
                    "Backend Test",
                    "X11 backend selected.\n\n"
                    "Try sending a command to the selected window.",
                )
                return

            else:
                messagebox.showerror(
                    "Backend Test",
                    f"Unknown backend: {name}",
                )
                return

        except Exception as exc:
            self.app.show_traceback_window("Backend Test Failed", exc)

        try:
            if self.window.winfo_exists():
                self.refresh_info()
        except Exception:
            pass

    def send_text(self, text: str, record_history: bool = True):
        self.run_detached(text, record_history=record_history)

class TmuxTargetPickerWindow:
    def __init__(self, app, manager=None):
        self.app = app
        self.manager = manager

        self.window = Toplevel(app.root)
        self.window.title("Tmux Target Picker")
        self.window.geometry("980x520")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Tmux Target Picker",
            bd=4,
            width=34,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))

        Button(
            action_row,
            text="Use Selected",
            width=14,
            bg="darkgreen",
            fg="white",
            command=self.use_selected,
        ).pack(side=LEFT, padx=(0, 6))

        Button(
            action_row,
            text="Refresh",
            width=14,
            bg="navy",
            fg="white",
            command=self.refresh,
        ).pack(side=LEFT, padx=(0, 6))

        Button(
            action_row,
            text="Close",
            width=14,
            bg="red",
            fg="black",
            command=self.window.destroy,
        ).pack(side=RIGHT)

        self.listbox = Listbox(
            outer,
            width=140,
            height=18,
            exportselection=False,
        )
        self.listbox.pack(fill=BOTH, expand=True)

        self.info = Text(outer, wrap="word", height=8)
        self.info.pack(fill=BOTH, expand=True, pady=(8, 0))

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.refresh()

    def refresh(self):
        backend = TmuxBackend(self.app)
        self.snapshot = backend.list_targets()

        self.listbox.delete(0, END)
        self.info.delete("1.0", END)

        if not self.snapshot:
            self.info.insert(
                "1.0",
                "No tmux targets found.\n\n"
                "Create one with:\n"
                "tmux new-session -d -s termforge bash",
            )
            return

        for item in self.snapshot:
            active = "*" if item.get("active") else " "
            self.listbox.insert(
                END,
                f'{active} {item.get("target")} '
                f'[{item.get("pane_id")}] '
                f'window="{item.get("window_name")}" '
                f'cmd={item.get("command")}',
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

        if not item:
            return

        self.info.delete("1.0", END)
        self.info.insert("1.0", pprint.pformat(item, indent=4))

    def use_selected(self):
        item = self.selected_item()

        if not item:
            messagebox.showerror(
                "Tmux Target Picker",
                "Select a tmux target first.",
            )
            return

        session = item.get("session", "")
        target = item.get("target", "")

        setattr(self.app.cfg, "TmuxSession", session)
        setattr(self.app.cfg, "TmuxPane", target)

        self.app.persist_full_config()

        if self.manager is not None:
            if hasattr(self.manager, "tmux_session_var"):
                self.manager.tmux_session_var.set(session)

            if hasattr(self.manager, "tmux_pane_var"):
                self.manager.tmux_pane_var.set(target)

        self.app.set_status(f"Selected tmux target: {target}")
        self.window.destroy()

