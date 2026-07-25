# 🎨 Anki Multi-Device Responsive Card Studio

An automated toolkit for designing, developing, and testing Anki card templates across multiple devices (**PC Desktop, AnkiDroid Android, AnkiMobile iPhone, iPad Tablet**) with **zero manual copy-pasting**.

---

## ⚡ Quick Start

### 1. Launch the Live Dev Server
Open a terminal in `D:\Projects\Anki_Vocab_Suite\card_design` and run:
```powershell
python server.py
```
Then open your web browser to:
👉 **[http://localhost:8080](http://localhost:8080)**

---

## 🌟 Features

1. **📱 Multi-Device Simultaneous Preview**:
   - See your card design rendered across 4 responsive viewports in real time:
     - 💻 **PC Mode** (720px × 480px)
     - 🤖 **Android Mode** (360px × 740px, AnkiDroid `.card.night_mode`)
     - 📱 **iPhone Mode** (390px × 800px, AnkiMobile `.night_mode` with notch)
     - 📟 **iPad Mode** (640px × 800px)

2. **☀️/🌙 1-Click Theme Switcher**:
   - Toggle between Light mode (`#f9f9fb`) and Anki exact Night mode (`#2f2f31`) across all 4 devices simultaneously.

3. **🔄 Live Auto-Sync (Hot Reloading)**:
   - Edit any HTML or CSS file in `card_design/<ModelName>/` (e.g. `Abstract Words/Styling.css`, `Front.html`, `Back.html`).
   - The previewer polls for changes every 1.5s and automatically updates all device viewports without refreshing the page!

4. **🚀 1-Click Push to Anki**:
   - Click the **"🚀 Push to Anki"** button in the web UI (or run `python push_models.py`).
   - Your local HTML/CSS templates are instantly pushed into Anki's database via AnkiConnect (`updateModelTemplates` & `updateModelStyling`). No copy-pasting ever again!

5. **📝 Live Sample Data Editor**:
   - Edit mock field data (`Word`, `IPA`, `Definition`, `Sentence`, `Synonym`) directly in the sidebar to test word wrapping on small phone screens vs wide desktop screens.
