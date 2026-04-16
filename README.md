🖥️ TermForge — Terminal Virtual Macropad
<p align="center"> <b>A programmable macro pad for controlling terminal windows on Linux (X11)</b> </p> <p align="center"> <a href="https://pypi.org/project/termforge/"> <img src="https://img.shields.io/pypi/v/termforge.svg"> </a> <a href="https://pypi.org/project/termforge/"> <img src="https://img.shields.io/pypi/pyversions/termforge.svg"> </a> <a href="https://github.com/cmora111/termforge/blob/main/LICENSE"> <img src="https://img.shields.io/github/license/cmora111/termforge.svg"> </a> <a href="https://github.com/cmora111/termforge/commits/main"> <img src="https://img.shields.io/github/last-commit/cmora111/termforge.svg"> </a> <a href="#installation"> <img src="https://img.shields.io/badge/install-pip%20-e-blue"> </a> </p>
<p align="center"> Build powerful terminal automations with chains, variables, profiles, and plugins. </p>
📸 Preview
<p align="center"> <img src="docs/main.png" width="600"> </p>
⚡ Why TermForge?
<p align="center">
Feature	What it gives you
🔗 Chains	Automate multi-step workflows
🔁 Shared Variables	Prompt once, reuse everywhere
🎯 Window Profiles	Target specific terminals
⏱️ Delays	Precise execution timing
🧩 Plugins	Extend functionality
⭐ Favorites	One-click access to key commands
📜 History	Rerun previous commands instantly
</p>
🚀 Quick Example
'Deploy': ['chain', [
    ['vars', ['path', 'user', 'host']],
    ['select_profile', 'server'],
    [2, 'cd <path>'],
    ['sleep', 1],
    [2, 'git pull'],
    ['sleep', 1],
    [2, 'ssh -T <user>@<host>'],
]]

👉 Prompts once → runs full deployment workflow

🧠 What TermForge Really Is

Not just a macro pad —
a lightweight terminal automation engine with a UI.

🔧 Installation
git clone https://github.com/cmora111/TermForge.git
cd termforge
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m termforge
📁 Project Structure
src/termforge/
    app.py
    cli.py
    xdo_helper.py
    default_config.py

examples/
    config.py
    plugins/
⚠️ Requirements
Linux (X11 — not Wayland)
xdotool
sudo apt install xdotool
🧩 Plugin Example
TermForge_PLUGIN_API_VERSION = 1

def run(app, context):
    app.set_status("Hello from plugin!")
📜 License

MIT

💡 Pro Tip

If you find yourself repeating terminal tasks…

TermForge turns them into one-click workflows.

🔥 Optional next upgrade

If you want to take this even further visually:

👉 I can add:

animated GIF demo (huge impact)
dark/light themed screenshots
“architecture diagram”
PyPI + GitHub release automation
