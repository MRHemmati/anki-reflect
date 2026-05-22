# Anki Reflect

> **A narrative-driven Anki add-on that generates rich, personalized study session reflections — with FSRS metrics, retention trends, and animated growth graphs.**

Anki Reflect hooks directly into your local database (`mw.col.db`) to analyze your daily or weekly study sessions, generating conversational insights and high-quality charts completely offline with zero binary dependencies.

---

## ✨ Features

| Feature | Details |
|---|---|
| 📊 **Session Overview** | Cards reviewed, time spent, avg speed, comparison to previous period. |
| 🎯 **Retention Analysis** | Mature card retention %, correct/total breakdown, and a visual HTML/SVG ring chart. |
| 🔁 **Lapse Tracking** | "Again" press rate with contextual narrative commentary. |
| 🧠 **FSRS Metrics** | Median stability, mean difficulty, Estimated Total Knowledge (expected recall count), and struggling card % |
| 📈 **Growth Graphs** | **Pure Python SVG graphs** (Mature Card Growth, Daily Review Volume, FSRS Stability Distribution). Fully responsive and crisp on Retina/High-DPI screens without requiring `matplotlib` or compiling C-extensions. |
| 💡 **Narrative Insights** | Offline, deterministic Python template engine generating conversational, personalized reflections. |
| 🤖 **Optional LLM** | Plug in an OpenAI or Anthropic key in the config to receive AI-generated narrative reflections. |
| ⬇️ **Export** | Save your study reflections as a standalone HTML file. |

---

## 🚀 Installation & Setup

### Development Setup (from source)
If you've cloned this repository directly into your Anki add-ons folder, or have symlinked it:

```bash
# Symlink this folder into Anki's add-ons directory
ln -s "$(pwd)" ~/Library/Application\ Support/Anki2/addons21/anki_reflect
# (Linux: ~/.local/share/Anki2/addons21/anki_reflect)
# (Windows: %APPDATA%\Anki2\addons21\anki_reflect)
```

Restart Anki to load the add-on.

---

## 🎮 Usage

Once loaded, go to **Tools → Generate Session Reflection** in your Anki menu.

The report will display in a beautiful, dark-mode glassmorphic interface:
- **Session Overview** — key stats at a glance
- **Retention & Lapses** — accuracy and lapse rate commentary
- **Metric Breakdown** — detailed comparison table of current vs previous sessions
- **FSRS Insights** — deep dive into stability distributions and knowledge accumulation
- **Mature Card Growth & Volume** — clean, responsive timeline charts
- **Reflection & Insights** — final motivational commentary

---

## ⚙️ Configuration

Settings can be changed by going to **Tools → Add-ons → Anki Reflect → Config**:

```json
{
  "report_scope": "today",
  "mature_threshold_days": 21,
  "graph_theme": "dark",
  "llm_enabled": false,
  "llm_provider": "openai",
  "llm_api_key": "",
  "llm_model": "gpt-4o-mini"
}
```

- `report_scope`: `"today"`, `"week"`, or `"month"`.
- `mature_threshold_days`: The interval threshold (in days) at which a card is classified as mature.
- `graph_theme`: Choose `"dark"` or `"light"` to match your system aesthetics.
- `llm_enabled`: Enable to generate narrative paragraphs via OpenAI/Anthropic. Requires a valid API key.

See [`config.md`](config.md) for more details.

---

## 🏗️ Structure

```
.
├── __init__.py          # Entry point — registers menu action & hooks
├── manifest.json        # Anki add-on metadata
├── config.json          # Default user config
├── config.md            # Config documentation (rendered inside Anki)
├── _version_info.py     # Version specification
├── data/
│   ├── queries.py       # SQL queries targeting mw.col.db
│   └── fsrs_metrics.py  # FSRS parsing and stats calculation
├── report/
│   ├── builder.py       # Report orchestration pipeline
│   ├── graphs.py        # Offline Python SVG graph generator
│   ├── insights.py      # Conditional narrative engine & LLM api client
│   └── templates/
│       ├── report.html.j2 # Jinja2 HTML report template
│       └── styles.css    # Premium glassmorphic styles
└── ui/
    ├── menu.py          # Action hooks
    └── dialog.py        # PyQt WebEngine window
```

---

## 📜 License

MIT © Mohammad Hemmati
