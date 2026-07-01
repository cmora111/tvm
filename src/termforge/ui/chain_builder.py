import json
import pprint
import time
from datetime import datetime
from tkinter import *
from tkinter import filedialog, messagebox, simpledialog

class ChainBuilderWindow:
    STEP_KINDS = ["vars", "select_profile", "sleep", "send", "spawn", "detached"]

    def __init__(self, parent, app, initial_steps=None):
        self.parent = parent
        self.app = app
        self.result = None
        self.window = Toplevel(parent)
        self.window.title("Visual Chain Builder")
        self.window.geometry("1100x700")
        self.window.transient(parent)
        self.window.grab_set()
        self.build_menu()

        self.steps = list(initial_steps or [])

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(outer, text="Visual Chain Builder", bd=4, width=32, bg="lightgreen", fg="black", relief="raised",).pack(pady=(0, 8))

        top_actions = Frame(outer)
        top_actions.pack(fill=X, pady=(0, 8))

        Button(top_actions, text="Apply to Editor", width=18, bg="navy", fg="white", command=self.apply_to_editor_now,).pack(side=LEFT, padx=(0, 6))
        Button(top_actions, text="Templates", width=14, bg="#555577", fg="white", command=self.manage_chain_templates,).pack(side=LEFT, padx=(0, 6))
        Button(top_actions, text="Close", width=12, bg="red", fg="black", command=self.close,).pack(side=RIGHT)

        top = Frame(outer)
        top.pack(fill=BOTH, expand=True)

        left = Frame(top)
        left.pack(side=LEFT, fill=Y)

        right = Frame(top)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=42, height=22)
        self.listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        row = 0

        Label(form, text="Step Kind:", width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        self.kind_var = StringVar(value="send")
        kind_menu = OptionMenu(form, self.kind_var, *self.STEP_KINDS)
        kind_menu.config(width=38)
        kind_menu.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        self.value_label = Label(form, text="Value:", width=14, anchor="nw")
        self.value_label.grid(row=row, column=0, sticky="nw", pady=3)
        self.value_text = Text(form, height=7, width=70, wrap="word")
        self.value_text.grid(row=row, column=1, sticky="nsew", pady=3)

        self.profile_var = StringVar()
        self.profile_menu = OptionMenu(form, self.profile_var, "")
        self.profile_menu.config(width=38)
        self.profile_menu.grid(row=row, column=1, sticky="w", pady=3)
        self.profile_menu.grid_remove()
        row += 1

        self.hint_var = StringVar(value="")
        Label(form, textvariable=self.hint_var, anchor="w", fg="#333333").grid(row=row, column=1, sticky="w", pady=(0, 6))

        help_box = Text(right, height=14, wrap="word")
        help_box.pack(fill=BOTH, expand=True, pady=(10, 0))
        help_box.insert(
            "1.0",
            "Kinds:\n"
            "  vars            value = JSON list, e.g. [\"path\", \"host\"]\n"
            "  select_profile  value = profile name, e.g. server\n"
            "  sleep           value = seconds, e.g. 1\n"
            "  send            value = terminal command, becomes [2, \"...\"]\n"
            "  spawn           value = new terminal command, becomes [1, \"...\"]\n"
            "  detached        value = detached command, becomes [3, \"...\"]\n\n"
            "Examples:\n"
            "  kind=vars\n"
            "  value=[\"path\", \"host\"]\n\n"
            "  kind=send\n"
            "  value=cd <path>\n"
            "  Ctrl+I       = Insert Before\n"
            "  Ctrl+R       = Run Selected Step\n"
            "  Ctrl+Shift+R = Run To End\n"
            "  Ctrl+Shift+D = Dry Run Preview\n"
            "  Ctrl+Alt+d   = Dry Run Preview with Value\n"
            "  <home>       = Move to Top\n"
            "  <end>        = Move to Bottom\n"
            "  <delete>     = Delete step\n"
        )
        help_box.config(state="disabled")

        btns = Frame(outer)
        btns.pack(fill=X, pady=(10, 0))
        Button(btns, text="Add / Update Step", width=16, bg="darkgreen", fg="white", command=self.add_or_update_step).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Insert Before", width=14, bg="#2f5597", fg="white", command=self.insert_step_before,).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Remove Step", width=14, bg="#7f6000", fg="white", command=self.remove_selected_step,).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Validate Chain", width=14, bg="#555577", fg="white", command=self.validate_chain_with_notice,).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Run Selected Step", width=16, bg="#2f5597", fg="white", command=self.run_selected_step,).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Dry Run", width=12, bg="#555577", fg="white", command=self.show_dry_run_preview,).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Dry Run + Vars", width=14, bg="#555577", fg="white", command=self.show_dry_run_preview_with_values,).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Load Selected", width=14, bg="#2f5597", fg="white", command=self.load_selected).pack(side=LEFT, padx=(0, 6))

        self.drag_index = None

        self.listbox.bind("<Button-1>", self.on_drag_start)
        self.listbox.bind("<B1-Motion>", self.on_drag_motion)
        self.window.bind("<Control-i>", lambda _e: self.insert_step_before())
        self.window.bind("<Control-r>", self.run_selected_step_shortcut)
        self.window.bind("<Control-R>", self.run_selected_step_shortcut)
        self.listbox.bind("<Control-r>", self.run_selected_step_shortcut)
        self.listbox.bind("<Control-R>", self.run_selected_step_shortcut)
        self.window.bind("<Control-Shift-R>", self.run_from_selected_to_end_shortcut)
        self.listbox.bind("<Control-Shift-R>", self.run_from_selected_to_end_shortcut)
        self.window.bind("<Control-Shift-D>", lambda _e: self.show_dry_run_preview())
        self.listbox.bind("<Control-Shift-D>", lambda _e: self.show_dry_run_preview())
        self.window.bind("<Control-Alt-d>", lambda _e: self.show_dry_run_preview_with_values())
        self.listbox.bind("<Control-Alt-d>", lambda _e: self.show_dry_run_preview_with_values())
        self.window.bind_all("<Home>", self.move_to_top_shortcut)
        self.window.bind_all("<End>", self.move_to_bottom_shortcut)
        self.listbox.bind("<Home>", self.move_to_top_shortcut)
        self.listbox.bind("<End>", self.move_to_bottom_shortcut)
        self.window.bind("<Delete>", lambda _e: self.remove_selected_step())
        self.listbox.bind("<Delete>", lambda _e: self.remove_selected_step())
        self.kind_var.trace_add("write", self.update_kind_ui)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.update_kind_ui()
        self.refresh()

    def update_kind_ui(self, *_args):
        kind = self.kind_var.get().strip().lower()
        if kind == "vars":
            self.value_label.config(text="Vars JSON:")
            self.hint_var.set('Enter a JSON list, e.g. ["path", "host"]')
        elif kind == "select_profile":
            self.value_label.config(text="Profile:")
            self.show_profile_dropdown()
            self.hint_var.set("Choose a saved window profile.")
            return
        elif kind == "sleep":
            self.value_label.config(text="Seconds:")
            self.hint_var.set("Enter a number, e.g. 1 or 0.5")
        elif kind == "send":
            self.value_label.config(text="Command:")
            self.value_label.config(text="Command:")
            self.hint_var.set("Plain text command run in a new terminal")
        elif kind == "detached":
            self.value_label.config(text="Command:")
            self.hint_var.set("Plain text detached command run in background")
        else:
            self.value_label.config(text="Value:")
            self.hint_var.set("")

    def build_menu(self):
        menubar = Menu(self.window)

        edit_menu = Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Insert Before\tCtrl+I", command=self.insert_step_before)
        edit_menu.add_command(label="Duplicate Step\tCtrl+D", command=self.duplicate_step)
        edit_menu.add_command(label="Delete Step\tDelete", command=self.delete_step)
        edit_menu.add_separator()
        edit_menu.add_command(label="Move Up\tAlt+Up", command=self.move_up)
        edit_menu.add_command(label="Move Down\tAlt+Down", command=self.move_down)
        edit_menu.add_separator()
        edit_menu.add_command(label="Move To Top\tHome", command=self.move_to_top)
        edit_menu.add_command(label="Move To Bottom\tEnd", command=self.move_to_bottom)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        templates_menu = Menu(menubar, tearoff=0)
        templates_menu.add_command(label="Save Current Chain as Template", command=self.save_steps_as_template)
        templates_menu.add_command(label="Insert Template Before Selected", command=self.insert_template_before_selected)
        templates_menu.add_command(label="Append Template", command=self.append_template)
        templates_menu.add_separator()
        templates_menu.add_command(label="List Templates", command=self.manage_chain_templates)
        menubar.add_cascade(label="Templates", menu=templates_menu)

        run_menu = Menu(menubar, tearoff=0)
        run_menu.add_command(label="Run Selected Step\tCtrl+R", command=self.run_selected_step)
        run_menu.add_command(label="Run To End\tCtrl+Shift+R", command=self.run_from_selected_to_end)
        run_menu.add_separator()
        run_menu.add_command(label="Validate Chain", command=self.validate_chain_with_notice)
        run_menu.add_command(label="Dry Run\tCtrl+Shift+D", command=self.show_dry_run_preview)
        menubar.add_cascade(label="Run", menu=run_menu)

        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="Shortcuts", command=self.show_chain_builder_shortcuts)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.window.config(menu=menubar)


    def on_drag_start(self, event):
        index = self.listbox.nearest(event.y)
        if index >= 0:
            self.drag_index = index


    def on_drag_motion(self, event):
        if self.drag_index is None:
            return

        new_index = self.listbox.nearest(event.y)

        if new_index == self.drag_index:
            return

        if new_index < 0 or new_index >= len(self.steps):
            return

        # move step
        step = self.steps.pop(self.drag_index)
        self.steps.insert(new_index, step)

        self.refresh()

        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(new_index)
        self.listbox.activate(new_index)
        self.listbox.see(new_index)

        self.drag_index = new_index

    def get_selected_step_index(self):
        idxs = self.listbox.curselection()
        if idxs:
            return idxs[0]

        try:
            active = self.listbox.index("active")
            if 0 <= active < len(self.steps):
                return active
        except Exception:
            pass

        return None

    def move_to_top(self):
        i = self.get_selected_step_index()
        if i is None or i <= 0:
            return

        step = self.steps.pop(i)
        self.steps.insert(0, step)

        self.refresh()
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(0)
        self.listbox.activate(0)
        self.listbox.see(0)

    def move_to_bottom(self):
        i = self.get_selected_step_index()
        if i is None or i >= len(self.steps) - 1:
            return

        step = self.steps.pop(i)
        self.steps.append(step)

        new_index = len(self.steps) - 1

        self.refresh()
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(new_index)
        self.listbox.activate(new_index)
        self.listbox.see(new_index)

    def move_to_top_shortcut(self, event=None):
        self.move_to_top()
        return "break"

    def move_to_bottom_shortcut(self, event=None):
        self.move_to_bottom()
        return "break"

    def step_to_label(self, step):
        if isinstance(step, (list, tuple)) and step:
            kind = step[0]
            return f"{kind}: {step!r}"
        return repr(step)

    def show_chain_builder_shortcuts(self):
        messagebox.showinfo(
            "Chain Builder Shortcuts",
            "\n".join([
                "Chain Builder Shortcuts",
                "",
                "Ctrl+I         Insert step before selected",
                "Ctrl+D         Duplicate selected step",
                "Delete         Delete selected step",
                "Alt+Up         Move selected step up",
                "Alt+Down       Move selected step down",
                "Home           Move selected step to top",
                "End            Move selected step to bottom",
                "Ctrl+R         Run selected step",
                "Ctrl+Shift+R   Run selected step to end",
                "Ctrl+Shift+D   Dry run preview",
                "Ctrl+T         Edit Tags",
            ])
        )

    def refresh_profile_menu(self):
        profiles = self.app.get_window_profiles()
        names = sorted(profiles.keys())

        menu = self.profile_menu["menu"]
        menu.delete(0, "end")

        for name in names:
            menu.add_command(
                label=name,
                command=lambda value=name: self.profile_var.set(value),
            )

        if names and self.profile_var.get() not in names:
            self.profile_var.set(names[0])
        elif not names:
            self.profile_var.set("")


    def show_value_text(self):
        self.profile_menu.grid_remove()
        self.value_text.grid()
        self.value_label.config(anchor="nw")


    def show_profile_dropdown(self):
        self.value_text.grid_remove()
        self.profile_menu.grid()
        self.value_label.config(anchor="w")
        self.refresh_profile_menu()

    def save_steps_as_template(self):
        if not self.steps:
            self.app.show_traceback_window("Chain Templates", "There are no steps to save.")
            return

        prompt = MultiFieldPrompt(
            self.window,
            "Save Chain Template",
            ["template_name"],
            heading="Enter template name",
        )

        values = prompt.show()
        if values is None:
            return

        name = values.get("template_name", "").strip()
        if not name:
            self.app.show_traceback_window("Chain Templates", "Template name is required.")
            return

        templates = self.app.get_chain_templates()

        if name in templates:
            if not messagebox.askokcancel(
                "Overwrite Template",
                f"Template '{name}' already exists.\n\nOverwrite it?"
            ):
                return

        templates[name] = copy.deepcopy(self.steps)
        self.app.persist_chain_templates()
        self.app.set_status(f"Saved chain template {name}")
        messagebox.showinfo("Chain Templates", f"Saved template:\n\n{name}")


    def choose_chain_template(self):
        templates = self.app.get_chain_templates()
        if not templates:
            self.app.show_traceback_window("Chain Templates", "No chain templates have been saved yet.")
            return None

        names = sorted(templates.keys())

        prompt = MultiFieldPrompt(
            self.window,
            "Choose Chain Template",
            ["template_name"],
            defaults={"template_name": names[0]},
            heading="Enter template name",
        )

        values = prompt.show()
        if values is None:
            return None

        name = values.get("template_name", "").strip()
        if name not in templates:
            available = "\n".join(names)
            self.app.show_traceback_window(
                "Chain Templates",
                f"Unknown template: {name}\n\nAvailable templates:\n{available}"
            )
            return None

        return copy.deepcopy(templates[name])


    def insert_template_before_selected(self):
        steps = self.choose_chain_template()
        if steps is None:
            return

        idxs = self.listbox.curselection()
        insert_index = idxs[0] if idxs else len(self.steps)

        for offset, step in enumerate(steps):
            self.steps.insert(insert_index + offset, step)

        self.refresh()
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(insert_index)
        self.listbox.activate(insert_index)
        self.listbox.see(insert_index)

    def remove_selected_step(self):
        index = self.get_selected_step_index()

        if index is None:
            messagebox.showerror("Chain Builder", "Select a step first.")
            return

        if index < 0 or index >= len(self.steps):
            return

        step = self.steps[index]

        if not messagebox.askokcancel(
            "Remove Step",
            f"Remove this step?\n\n{step!r}",
        ):
            return

        del self.steps[index]

        self.refresh()

        if self.steps:
            new_index = min(index, len(self.steps) - 1)
            self.listbox.selection_clear(0, END)
            self.listbox.selection_set(new_index)
            self.listbox.activate(new_index)
            self.listbox.see(new_index)

        self.value_text.delete("1.0", END)

    def append_template(self):
        steps = self.choose_chain_template()
        if steps is None:
            return

        start = len(self.steps)
        self.steps.extend(steps)

        self.refresh()
        if self.steps:
            self.listbox.selection_clear(0, END)
            self.listbox.selection_set(start)
            self.listbox.activate(start)
            self.listbox.see(start)


    def manage_chain_templates(self):
        templates = self.app.get_chain_templates()

        if not templates:
            messagebox.showinfo("Chain Templates", "No templates saved yet.")
            return

        lines = ["Saved Chain Templates", ""]

        for name in sorted(templates.keys()):
            steps = templates.get(name, [])
            lines.append(f"{name}  ({len(steps)} step{'s' if len(steps) != 1 else ''})")

        messagebox.showinfo("Chain Templates", "\n".join(lines))

    def refresh(self):
        self.listbox.delete(0, END)
        for step in self.steps:
            self.listbox.insert(END, self.step_to_label(step))

    def insert_step_before(self):
        try:
            step = self.parse_current_step()
        except Exception as exc:
            self.app.show_traceback_window("Chain Builder", str(exc))
            return

        idxs = self.listbox.curselection()

        if idxs:
            insert_index = idxs[0]
        else:
            insert_index = len(self.steps)

        self.steps.insert(insert_index, step)
        self.refresh()

        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(insert_index)
        self.listbox.activate(insert_index)
        self.listbox.see(insert_index)

        self.value_text.delete("1.0", END)
        self.value_text.focus_set()

    def apply_to_editor_now(self):
        errors = self.validate_chain()
        if errors:
            self.app.show_traceback_window("Validate Chain", "\n".join(errors))
            return

        self.result = list(self.steps)

        try:
            self.window.grab_release()
        except Exception:
            pass

        self.window.destroy()





    def run_selected_step(self):
        index = self.get_selected_step_index()

        if index is None:
            self.app.show_traceback_window("Run Selected Step", "Select a step first.")
            return

        if index < 0 or index >= len(self.steps):
            return

        step = self.steps[index]

        try:
            self.app.run_chain_step(step)
            self.app.set_status(f"Ran chain step #{index + 1}")
        except Exception as exc:
            self.app.show_traceback_window(
                "Run Selected Step",
                f"Could not run selected step:\n\n{exc}"
            )


    def run_selected_step_shortcut(self, event=None):
        self.run_selected_step()
        return "break"

    def run_from_selected_to_end(self):
        index = self.get_selected_step_index()

        if index is None:
            self.app.show_traceback_window("Run To End", "Select a step first.")
            return

        if index < 0 or index >= len(self.steps):
            return

        failures = []

        for i in range(index, len(self.steps)):
            step = self.steps[i]

            try:
                self.app.run_chain_step(step)
                self.app.set_status(f"Ran chain step #{i + 1}")
            except Exception as exc:
                self.app.show_traceback_window(f"Step {i + 1}: ", str(exc))
                break

        if failures:
            self.app.show_traceback_window(
                "Run To End",
                "\n".join(failures)
            )


    def run_from_selected_to_end_shortcut(self, event=None):
        self.run_from_selected_to_end()
        return "break"

    def dry_run_lines(self, substitute_vars: bool = False) -> list[str]:
        lines = ["Dry Run Preview", ""]

        if not self.steps:
            lines.append("Chain has no steps.")
            return lines

        values = {}

        if substitute_vars:
            var_names = []
            for step in self.steps:
                if (
                    isinstance(step, (list, tuple))
                    and len(step) >= 2
                    and step[0] == "vars"
                    and isinstance(step[1], list)
                ):
                    for name in step[1]:
                        if isinstance(name, str) and name not in var_names:
                            var_names.append(name)

            if var_names:
                prompt = MultiFieldPrompt(
                    self.window,
                    "Dry Run Variables",
                    var_names,
                    heading="Enter preview values",
                )
                values = prompt.show() or {}

        def substitute(text: str) -> str:
            if not substitute_vars:
                return text
            for key, value in values.items():
                text = text.replace(f"<{key}>", value)
            return text

        for index, step in enumerate(self.steps, start=1):
            if not isinstance(step, (list, tuple)) or not step:
                lines.append(f"{index}. INVALID STEP: {step!r}")
                continue

            kind = step[0]

            if kind == "vars":
                names = step[1] if len(step) > 1 and isinstance(step[1], list) else []
                lines.append(
                    f"{index}. prompt vars -> {', '.join(map(str, names)) if names else '(none)'}"
                )

            elif kind == "select_profile":
                profile = step[1] if len(step) > 1 else ""
                lines.append(f"{index}. select profile -> {profile or '(missing)'}")

            elif kind == "sleep":
                seconds = step[1] if len(step) > 1 else ""
                lines.append(f"{index}. sleep -> {seconds} second(s)")

            elif kind in (1, "spawn"):
                command = substitute(str(step[1])) if len(step) > 1 else ""
                lines.append(f"{index}. spawn terminal -> {command or '(missing command)'}")

            elif kind in (2, "send"):
                command = substitute(str(step[1])) if len(step) > 1 else ""
                lines.append(f"{index}. send to selected window -> {command or '(missing command)'}")

            elif kind in (3, "detached"):
                command = substitute(str(step[1])) if len(step) > 1 else ""
                lines.append(f"{index}. detached/background -> {command or '(missing command)'}")

            else:
                lines.append(f"{index}. UNKNOWN kind={kind!r} step={step!r}")

            if len(step) > 2 and isinstance(step[2], dict) and step[2]:
                lines.append(f"   options -> {step[2]}")

        return lines

    def show_dry_run_preview(self):
        lines = self.dry_run_lines(substitute_vars=False)
        messagebox.showinfo("Dry Run Preview", "\n".join(lines))

    def show_dry_run_preview_with_values(self):
        lines = self.dry_run_lines(substitute_vars=True)
        messagebox.showinfo("Dry Run Preview With Values", "\n".join(lines))

    def parse_current_step(self):
        kind = self.kind_var.get().strip().lower()
        value = self.value_text.get("1.0", END).strip()
        if not kind:
            raise ValueError("Step kind is required.")

        if kind == "vars":
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError("vars value must be a JSON list.")
            return ["vars", parsed]
        if kind == "select_profile":
            profile_name = self.profile_var.get().strip()
            if not profile_name:
                raise ValueError("Profile name is required.")
            return ["select_profile", profile_name]
        if kind == "sleep":
            if not value:
                raise ValueError("Sleep seconds are required.")
            try:
                num = int(value)
            except ValueError:
                num = float(value)
            return ["sleep", num]
        if kind == "send":
            return [2, value]
        if kind == "spawn":
            return [1, value]
        if kind == "detached":
            return [3, value]
        raise ValueError("Unknown step kind.")

    def add_or_update_step(self):
        try:
            step = self.parse_current_step()
        except Exception as exc:
            self.app.show_traceback_window("Chain Builder", str(exc))
            return
        idxs = self.listbox.curselection()
        if idxs:
            self.steps[idxs[0]] = step
        else:
            self.steps.append(step)
        self.refresh()

    def duplicate_step(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        step = self.steps[idxs[0]]
        cloned = json.loads(json.dumps(step))
        self.steps.insert(idxs[0] + 1, cloned)
        self.refresh()
        self.listbox.selection_set(idxs[0] + 1)

    def delete_step(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        del self.steps[idxs[0]]
        self.refresh()

    def move_up(self):
        idxs = self.listbox.curselection()
        if not idxs or idxs[0] == 0:
            return
        i = idxs[0]
        self.steps[i-1], self.steps[i] = self.steps[i], self.steps[i-1]
        self.refresh()
        self.listbox.selection_set(i-1)

    def move_down(self):
        idxs = self.listbox.curselection()
        if not idxs or idxs[0] >= len(self.steps) - 1:
            return
        i = idxs[0]
        self.steps[i+1], self.steps[i] = self.steps[i], self.steps[i+1]
        self.refresh()
        self.listbox.selection_set(i+1)

    def validate_chain(self) -> list[str]:
        errors = []

        if not self.steps:
            errors.append("Chain has no steps.")
            return errors

        for index, step in enumerate(self.steps, start=1):
            if not isinstance(step, (list, tuple)) or not step:
                errors.append(f"Step {index}: invalid step format.")
                continue

            kind = step[0]

            if kind == "vars":
                if len(step) < 2 or not isinstance(step[1], list):
                    errors.append(f"Step {index}: vars step must be ['vars', ['name1', 'name2']].")
                else:
                    for var_name in step[1]:
                        if not isinstance(var_name, str) or not var_name.strip():
                            errors.append(f"Step {index}: vars contains an invalid variable name.")

            elif kind == "select_profile":
                if len(step) < 2 or not str(step[1]).strip():
                    errors.append(f"Step {index}: select_profile requires a profile name.")

            elif kind == "environment":
                if len(step) < 2 or not str(step[1]).strip():
                    errors.append(f"Step {index}: environment requires a template name.")

            elif kind == "sleep":
                if len(step) < 2:
                    errors.append(f"Step {index}: sleep requires seconds.")
                else:
                    try:
                        seconds = float(step[1])
                        if seconds < 0:
                            errors.append(f"Step {index}: sleep seconds cannot be negative.")
                    except Exception:
                        errors.append(f"Step {index}: sleep value must be a number.")

            elif kind in (1, 2, 3, "spawn", "send", "detached"):
                if len(step) < 2 or not str(step[1]).strip():
                    errors.append(f"Step {index}: command step requires command text.")

            else:
                errors.append(f"Step {index}: unknown step kind {kind!r}.")

        return errors


    def validate_chain_with_notice(self):
        errors = self.validate_chain()

        if errors:
            self.app.show_traceback_window("Validate Chain", "\n".join(errors))
            return False

        messagebox.showinfo("Validate Chain", "Chain looks valid.")
        return True

    def on_select(self, _event=None):
        self.load_selected()

    def load_selected(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        step = self.steps[idxs[0]]
        self.value_text.delete("1.0", END)
        if isinstance(step, (list, tuple)) and step:
            if step[0] == "vars":
                self.kind_var.set("vars")
                self.value_text.insert("1.0", json.dumps(step[1], indent=2))
            elif step[0] == "select_profile":
                self.kind_var.set("select_profile")
                self.refresh_profile_menu()
                self.profile_var.set(str(step[1]))
            elif step[0] == "sleep":
                self.kind_var.set("sleep")
                self.value_text.insert("1.0", str(step[1]))
            elif step[0] == 2:
                self.kind_var.set("send")
                self.value_text.insert("1.0", str(step[1]))
            elif step[0] == 1:
                self.kind_var.set("spawn")
                self.value_text.insert("1.0", str(step[1]))
            elif step[0] == 3:
                self.kind_var.set("detached")
                self.value_text.insert("1.0", str(step[1]))
        self.update_kind_ui()

    def apply_and_close(self):
        self.result = list(self.steps)
        self.window.destroy()

    def close(self):
        self.result = None
        self.window.destroy()

    def show(self):
        self.parent.wait_window(self.window)
        return self.result

class ChainRunnerWindow:
    def __init__(self, parent, total_steps: int):
        self.window = Toplevel(parent)
        self.window.title("Chain Runner")
        self.window.geometry("820x500")
        self.window.transient(parent)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        self.header_var = StringVar(value=f"Chain Runner — {total_steps} step(s)")

        Label(
            outer,
            textvariable=self.header_var,
            bd=4,
            width=40,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        self.output = Text(outer, wrap="word", height=12, width=90)
        self.output.pack(fill=BOTH, expand=True, pady=(0, 8))

        self.last_run_start_index = self.output.index("end-1c")
        self.log("──", f"New chain run — {total_steps} step(s)")

        button_row = Frame(outer)
        button_row.pack(fill=X, side="bottom", pady=(8, 0))

        Button(button_row, text="Copy Log", width=14, bg="#2f5597", fg="white", command=self.copy_log).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Copy Last Run", width=16, bg="#4b4b88", fg="white", command=self.copy_last_run).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Save Log", width=14, bg="#3d6d3d", fg="white", command=self.save_log).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Clear Log", width=14, bg="#7f6000", fg="white", command=self.clear_log).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Close", width=14, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        self.log("──", f"New chain run — {total_steps} step(s)")

    def exists(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except Exception:
            return False

    def reset_for_run(self, total_steps: int) -> None:
        try:
            self.window.deiconify()
            self.window.lift()
            self.header_var.set(f"Chain Runner — {total_steps} step(s)")

            # Add spacing after previous run if log is not empty.
            if self.output.get("1.0", "end-1c").strip():
                self.output.insert("end", "\n")

            # Mark the start of THIS run before writing its first line.
            self.last_run_start_index = self.output.index("end-1c")

            self.log("──", f"New chain run — {total_steps} step(s)")
        except Exception:
            pass

    def log(self, marker: str, message: str) -> None:
        if not hasattr(self, "output"):
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {marker} {message}" if marker else f"[{timestamp}] {message}"
        self.output.insert("end", line + "\n")
        self.output.see("end")
        self.output.update_idletasks()

    def get_log_text(self) -> str:
        return self.output.get("1.0", "end-1c").strip()

    def get_last_run_text(self) -> str:
        try:
            return self.output.get(self.last_run_start_index, "end-1c").strip()
        except Exception:
            return ""

    def copy_log(self) -> None:
        text = self.get_log_text()
        if not text:
            messagebox.showinfo("Copy Log", "Log is empty.")
            return
        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.window.update()
        messagebox.showinfo("Copy Log", "Full chain log copied to clipboard.")

    def copy_last_run(self) -> None:
        text = self.get_last_run_text()
        if not text:
            messagebox.showinfo("Copy Last Run", "No recent chain run found.")
            return
        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.window.update()
        messagebox.showinfo("Copy Last Run", "Last chain run copied to clipboard.")
        print("LAST RUN START:", self.last_run_start_index)

    def save_log(self) -> None:
        text = self.get_log_text()
        if not text:
            messagebox.showinfo("Save Log", "Log is empty.")
            return
        target = filedialog.asksaveasfilename(
            title="Save Chain Execution Log",
            defaultextension=".log",
            initialfile="termforge_chain.log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not target:
            return
        Path(target).write_text(text + "\n", encoding="utf-8")
        messagebox.showinfo("Save Log", f"Saved chain log to:\n\n{target}")

    def clear_log(self) -> None:
        self.output.delete("1.0", END)

    def step_running(self, index: int, total: int, message: str) -> None:
        self.log("[>]", f"[{index}/{total}] {message}")

    def step_done(self, message: str) -> None:
        self.log("[✓]", message)

    def step_failed(self, message: str) -> None:
        self.log("[x]", message)

    def finished(self) -> None:
        self.log("[✓]", "Chain complete.")

