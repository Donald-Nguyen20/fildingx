# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This file covers the **application codebase**: `Finding8.py`, a PySide6 desktop app for searching plant documents.

The **document-database domain** — the schema of `Databasev3.db`, the VP1 document naming convention and the operation-report workflow — lives in `DATABRAIN.md`. Read that file when asked to answer a question *from the documents* rather than change code. It is not merely documentation: `_load_domain_md()` in `ui/claude_assistant/widget.py` loads it at runtime as the Data Brain agent's system prompt, so editing it changes how the shipped app answers.

## Commands

```bash
pip install -r requirements.txt
python Finding8.py                    # run the app; no CLI arguments; Ctrl+C is ignored, close the window
```

`requirements.txt` does **not** list `claude_agent_sdk`, which `ui/claude_assistant/agent.py` imports. Install it separately if the Data Brain tab fails to load.

**Build (PyInstaller).** The complete, current onedir command lives in the docstring at the top of `Finding8.py` — copy it from there rather than reconstructing it. The three `.spec` files on disk are gitignored and drift, so they are not a reliable source. New modules under `ui/` or `core/` are picked up by Analysis automatically and need no spec change; new *data* files (JSON, the CLI helpers) do.

PyInstaller 6 puts everything listed in `datas` under `_internal/`, but `paths.APP_DIR` is the folder holding the `.exe` — so a file the app opens through `APP_DIR` cannot be shipped through the spec at all. **`DATABRAIN.md` has to be copied beside the `.exe` by hand after the build**; the `--add-data` copy inside the bundle is only the fallback `_load_domain_md()` reaches for when the outer one is missing, so the notes stay editable without a rebuild. The two CLI helpers need no copying — see below. No dist built before this was carried any of them, which is why Data Brain's DB mode had never worked from a packaged build.

OCR recognises text with PaddleOCR's English model, `models/ocr/en_PP-OCRv4_rec_mobile.onnx` (7.6 MB, gitignored — `paths.ocr_rec_model()` says where it comes from). A fresh clone has to fetch it; without it OCR falls back to RapidOCR's bundled Chinese recogniser, which runs English words together, and Create DB's OCR notice says the model is missing. The build ships it with `--add-data "models/ocr;models/ocr"`.

**There is no test suite, no linter and no packaging config.** No `pytest`, `pyproject.toml`, `setup.cfg` or `tox.ini` exists anywhere in the tree. Do not invent a test command. The two checks actually used here are:

```bash
python -c "import ast; ast.parse(open('ui/main_window.py', encoding='utf-8').read())"   # syntax
python -c "from ui.main_window import FileSearchApp; print('ok')"                       # import smoke test
```

The app is normally running live under the VS Code debugger while you work — never kill stray `python.exe` processes without checking which one it is.

**OCR changes are measured, not tested.** `ocr_bench.py` reads a fixed set of text-layer pages (and any drawing sheets you name) the way Create DB does and prints the share of words read, the full KKS tags found and the seconds per page. Run it before and after touching `core/ocr_engine.py`, `core/kks.py` or the OCR paths of `core/create_index_v3.py`, with the app's own build stopped so the GPU is free:

```bash
python ocr_bench.py --docs "<folder of PDFs>" --sheet "<P&ID.pdf>=<drawing no>" --register "<sqlite with kks_xref>"
```

The page choice is kept in `ocr_bench_set.json` (gitignored) so runs compare like with like. On an RTX 4060 the last measurement was A4 98.2% at 0.7 s a page, A3 93.9% at 2.0 s, and the MAW P&ID at 600 dpi 17 of its 18 printed tags in 17 s. Differences under about 10% in time are run-to-run noise.

**The two read-only CLI helpers.** These exist so the Data Brain agent can drive them through `Bash`, and they are also the fastest way for you to inspect the data yourself:

```bash
python db_query.py "<db path>" "SELECT ..."       # SELECT only; opens file:...?mode=ro
python logic_query.py cpus  <dcs_folder>
python logic_query.py find  <dcs_folder> <signal>
python logic_query.py why   <dcs_folder> <signal>   # what makes this signal go true
python logic_query.py tree  <dcs_folder> <signal>
python logic_query.py trace <dcs_folder> <signal>
```

Each prints exactly one JSON object on stdout; failures print `{"error": ...}` and exit non-zero. Signals are addressed by name or by `ref` = `"<db file>|<sheet>|<net>"`.

A packaged build ships no `python.exe`, so `python db_query.py …` cannot run there. The exe dispatches both scripts itself: `Finding8.py` checks for `--db-query` / `--logic-query` before Qt is imported and hands the remaining arguments to the same `main()`, and the literal `import db_query` / `import logic_query` in that block is also what makes PyInstaller bundle them. **Prompts must build the command from `paths.db_query_cmd()` / `paths.logic_query_cmd()`**, never spell out `python db_query.py`, or they break in the frozen app. Both return the `python …` form from source, so the scripts stay usable on their own and dev behaviour is unchanged.

## Architecture

### The shell

`Finding8.py` sets `PLAYWRIGHT_BROWSERS_PATH` when frozen, then hands everything to `FileSearchApp(QMainWindow)` in `ui/main_window.py`. `_setup_body()` builds three regions:

- a fixed 80 px `QFrame#sidebar` — three *checkable* panel buttons (Containers / Tools / Add-ons) plus a *non-checkable* **Config LLM** button. That last button is deliberately excluded from `_sidebar_btns` / `_sidebar_icons` so it never latches or lights up green; keep it that way.
- `self._search_tabs` — four tabs in order: **File Search** (built inline), **DB Search** (`ui/index_search_window.py`), **NotebookLM** (`ui/notebooklm_window.py`), **Data Brain** (`ui/claude_assistant/widget.py`).
- `self._right_stack` — a `QStackedWidget` whose pages 0/1/2 are containers / tools / exe add-ons, revealed by the sidebar buttons.

`core/` is UI-free logic and should stay importable without Qt; the exceptions are `core/workers.py` and `core/ai_grouper.py`, which own the `QThread` workers. `ui/` is all PySide6.

**Never hardcode a path.** `paths.py` defines every one, and `get_app_dir()` returns `os.path.dirname(sys.executable)` when frozen but the module directory otherwise. A hardcoded path works in development and breaks the packaged exe silently.

### One database schema, read by two tabs

This is the most important structural rule in the repo.

| Tab | Config file | Database | Access |
|---|---|---|---|
| **DB Search** | `db_list.json` | a Create DB database — `files_fts` / `chunks_fts` phrase search plus `LIKE` on the name, `kks_tags` for a typed tag, `chunks.page_start/page_end` for the Pages column and `doc_revisions` for Rev / "Latest revision only"; always `name != 'BASE_PATH'`, `_RESULT_LIMIT = 500` | read-only |
| **Data Brain** | `claude_db.json` | a Create DB database plus a `dcs_folder` of Toshiba DCS CAD databases | read-only |

Both tabs read the schema `core/create_index_v3.py` writes (Tools → Create DB), so one file can serve both; the two config files stay separate and may point at the same database. This replaced, on 2026-10-22, the old split in which DB Search read the simple `create_index2.1.py` schema of `AB Drawings.db`.

DB Search **refuses** a database that lacks `chunks`, `doc_revisions`, `kks_tags`, the two FTS tables or the chunk page columns — `AB Drawings.db`, and any Create DB build from before those were added — with a message to rebuild it (into a new file, or with *Incremental* unticked, since an incremental run leaves already-indexed files without pages or tags) and an offer to drop it from `db_list.json`. Do not add cross-schema detection or a "limited mode" that searches such a database in part. Always open with `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` and never write: `AB Drawings.db` is still the live daily database, and the DCS databases are the plant's design masters.

The KKS tag pattern lives in `core/kks.py` (unit prefix `00`/`10`/`20` only), shared by the indexer and DB Search so a typed tag is read exactly as it was stored. `kks.search_globs()` turns a typed tag into `kks_tags.tag_norm` patterns: any spacing or dash, and a tag typed without its unit (`MAW85 AA001`) stands for it on every unit, one indexed pattern per prefix.

**Both search boxes run one query**, `core/fts_search.py` (Qt-free): DB Search's keyword mode and the Create DB window's own search. A keyword is found as a phrase in the FTS index (words together and in order, across line breaks and dashes, last word a prefix), in a file name by `LIKE`, or as a KKS tag; after those, marked `loose` and shown in grey italics, come files holding every space-separated term apart. Keep the two boxes on it — they used to disagree, one matching every word anywhere and the other a raw `LIKE` substring that missed a phrase split by a line break. The measurements behind the choice are in the module docstring.

DB Search shows Name, System, Rev, Source and Pages (the path is the Name tooltip); its columns can be resized and dragged, and a header click sorts (names naturally, Pages by how many pages hold the keyword); each new search starts back in relevance order. Both result tables take the **Source** label (OCR / Text+OCR / Text / Scanned), its colour and tooltip, and the **Pages** text from `core/doc_source.py`, which is Qt-free. `files.ocr` counts the pages read by OCR; a database built before it has no such column, so `doc_source.ocr_column()` selects NULL and its scans show as "Scanned/OCR". That is a display fallback for one optional column, not a limited mode — the required-schema refusal above still applies. `ui/index_search_window.py` keeps its query layer (`search_database`) Qt-free, and fetches `_RESULT_LIMIT + 1` rows so it can tell the user there are more results than it is showing.

### `ui/dcs_logic/` is a vendored copy

It is a verbatim copy of `T_Designer_Lite/core`, kept unmodified so upstream fixes can be re-copied rather than re-merged. **Do not refactor, restyle or tidy anything inside it.** Only `__init__.py` is local. Two deliberate departures from upstream, both documented in place:

- `dbreader.connect()` opens `file:...?mode=ro` — the design masters are never written.
- `project_index` writes its index to a caller-supplied `out_path=` under `APP_DIR`, hashed per DCS folder, instead of the shared `~/.tdesigner_index.db`.

The importer, the Qt UI, the symbol geometry and the simulators were deliberately left behind. Entry points `logic_query.py` uses: `project_index.find`, `cond_tree.formula` / `build` / `blockers`, `signal_graph.trace_project`.

### The LLM layer

- **`core/llm_config.py` is the one place a default model name may live.** The three names originally shipped had all been withdrawn and were 404-ing from six separate call sites; `LEGACY_MODEL_REPLACEMENTS` now silently upgrades retired names on load. Vision defaults are separate (`DEFAULT_VISION_*`) because Groq serves no image-input model. The config file resolves next to the exe when frozen, else the repo root; writes are atomic (tmp + fsync + `os.replace`); loading never raises — it falls back to `DEFAULT_CONFIG`.
- **`core/llm_client.py`** — four providers (`ollama`, `openrouter`, `groq`, `gemini`) behind `create_llm_client(provider_key, model_override="")`. The token budgets near the top each carry a comment recording the *measured* reason they are what they are (reasoning models spend the same budget on hidden thinking; Groq's free tier reserves prompt + `max_tokens` up front and returns HTTP 413). Change them only against a new measurement.
- **`core/ai_grouper.py`** — grouping is split on purpose: duplicate detection is deterministic and fully offline via `core/doc_naming.py` (`classify`, `duplicate_sets`), and only "what is this about" goes to a model. `_build_note()` reports a partial grouping rather than failing.
- **`ui/claude_assistant/agent.py`** switches its tool set on mode: with a `db_path` or `dcs_folder` set it gives the agent `["Bash", "WebSearch", "WebFetch"]` so it drives `db_query.py` / `logic_query.py`; otherwise `["Read", "Glob", "Grep", ...]`. An explicit `allowed_tools=` overrides both, which is how **Web Ask** gets `["WebSearch", "WebFetch"]` and nothing else even while a DB is loaded — see `_web_options` in `ui/claude_assistant/widget.py`.
- **`ui/claude_assistant/cli_locator.py`** is the one place the Claude Code CLI is found. A packaged build carries no `claude.exe`, so on any other machine it comes from the native installer (`%USERPROFILE%\.local\bin`, probed by path so no restart is needed) or from the `claude.exe` inside npm's package. npm's `claude.cmd` shim is never used: the SDK refuses to spawn it. The Login button, the sign-in badge and every `ClaudeAgentOptions` (`cli_path=`) take the same path, so a machine cannot sign in through one CLI and ask through another. Do not tell users to `npm install` on Windows.
- **`ui/claude_assistant/web_research.py`** is the Web Ask mode: the research/citation contract on one side, and on the other the audit that checks it. `ui/claude_assistant/worker.py` emits `tool_call(name, input)` beside `tool_used(name)`, the widget records every call in `_tool_calls`, and `tool_urls` / `audit` compare the URLs in the answer's `SOURCES:` block against the pages `WebFetch` actually opened. A model will credit a figure to a URL it only saw in a search snippet, so each source card says whether its page was really read, and the prompt is told the audit exists. The module is Qt-free on purpose — it is text in, text out, so the parser can be exercised from a plain script.
- `llm_config.json` holds the API keys and is gitignored. Never print a key value — report it as `<set, N chars>`.

### Theming and icons

- `ui/themes.py` holds **8** themes (0 Metal Blue … 7 Daylight). `_current_index` is module-level and **not persisted**, so every launch starts on **5 Arctic**, the ice-blue one. The only way to switch is the hidden keyword `@colour0`…`@colour7` typed into the Keyword box (matched in `ui/main_window.py` around line 821). There is no visible picker.
- Three surfaces, three questions, and a theme may answer them separately: `is_light()` for the frame (toolbar, sidebar, buttons), `light_page()` for the content page (tree, text views) and `light_bar()` for the window behind the tab bar. Arctic answers False / True / True — a near-white window framing a white page while wearing the dark frame. A theme may also carry its own `"chrome"` dict, which `chrome()` merges last and which beats all three; Arctic uses it for its sidebar.
- The theme QSS styles the results-tree body too, and its background is **white under Metal Blue, Arctic and Daylight but dark under the other five** — any fixed colour chosen against a white tree will fail on the dark ones.
- `ui/icons.py` embeds 25 monochrome Lucide SVGs. **Qt does not resolve SVG `currentColor` — it renders black.** Icons are tinted by painting the shape, then `QPainter.CompositionMode_SourceIn` + `fillRect(colour)`. That is why every call site passes an explicit colour.
- Which colour depends on the surface. *Themed* widgets live under `self.main_widget` and follow `themes.ink()`. *Native* surfaces — `QMenu`, `MultiFolderDialog`, anything parented straight to the `QMainWindow` — are light Windows surfaces and must use the fixed dark `icons.INK_NATIVE`.
- **A widget's own `setStyleSheet` overrides the theme QSS** applied to `main_widget`. This is why parts of the chrome stay blue in every theme.
- `HudPanel` in `ui/hud_widgets.py` is never instantiated, so all seven `"hud"` dicts in `ui/themes.py` are dead configuration.

### The File Search keyword DSL

The keyword box is a small language implemented in `core/search_engine.py` and `core/percent_exclude_search.py`:

| Input | Meaning |
|---|---|
| `A,B` | name contains A **or** B (any number of comma-separated terms) |
| `A%B` | contains A, does **not** contain B |
| `A*B` | contains both, in either order |
| anything else | case-insensitive substring |

### Runtime state

Almost every file the app writes is gitignored — the repo is code only: `containers_data.json`, `container_parents.json`, `db_list.json`, `claude_db.json`, `llm_config.json`, `gsheet_config.json`, `sync_config.json`, `file_stats.json`, `synonyms.json`, `summaries.json`, `exe_addons.json`, `nlm_source_map.json`, plus all `*.db`, `images/`, `mindmaps/` and `reports/`. (`ui_state.json` is the one that *is* tracked.) Reach them through `paths.py` and assume they may be absent.

## Conventions

- **Write new code, comments and UI strings in English.** Much of the existing code and its docstrings are Vietnamese; leave what you are not otherwise touching alone, but do not add new Vietnamese.
- PySide6 traps that have bitten this codebase before: compare `item.checkState(0) == Qt.Checked` (never wrap it in `int()`); guard checkbox handlers with the `self._blocking` flag or they loop; `QPushButton.clicked` passes a `bool checked` argument, so connect with `lambda:` when the slot takes none.
- Files are CRLF in the working tree (`core.autocrlf=true`). When writing Python that rewrites a source file, use `io.open(..., newline="\r\n")`.
- The console here is cp1258 — a script that prints Vietnamese or emoji needs `sys.stdout.reconfigure(encoding="utf-8")`.
- Git: the working branch is **`new-layout`**, not `main`. `origin` is a **public** GitHub repo — plant PDFs and the vendor-manual-derived `macro_catalog.json` / `macro_manual.json` must never be pushed, and are gitignored. Never `git add -A` or `git add .`; stage named files.

## About `CODEBASE.md`

There is a second architecture document, `CODEBASE.md`, in Vietnamese. It is useful background but **verifiably stale**: it documents a `core/rag/` package and a root `vector_store_builder.py` that do not exist, says "6 bộ màu" where `ui/themes.py` has 7, and predates `ui/claude_assistant/`, `ui/dcs_logic/`, `ui/icons.py`, `core/ai_grouper.py`, `logic_query.py` and `db_query.py`. Prefer this file, and verify anything you take from `CODEBASE.md` against the code.
