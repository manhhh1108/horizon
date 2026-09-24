# Horizon X Media Tool — Design Spec

- **Date:** 2026-09-24
- **Status:** Approved (design), pending implementation plan
- **Source documents:** `Facebook_Story_Master_Assistant_System_Prompt_v11.docx` (Master Prompt v11), `Sơ Bộ Workflow.docx`, user requirement prompt.

> Language convention: **UI labels, logs, and user-facing report text in Vietnamese**; **code identifiers, docstrings, and comments in English**.
> Location: source under `D:\Home\wf\horizon_tool\`; git repo rooted at `D:\Home\wf`.

---

## 1. Purpose

A Windows desktop app that batch-processes story scripts. For each script it:

1. Sends a Master Prompt ("Plugin") + the script to **ChatGPT** (logged-in browser, not API) to rewrite the story and produce 9 content sections.
2. Builds a Word file from the result.
3. Renders a 9:16 image and a 16:9 thumbnail via ChatGPT.
4. Feeds the 9:16 image into **Grok** to create a video.
5. Saves everything into an output folder named after the script's ordinal number.

Multi-account rotation handles quota exhaustion; a Resume feature continues interrupted work.

**Out of scope:** editing, rewriting, or augmenting the Master Prompt content. The tool must run with the user's Master Prompt (currently v11) verbatim.

## 2. Tech stack (mandatory)

Python 3.11+ · PySide6 (GUI) · Playwright Chromium via `launch_persistent_context` (one profile dir per account) · python-docx · openpyxl · PyYAML · cryptography (Fernet / AES-GCM) · PyInstaller + PyArmor · stdlib `logging` (file + realtime GUI).

## 3. Architecture decisions (the designed part)

### 3.1 Threading model
- GUI runs on the main thread. **All automation runs on a dedicated worker `QThread`** so the GUI never freezes.
- Worker → GUI communication via **Qt signals** (live log, progress table updates, statistics).
- **Playwright sync API** runs inside the worker thread (avoids asyncio/Qt event-loop conflict).
- **Pause/Stop are cooperative:** the worker checks flags at the boundary of each state-machine step (never kills mid-step, to avoid corrupt state). Pause = stop at the end of the current step; Stop = persist state then exit cleanly.

### 3.2 Pipeline state machine (`core/pipeline.py`)
- States: `PENDING → SCRIPT_WRITING → WORD_BUILT → IMG_9x16 → IMG_16x9 → VIDEO → DONE`.
- Each step yields a result: `done / skipped / rejected / failed`.
- **State JSON is written after every step** (atomic: write temp file, then rename).
- Scripts run **strictly sequentially**. A failed script → log + browser screenshot + move to the next script; a single failure never halts the whole run.
- If `SCRIPT_WRITING` fails, later steps of that script are not attempted.

### 3.3 Everything externalized in YAML
- `config/selectors.yaml` holds every ChatGPT/Grok CSS/XPath selector plus recognition regexes: CONTINUE marker (`[PART X COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]`), quota-exhausted text, policy-refusal text, session-expired text, and the 9 section headings.
- `config/config.yaml` holds general options: Grok duration/quality choices (default 10s/15s/20s, 720p/1080p), timeouts, retry counts/backoff, min–max random delays, `runtime_suffix`, send mode (combined vs two messages), image wrapper command, video motion prompt override.
- **Honest constraint:** real ChatGPT/Grok selectors cannot be known without the user's logged-in sites. Automation selectors (Phases 2–5) ship as **placeholders marked `# TODO: kiểm tra selector thực tế`**, with documented steps to capture real selectors from the live DOM. This part must be iterated against the real machine; no guessed selector will be reported as "working".

### 3.4 Plugin manager (PL-01 → PL-07)
- Reads `.docx / .txt / .md` from `plugins/`; **re-reads the plugin file before every script** (PL-03).
- Computes a content hash each use; plugin name + hash + mtime recorded to log and per-script report (PL-05).
- Variable substitution: `{VIDEO_DURATION}`, `{VIDEO_QUALITY}` replaced with current GUI selections; if absent, plugin sent verbatim (PL-06).
- `.docx → text` conversion preserves line breaks, heading markers, and `**bold**` as Markdown so ChatGPT understands structure.
- In-tool plugin editor (used for the SEC-08 encrypted mode): open/edit/save with auto-backup of the previous version into `plugins/_history/` (PL-07).

### 3.5 Section parser & Word builder
9 sections in Master Prompt v11 order:
1. FULL STORY
2. KEY SCENES + CONTINUITY NOTE
3. IMAGE PROMPT — 9:16
4. THUMBNAIL PROMPT — 16:9
5. VIDEO AI PROMPT
6. FACEBOOK TITLE
7. FACEBOOK VIDEO DESCRIPTION
8. STORY TEASER
9. HASHTAGS

- Flexible heading regex (with/without number, `#`, `**`, upper/lower) declared in YAML.
- Merge all CONTINUE parts into one seamless story; strip `[PART X COMPLETE …]` lines.
- Handles both delivery cases: ChatGPT returns a `.docx` link (download + read to split sections) OR returns text only (split from raw text and build the Word file). Final Word file must contain 9 sections; if ChatGPT's file is short but chat text is complete, prefer the tool-built file.
- Missing sections → warn in log + report, still build Word with available sections.
- Word formatting: Calibri 11–12pt; section titles = Heading 1; story chapter titles (`CHAPTER ONE — …`) = Heading 2; `**bold**` → real bold, keep UPPERCASE; Facebook Title uppercase + bold, own paragraph; Video AI Prompt in monospace (Consolas) indented block; no cover page / TOC / header / footer / page numbers.

### 3.6 Browser core (`automation/browser.py`, shared)
- Opens Chromium with the current account's persistent profile.
- Stable helpers: wait-for-element, click-with-retry, paste long text via clipboard (not per-char typing), wait-for-response-complete (detect Stop button gone / Send button back — selectors in YAML).
- Per-operation configurable timeouts.

### 3.7 ChatGPT automation (`automation/chatgpt.py`)
- **Script writing:** new chat → send plugin then script (combined or two messages, config); optional `runtime_suffix` after the script; on CONTINUE marker auto-send `CONTINUE` and loop until gone; save conversation URL to state for Resume; concatenate all responses into `raw_response.txt`.
- **Image render:** prompt from section 3 (9:16) and section 4 (16:9), each in a new chat; wrapper command from config; download highest-resolution original. **Policy refusal → skip immediately, no retry**, mark "Bị từ chối", log, continue.

### 3.8 Grok automation (`automation/grok.py`)
- Open Grok with the Grok account profile → image-to-video mode (URL/selectors in YAML); upload the 9:16 image; motion prompt from section 5 (or a fixed config prompt); set duration/quality per GUI; wait for render (config timeout, default 10 min); download video.
- If the 9:16 image is missing (refused/error) → **skip the video step**. Refusal/render-error → skip, log, no retry.

### 3.9 Multi-account, quota, Resume (`core/account_manager.py`, `core/state_store.py`)
- Separate pools for ChatGPT and Grok; one profile dir per account; manual login ("Đã đăng nhập xong"); passwords never stored/received.
- Per-account status: Sẵn sàng / Đang dùng / Hết quota (with reset time if readable) / Phiên hết hạn.
- Quota detected (YAML text) → switch to another same-type account with quota and **redo the exact step in progress**. All same-type accounts exhausted → auto-pause, persist state, notify GUI. Optional auto-resume on a configurable cycle (e.g. every 30 min).
- State saved to `state/` after each completed step (atomic temp+rename): which script, which step done, conversation URL, downloaded files. Resume continues at the exact unfinished step, surviving app or machine restart.

### 3.10 Security (Phase 8; slots designed from the start)
SEC-01 no password storage · SEC-02 isolated profile per account · SEC-03 encrypt profiles at rest (decrypt to temp on run, re-encrypt + wipe temp on close; key = hardware ID + license key) · SEC-04 mask sensitive log data (email/token/cookie/session-URL) · SEC-05 randomized delays between steps and scripts · SEC-06 license bound to hardware ID + a separate key-gen script for the seller · SEC-07 PyArmor obfuscation before packaging · SEC-08 optional plugin encryption (default off; `.plugin` files, edited only via in-tool editor, decrypted in memory only, still re-read before each script).

## 4. Input reading (`core/input_reader.py`)
- Read all `.txt` and `.docx` in the input folder (IN-01).
- Extract ordinal from filename (`1.txt`, `Kịch bản 12.docx` → 12); sort numerically ascending, not alphabetically (IN-02).
- GUI range/list selection (e.g. 5–20, or 3,7,9) (IN-03).
- Skip empty / unreadable / no-number files with a logged reason; never halt the run (IN-04).
- `.txt` encoding auto-detection: UTF-8, UTF-8-BOM, UTF-16, cp1258 (IN-05).

## 5. Output, log, report (`core/output_manager.py`)
- One folder per script named by ordinal: `output/1/`, `output/2/` … (OUT-01).
- Filenames: `1.docx`, `1_9x16.png`, `1_16x9.png`, `1.mp4`, `raw_response.txt` (OUT-02).
- Refused image/video → folder keeps only produced files (minimum: the Word file) (OUT-03).
- Existing folder on a fresh run → ask user: Overwrite / Skip this script / New folder with timestamp suffix (OUT-04).
- `log.txt` per session (OUT-05).
- `report.xlsx`: ordinal, input filename, plugin + hash, account used, per-step status (Word / Ảnh 9:16 / Ảnh 16:9 / Video), missing sections, error/skip reason, timing; "Bị từ chối" rows color-highlighted for filtering (OUT-06).

## 6. GUI (`gui/`)
- Choose input & output folders.
- Plugin dropdown + buttons: Mở file / Sửa / Xem trước / Tải lại (refresh list).
- Grok video options: Thời lượng + Chất lượng dropdowns, values from `config.yaml`.
- Per-step checkboxes: Viết kịch bản, Ảnh 9:16, Thumbnail 16:9, Video.
- Start / Pause / Resume / Stop.
- Progress table: one row per script, status columns per step (Chờ / Đang chạy / Xong / Bỏ qua / Lỗi).
- Live log pane.
- Statistics: total, done, skipped, error, elapsed time, current account.
- Buttons to open Quản lý tài khoản and Cài đặt windows.

## 7. Error handling

| Situation | Handling |
|---|---|
| Image refused (policy) | Skip immediately, no retry, log |
| Video refused / render error | Skip, log |
| No 9:16 image | Skip the video step |
| Network down / page not loading | Retry up to N times with increasing backoff (config) |
| Login session expired | Mark account, switch account, ask user to re-login |
| ChatGPT response cut off / stalled | Wait out timeout, try "Continue generating" or send CONTINUE; after N tries mark failed |
| Quota exhausted | Rotate accounts (§3.9) |
| Unknown error | Screenshot browser to output folder, log, move to next script |

A single failed script must never stop the whole run.

## 8. Project structure

```
horizon_tool/
├── main.py
├── config/ (config.yaml, selectors.yaml)
├── plugins/            (+ _history/)
├── profiles/           (per-account browser profiles, encrypted at rest)
├── state/              (resume state JSON)
├── core/ (pipeline.py, input_reader.py, plugin_manager.py, section_parser.py,
│          word_builder.py, output_manager.py, account_manager.py, state_store.py,
│          security/{license.py, crypto.py, log_mask.py})
├── automation/ (browser.py, chatgpt.py, grok.py)
└── gui/ (main_window.py, accounts_window.py, plugin_editor.py, settings_window.py)
```

## 9. Delivery phases (stop for approval after each)

1. **Skeleton + git, config, input reading, plugin management, basic GUI** — runnable & testable without a browser.
2. Browser core, account management, manual login via profile.
3. ChatGPT script writing + CONTINUE + section split + Word build + output/log/report.
4. ChatGPT image render 9:16 & 16:9, refusal detection.
5. Grok video generation.
6. Quota, account rotation, state persistence, Resume.
7. Comprehensive error handling.
8. Security (SEC-01 → SEC-08).
9. Packaging (PyInstaller/PyArmor, first-run Chromium install) + Vietnamese user guide (incl. how to edit `selectors.yaml` when ChatGPT/Grok UI changes).

## 10. Quality requirements
Type hints, docstrings, explicit exception handling, logic decoupled from GUI (automation on its own thread). Uncertain selectors marked `# TODO: kiểm tra selector thực tế` in `selectors.yaml` rather than guessed.

## 11. Known risks / open items
- **Live selectors (Phases 2–5)** must be captured from the real logged-in ChatGPT/Grok DOM; iterate with the user on the target machine.
- ChatGPT `.docx` link download behavior varies; the tool always keeps a tool-built Word file as the authoritative fallback.
- Grok image-to-video UI and option controls are the least predictable; config-driven values reduce churn.
```
