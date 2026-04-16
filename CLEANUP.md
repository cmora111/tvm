# TermForge Repository Cleanup Guide

This checklist helps keep the repository clean, consistent, and ready for development and distribution.

---

## ✅ Keep (Core Project Files)

These should remain in the repository:

```
pyproject.toml
README.md
LICENSE
docs/
examples/
src/termforge/
```

Inside `src/termforge/`, keep:

```
__init__.py
__main__.py
app.py
cli.py
default_config.py
xdo_helper.py
```

Inside `examples/`:

```
config.py
plugins/hello_world.py
```

---

## ❌ Remove (Generated / Temporary Files)

These should NOT be committed:

*.pyc
```

Specific files to remove:

```
---

## ⚠️ Review (Optional Files)

Decide whether to keep or move:

```
project.html
```

Questions:

* Is this documentation? → move to `docs/`
* Is this temporary? → remove
* Is this part of the app? → keep

---

## 📁 Target Repository Structure

```
termforge/
├── docs/
├── examples/
│   ├── config.py
│   └── plugins/
│       └── hello_world.py
├── LICENSE
├── README.md
├── pyproject.toml
└── src/
    └── termforge/
        ├── __init__.py
        ├── __main__.py
        ├── app.py
        ├── cli.py
        ├── default_config.py
        └── xdo_helper.py
```

---

## 🧹 Cleanup Commands

Run from repo root:

```bash

If files are already tracked by git:

```bash
```

---

## 🛡️ .gitignore

Create or update `.gitignore`:

```gitignore
# Python
__pycache__/
*.pyc
*.pyo

# Packaging
build/
dist/
*.egg-info/

# Virtual environments
.venv/
venv/

# Logs
*.log

# Local config
.config/

# OS/editor noise
*.swp
*~
```

---

## 🔄 Rebuild After Cleanup

```bash
pip install -e .
```

---

## ✅ Final Verification Checklist

Run:

```bash
python -m termforge
termforge
```

Verify:

* App launches
* Window selection works
* Commands send correctly
* Placeholders prompt correctly:

  * `cd <path>`
  * `ssh <user>@<host>`
* Confirmation works on flagged commands
* Plugin Browser loads
* Example plugin runs

---

## 🧼 Optional Improvements

* Move `PLUGIN_API.md` into root or reference it in README
* Ensure `examples/config.py` matches current app format
* Remove outdated README references (e.g., old `xdo` mentions)
* Add screenshots to `docs/` if useful

---

## 🚀 Result

After cleanup:

* Cleaner repo
* Faster installs
* Easier maintenance
* Ready for packaging and sharing

---

