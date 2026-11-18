# StarVault · 星匣

[简体中文](README.md) | **English**

**Your AI memories always belong to you.**

**[Project site](https://stardreamtech.github.io/projects/starvault/)**

StarVault helps you take your AI conversations with you when moving to a new computer or handing over work. Collect existing local records into a searchable, readable archive, export the archive to an external drive, and open it on another computer. Save images, attachments, and Skills when you need them.

Previously named Chat History Vault, the software is published at [StarDreamTech/StarVault](https://github.com/StarDreamTech/StarVault). Conversation backups use a separate private repository that you configure yourself. Both `starvault` and `chat-history-vault` commands work; Python modules, the MCP server identifier, Skill identifiers, and data directories retain their existing names for compatibility.

The desktop app's “Settings & Help → View source” opens the public software repository. “About & Feedback” includes repository and issue links. Feedback is public: do not include private conversations, attachments, or credentials.

<p align="center"><img src="assets/starvault-256.png" width="128" alt="StarVault icon: a star falling into a vault"></p>

## Install with Homebrew

```sh
brew tap cpython666/tap
brew install starvault                # CLI, MCP, and user Skill; macOS / Linux
brew install --cask starvault         # Desktop app; currently Apple Silicon macOS
starvault --help
open -a StarVault
```

The desktop Cask also installs the CLI and Python backend. Tool code and icons are bundled with the app. The initial macOS app is signed locally with an ad hoc signature; it is not signed with an Apple Developer certificate or notarized. If macOS blocks it, verify the source before allowing it in System Settings → Privacy & Security. Intel macOS, Windows, and Linux desktop users currently build from source; downloadable native installers are not available for those platforms.

See [GitHub Releases](https://github.com/StarDreamTech/StarVault/releases) for source packages, versions, and installers. The public software repository contains no conversations. Backup synchronization checks that its destination repository is private.

If a newer Homebrew version reports that the tap is untrusted, review the [Formula and Cask](https://github.com/cpython666/homebrew-tap). You can trust this product specifically with `brew trust --formula cpython666/tap/starvault` and `brew trust --cask cpython666/tap/starvault`, then continue installation.

Archive local conversations from Codex, Claude Code, Claude App, WorkBuddy, OpenClaw, and DeepSeek Harness, plus imported ChatGPT conversations. Claude App coverage includes ordinary conversations already saved locally, imported Code sessions, and cached Projects messages. **GitHub synchronization uploads conversation text and classification indexes only. Raw message records, attachments, commands, and logs stay local.**

- The software repository's `main` branch contains tool code. The conversation branches below belong in your separately configured private backup repository.
- `<device>-codex`: this computer's Codex CLI conversation text and index.
- `<device>-claude`: this computer's Claude Code conversation text and index.
- `<device>-claude-desktop`: local sessions, existing imported copies, and cached Code Projects messages from Claude / Claude-3p desktop directories, retaining their original source and coverage markers.
- `<device>-workbuddy`: this computer's WorkBuddy conversation text and index.
- `<device>-openclaw`: this computer's OpenClaw conversation text and index.
- `<device>-dsh`: this computer's DeepSeek Harness conversation text and index.
- `<device>-chatgpt`: imported ChatGPT conversations, stored separately.
- Local `images/`: original PNG/JPEG/GIF/WebP files, deduplicated by SHA-256 content hash, without compression or upload.
- Local `attachments/`: optional copies of GLB, Blend, documents, code, and other files, deduplicated by content while retaining older versions.
- Local `skills/`: ZIP snapshots of complete Skill folders, their sources, and version history. These remain local.
- Local `records/<device-tool>/<session>/`: dialogue JSONL, original metadata, file associations, and optional command logs. Text-only imports do not retain full event snapshots or resource binaries. Projects retain text versions and relationships in `project-state.jsonl` so merging can continue after the cache disappears. With full snapshots enabled, Claude App local sessions, OpenClaw, and DeepSeek Harness retain `source.jsonl`; compressed Codex sessions retain `source.jsonl.zst`.

Requirements: Python 3.9+; backups require Git, and private repository synchronization requires GitHub authentication. No third-party Python package, Git LFS, or database service is mandatory. To decode zstd content from Codex, DeepSeek Harness, or OpenClaw, the tool tries Python 3.14+ standard-library support, the optional `zstandard` package, system or Homebrew libzstd, then the `zstd` command. If none is available, it reports that the source cannot be read instead of silently skipping it.

MCP queries against an existing archive need only Python 3.9+. You do not need the desktop app, third-party runtime dependencies, or a GitHub login.

## Unified command line

`chat-history-vault` provides backup, queries, attachment and Skill migration, and the MCP server through one entry point. It needs Python 3.9+ and uses the standard library at runtime; backup operations also require Git, and private synchronization requires GitHub authentication. Install it in a separate virtual environment to avoid conflicts with other Python software.

From the repository root on macOS / Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
chat-history-vault --help
chat-history-vault --version
```

On Windows PowerShell, run the virtual environment's executables directly without changing the script execution policy:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\chat-history-vault.exe --help
.\.venv\Scripts\chat-history-vault.exe --version
```

Without activating the environment, replace `chat-history-vault` below with `.venv/bin/chat-history-vault` on macOS/Linux or `.\.venv\Scripts\chat-history-vault.exe` on Windows. The same interpreter supports `python -m chat_history_vault`; from the source directory, `python3 -m chat_history_vault` works directly. Existing `vault.py` and `vault_mcp.py` entry points remain available. Installation does not configure an MCP client, create scheduled tasks, or install the desktop app. Desktop backend discovery still uses `CHAT_HISTORY_VAULT_TOOL`, described below.

```sh
# Backup and migration retain their existing arguments; see new-computer setup for init.
chat-history-vault export                   # Local backup only
chat-history-vault import-local --archive /path/to/backup --tools codex,claude-desktop  # Manual incremental import; text only, no Git required
chat-history-vault import-local --archive /path/to/backup --tools codex --resource-kinds images,documents  # Selected attachments without full snapshots
chat-history-vault transfer-archive --archive /path/to/backup --plan  # Check archive and export size
chat-history-vault transfer-archive --archive /path/to/backup --destination /path/to/drive  # Create a portable archive folder inside this parent directory
chat-history-vault cleanup-text --archive /path/to/backup --plan  # Estimate space held by archive resource copies
chat-history-vault cleanup-text --archive /path/to/backup         # Remove resource copies, retaining text; leave source app files unchanged
chat-history-vault sync --tool codex        # Commit and push to the configured private repository
chat-history-vault attachment-policy --kinds none   # Future backups copy no extra attachments
chat-history-vault attachment-policy --kinds images # Also copy images in future backups
chat-history-vault attachment-policy --kinds images,documents,models
chat-history-vault migrate --kinds models,logs --plan
chat-history-vault skills --archive "/path/to/backup" --defaults --plan

# Query an existing archive without init or GitHub authentication.
chat-history-vault call vault_status --archive "/path/to/backup"
chat-history-vault search "Windows migration" --archive "/path/to/backup" --limit 10
chat-history-vault read MyLaptop-codex SESSION_ID --archive "/path/to/backup" --format dialogue
chat-history-vault attachments MyLaptop-codex SESSION_ID --archive "/path/to/backup"
chat-history-vault tools
chat-history-vault mcp --archive "/path/to/backup" --print-config
chat-history-vault skill-path
```

`search`, `read`, `attachments`, `call`, and `tools` output UTF-8 JSON, write diagnostics to stderr, and return a nonzero exit code on failure. `search` supports `--tool`, `--project`, `--device`, and `--archived all|yes|no`. Queries and lists paginate with `--offset` and `--limit`; continue from the returned `next_offset`. `read` offsets and lengths count characters, with `markdown`, `dialogue`, `manifest`, and `operations` formats. `status` shows saved configuration and the previous backup result; use `call vault_status` for archive counts and source statistics.

`call TOOL` accepts `--arguments` or `--arguments-file`. Calling a write tool requires `--allow-write`. `mcp` accepts the existing `vault_mcp.py` options; running `chat-history-vault mcp` directly waits for a client over standard input/output. Explicit commands such as `export`, `sync`, `migrate`, and `skills` retain their behavior and do not require that flag. Run `chat-history-vault COMMAND --help` for complete options.

The configuration directory is selected in this order: `CHAT_HISTORY_VAULT_CONFIG_DIR`; the source directory's `.local/` when a `.git` directory or `.local/config.json` exists; otherwise `~/Library/Application Support/ChatHistoryVault/tool/.local/` on macOS or `~/ChatHistoryVault/tool/.local/` on Windows/Linux. Configuration, import caches, locks, and runtime status share this directory and are not written into the Python installation. Generated MCP configurations and newly installed macOS scheduled tasks carry the selected configuration directory. CLI upgrades and reinstalls do not migrate or delete existing archives. Backend regression tests use temporary data in macOS / Windows / Linux CI; real source-app data has been checked locally on macOS only.

## Rust desktop reader

`desktop/` is a native Rust + egui reader that opens the same local archive without a web server. It supports:

- A default “Chat archive” workspace with client filters, a session list, and conversation content. “Incremental import” and “Backup & Migration” remain available at the top. Migration follows three steps: collect local records, export an archive folder, then open that folder on another computer. Storage, attachments, and Skills have supporting entries.
- A three-column layout for filters, projects/sessions, and the timeline or conversation, with light toolbars, muted sidebars, and the gold StarVault mark. Source rows show session counts. Filters and lists resize and scroll independently, leaving reading room in narrow windows.
- Full-text search at the top of the session column. All search terms must match. Focus it with `Cmd+K` on macOS or `Ctrl+K` on Windows/Linux.
- Persistent source, update-time, computer, and project filters. The six local client categories remain visible even without archived sessions; ChatGPT appears when imported records exist. Model, session type, and original tags are under “More filters”. Remove individual active filters or clear them together; clearing preserves search text and the archive-status tab.
- Recent, project-grouped, and timeline views. Expand projects to see sessions; pinned Codex projects and sessions appear first. Each view retains unarchived, archived, and all tabs.
- Claude App Projects navigation by recovered project names, separately from working-directory projects. Keep the main conversation in the center and searchable discussions or the selected thread in a separate right panel. Both columns resize and scroll independently; close a discussion or expand its column. Narrow windows switch to one column. Follow discussion and cross-thread references, then return to the root message. Main messages without discussions do not create empty thread entries, and missing bodies are not invented.
- Project names and discussion titles recovered from locally saved Claude navigation records, with cached starting events as a fallback for thread titles. Recovered names survive sign-out and cache clearing. Unrecovered projects show an unnamed label with the channel ID's last eight characters. Names represent the last observed state; session titles are not used to guess project names or notes.
- Shared root-message identity between Projects main conversations and discussions, allowing deduplicated timeline navigation to the correct original text. Channels, client products, and computers stay isolated. Older cache archives upgrade incrementally, and observed history survives missing caches. Only verified local cache message formats are supported; coverage is not the account's complete Projects history.
- Parent, child-agent, and fork navigation for Codex / Claude Code, using explicit source relationships within the same computer and source. Codex forks also show their origin. Missing parents are marked. Older archives gain relationships on a subsequent manual incremental import when source records remain available.
- Project timelines combining sessions into request, decision, outcome, problem, and fix nodes. Filter node types, change time order, and jump to the original message. Session filters also apply.
- Markdown, code blocks, tables, local original images, and a choice between illustrated and text-only reading.
- The last assistant reply in a turn shown by default, with earlier replies under an expandable process-replies control. User questions remain visible. Expanding restores the original order. No new summary is generated; full-copy includes all text, and timeline navigation expands hidden replies when needed.
- Compact left-aligned session lists and centered, width-limited content. Archived sessions have an outlined archive icon with status on hover. Human questions use subtle right-aligned bubbles; assistant messages retain source labels, local timestamps, and individual-copy actions. Pure environment or project context is collapsed; mixed messages containing actual questions remain expanded. Original Markdown is preserved.
- Folding of confirmed Claude `isMeta` injections into agent collaboration, Skill, or session context. Tool screenshots remain associated images. Complete `<wake>` notifications containing one human question show that question directly while keeping the wrapper under message-source details. When raw records are missing or cannot be matched, messages remain ordinary content; classification is not guessed from position.
- A fixed migration entry at the bottom of the session column. Long filter values, project names, and session titles are truncated to one line with full text on hover. Archive location appears on the migration home page.
- Real user requests used as display titles when environment tags or project instructions occupy the original title. The original remains under “More → Session information”. Expanded context shows working directory, shell, date, and timezone, with the full tagged text available to view and copy.
- Rounded image thumbnails up to 320 × 240 by default, preserving aspect ratio without cropping. Click for a window-fit, original-size, or zoomed preview; close with Esc or the backdrop.
- Manual collection from six selectable local sources, text only by default. Claude App includes ordinary local chats, imported Code copies, and Projects. Optional ChatGPT JSON / ZIP import is inside the collection dialog and uses an export file you already have; it does not scan a local ChatGPT app or sign in. The session-list `↻` only reloads the archive.
- Storage estimation and confirmed cleanup of StarVault resource copies while preserving text and Projects incremental state. Original application files remain unchanged; selecting text-only mode does not automatically remove existing copies.
- Settings with category navigation on the left and independently scrolling content on the right. Image display and sharing remain fixed categories.
- “More → Copy complete conversation”, “More → Locate session file”, and an attachments/activity panel for files, tool logs, and raw messages.
- Skill collection, size estimation, incremental backup, and restoration to a selected folder under “Backup & Migration → Skill backup & restore”.
- Thumbnail sizing and a separate image folder under “Settings & Help → Image display settings”. Paste or browse to a path and apply it with a preview. The default is the archive's `images/`; external-drive folders work too. Settings persist locally.
- Separate empty states for loading, no filter matches, and a new archive, with relevant clear-filter or choose-folder actions.
- Index refresh every minute, lazy image loading, and release of the previous session's image cache when switching sessions.

Reading and migration do not modify original conversations or execute historical commands. Attachment migration copies selected local files; ChatGPT import processes files locally. Collection and archive export require no GitHub account, upload nothing, and create no automatic task. `sync` is a separate explicit operation. `--check` validates an archive index without opening a window.

To move computers, first check the archive and export size, then select a destination. StarVault creates a new folder containing collected source text, raw-message manifests, existing image/attachment copies, and Skill versions. Export ignores reader filters and does not fetch more source data. It excludes Git history, local configuration, and caches. Failed exports do not publish incomplete folders or overwrite the current archive. Copy the entire exported folder to the new computer and select “Open existing archive”. No extraction or original-account login is required. This is a searchable reading archive; it does not restore conversations into their original clients for continued chatting.

Manual import saves `.import-policy.json` in the archive root with selected sources, text-only mode, full-snapshot preference, and manual mode. Subsequent `all` operations honor those sources, and explicit `export` / MCP backups still import incrementally. In manual mode, `sync` synchronizes existing text without scanning source apps, copying their data, or automatically backing up Skills. Text-only mode disables automatic attachment preferences; explicit attachment migration remains available. Select images, documents, code, models, logs, and other files independently. CLI `--resource-kinds images,documents` copies selected types; add `--source-snapshots` to retain full event snapshots. Log extraction requires snapshots and enables them with an explanation in the UI. Legacy `--with-resources` remains compatible with full snapshots and existing attachment preferences. Archives without a new policy retain their existing export behavior.

Without full snapshots, uncompressed Claude App sessions and DeepSeek Harness JSONL are read directly, reducing temporary full-file copies. If a source changes during reading, the existing archive is preserved and a retry is reported. Incremental checks include file identity and state, detecting same-size replacements even when modification time is restored. Changed sessions are parsed in full, rather than by reading only an appended tail. Switching to text-only mode reuses unchanged archives and leaves existing resources and snapshots intact. Progress shows source, phase, update count, and elapsed time. Ordinary reading starts without waiting for timeline processing; timelines are generated incrementally in the background when opened.

Cleanup removes only recognized `source.jsonl*` copies and hash-named image/attachment objects in the archive. It first validates all text, session identities, directory boundaries, and Projects state. Missing, corrupt, or linked directories block cleanup. Text and project state are preserved before resource deletion, and interrupted cleanup can be retried. Resources found only in removed copies cannot subsequently be recovered from StarVault; image references and source associations remain.

On startup, the app checks the [latest stable StarVault release](https://github.com/StarDreamTech/StarVault/releases) in the background. A new version triggers a prompt; downloading starts only after you select “Download and install”. Downloads are verified before installation: use a matching minisign release signature when available, otherwise the release's `SHA256SUMS`. Failed verification prevents installation. Network failures do not interrupt reading. Manual checks are available in the management and about menus. Set `STARVAULT_DISABLE_UPDATE=1` to disable automatic checks.

On macOS, an installed `StarVault.app` exits after verification; a temporary script waits for the process, replaces the app with `ditto`, and reopens it. An invalid code signature cancels replacement. Unsigned packages still require valid `SHA256SUMS`. Windows updates work when a release supplies `StarVault-<version>-windows-x64.zip` with `chat-history-vault.exe` at the root or inside one top-level folder: the updater waits for exit, copies files to the program directory, and restarts. Linux, Intel Mac, source builds, and platforms without a matching package direct you to Releases. Published desktop packages are currently Apple Silicon macOS, locally signed and not notarized.

Develop and preview in the public StarVault software repository; your private backup repository stores conversations. These root-level shortcuts require Rust and npm, but no npm dependencies:

```sh
npm run preview           # Build and launch the current source
npm run preview:timeline  # Open the timeline
npm run preview:migration # Open backup and migration
```

They invoke Cargo and read the configured local archive without exporting source sessions or synchronizing backups.

Build on macOS with Rust 1.88+ and Xcode Command Line Tools:

```sh
cd desktop
cargo test --locked
python3 build_macos.py --output "$HOME/Applications"
open "$HOME/Applications/StarVault.app"
```

The built `.app` can run directly; reading does not require Python. Import, attachment/Skill migration, and incremental backups use local Python and `vault.py`. To run from source, use `cargo run --release --locked` inside `desktop/`. Windows/Linux use the same command; Linux also needs its distribution's graphical development dependencies. If moving the reader separately, set `CHAT_HISTORY_VAULT_TOOL` to the local tool-code directory or `vault.py` path.

Select another migrated archive from the command line:

```sh
cargo run --release --locked -- --archive /path/to/backup
cargo run --release --locked -- --archive /path/to/backup --timeline
cargo run --release --locked -- --archive /path/to/backup --check
```

The desktop reader uses system CJK fonts without bundling font files; images come from the archive. The macOS build has been checked locally. Windows/Linux desktop packaging has not been verified.

Images retain their hash-based filenames, so moving the image folder does not require editing conversations. Keep the filenames unchanged; selecting a folder cannot reconstruct originals that were already missing. Paths may contain spaces, Chinese characters, and parentheses. You can also set `--images /path/to/images`.

Project grouping retains computer and tool boundaries. Codex prefers explicit project ownership, project IDs, and pinning; older records are matched against known project roots, with unmatched sessions left ungrouped. Claude Code, WorkBuddy, OpenClaw, and DeepSeek Harness use their original working directories. Identically named projects at different paths remain separate. Records without an archive flag appear in the unarchived tab with unknown status. Reader filters never change archive status in the original application.

Timelines use those same project boundaries, local classification rules, and excerpts from original conversations. No language model generates semantic summaries. Nodes retain source-message links; verify actual progress against the original text. Pure environment context and code examples are excluded from key nodes. Missing message timestamps are shown as unknown.

## Share StarVault

“Settings & Help → Share StarVault” provides Chinese and English copy and product images. Copy is available as a short recommendation or product introduction. Three image themes cover overview, moving computers and data ownership, and preparing history for AI. Switching language retains the selected theme. Copy text, project links, or system images; save original PNGs; click previews to enlarge. All material uses fixed original examples independent of local conversations.

| Theme | Chinese artwork | English artwork |
| --- | --- | --- |
| Product overview | [PNG](assets/share/overview.png) | [PNG](assets/share/overview-en.png) |
| Moving computers and data ownership | [PNG](assets/share/ownership.png) | [PNG](assets/share/ownership-en.png) |
| Preparing history for AI | [PNG](assets/share/context.png) | [PNG](assets/share/context-en.png) |

Each image is 1080 × 1440 and follows “Your AI memories always belong to you”. See [sharing assets](docs/product-share.md) for details and regeneration instructions. Preview, copying, and saving work offline; project links open GitHub in a browser.

## Local sources and storage formats

| Source | Local location | Reader | Full records |
| --- | --- | --- | --- |
| Codex | `~/.codex/sessions`, `archived_sessions` | `.jsonl`, `.jsonl.zst`, `.jsonl.zstd` | Plain JSONL is read directly; compressed sessions can retain their original compressed copy as `source.jsonl.zst` |
| Claude Code | `~/.claude/projects` | JSONL | Source files are read without modification |
| Claude Desktop | `local-agent-mode-sessions`, `claude-code-sessions`, `Cache/Cache_Data`, and `Session Storage` in platform Claude / Claude-3p data directories | Existing JSONL and session metadata; allowlisted Code Projects message caches and navigation names | Local JSONL sessions/imported copies can retain `source.jsonl`; cached messages become merged snapshots without cloud export requests |
| WorkBuddy | `~/.workbuddy-ai/projects/*/*.jsonl`; `workbuddy.db` supplies titles, working directories, and models | JSONL + SQLite | Source JSONL is retained in full-snapshot mode; context wrappers remain in `dialogue.jsonl`, and clipboard images can be copied to `images/` |
| OpenClaw | `~/.openclaw/agents/*/agent/openclaw-agent.sqlite` | SQLite `transcript_events` | Full snapshots write event streams to `records/<device>-openclaw/<session>/source.jsonl` |
| DeepSeek Harness | `~/.dsh/sessions/<project>/<session>/session*.jsonl` and `.zst` / `.zstd` variants | JSONL or zstd-compressed JSONL | Full snapshots write decompressed events to `records/<device>-dsh/<session>/source.jsonl` |
| ChatGPT | Imported `conversations.json`, ZIP, or snapshot | JSON | Import caches and alternative branches remain local |

Claude Desktop defaults to `~/Library/Application Support/Claude` on macOS, `%APPDATA%/Claude` on Windows (falling back to `~/AppData/Roaming/Claude`), and `$XDG_CONFIG_HOME/Claude` on Linux (falling back to `~/.config/Claude`). The sibling `Claude-3p` directory is checked too. Override with `init --claude-desktop-home /path/to/Claude`; otherwise `CLAUDE_DESKTOP_HOME` or platform defaults apply. The reader scans both session-directory types, `Cache/Cache_Data`, and `Session Storage` under those roots. It extracts only allowlisted Code Projects message responses and Claude project/thread navigation names. It does not copy HTTP metadata, login credentials, or whole browser caches.

Source metadata retains import markers such as `claude-ai-chat`, `sibling-1p-code`, and `terminal-cli`, plus `coverage=local_imported_copy` or `local_desktop_session`. Existing imported cloud copies are not complete cloud history. Metadata without a body does not create empty sessions, and scheduled tasks do not sign in to Claude to fetch new chats. Identical original IDs in different accounts or product directories remain separate; moving an entire source directory preserves stable IDs. macOS local directories have been verified. Windows/Linux default paths have simulated tests, and backend CI uses native temporary-data regression tests on all three platforms; real source-app data still needs checking on those systems.

Code Projects uses `claude-desktop`, with `source=code-projects-cache` and `coverage=partial_cache`. Observed messages and updates merge incrementally by channel, thread, and message ID. Existing snapshots survive cache clearing; absence in one scan does not delete old records. Caches may cover only opened conversations or threads, so they do not prove full account coverage or a completed response. Attachments retain cached references and descriptions only; binaries may not be local or migrated, and no remote attachment is fetched automatically.

WorkBuddy wraps system instructions and memory in `<system-reminder data-role="user-context">`, followed by `<user_query>`. Markdown displays the actual question; `dialogue.jsonl` and local raw records retain the wrapper. OpenClaw heartbeats/tool results and DeepSeek Harness runtime context, time hints, and tool events likewise remain in local raw records without entering Markdown.

When retained, `records/.../source.jsonl` holds complete event streams for Claude Desktop local JSONL, OpenClaw, and DeepSeek Harness. Code Projects snapshots contain messages extracted from allowlisted responses, not complete HTTP response copies. Compressed Codex sessions use `source.jsonl.zst`, temporarily decompressed for log extraction. OpenClaw tool calls and results both have log associations. Like `dialogue.jsonl`, these copies stay local and are not uploaded through Git.

## Attachment-copy preferences

“Backup & Migration → Images & Attachments” starts with a preview of files associated with the current session. Search by name/path; filter by type, backup state, or size thresholds of 10 MB / 100 MB / 1 GB; sort large files first. The panel shows individual sizes, matching totals, and unbacked-up sizes, marking unknown sizes separately. Image thumbnails range from 64–240 pixels and open larger previews. Embedded session images are listed and deduplicated against file references. Only saved local images or an explicitly selected image folder are previewed; remote resources are not loaded.

List filters affect previews only. Actual copying uses the selected file types and session scope below the list; estimate first for accurate added space. Presets cover conversations only, conversations and images, or all associated files. You can select images, models, documents, code, command logs, and other attachments independently. The legacy default copies images; manual incremental imports default to text only. Saving future-backup preferences changes settings without starting a copy. Disabling a type stops future copies while keeping existing objects.

To fill gaps in existing sessions, select the current or all sessions, estimate, then copy incrementally. Only explicit session file references are processed. Originals remain unchanged, identical content reuses hash objects, and modified files retain older copies. Full source snapshots, when retained, may themselves contain embedded images; “conversations only” attachment preferences control extra resource-object copies, whereas text-only import also omits full snapshots. External links and Claude Projects descriptions do not prove that file binaries were saved, and remote attachments are not downloaded automatically.

Use `starvault attachment-policy --kinds none|images|all` or comma-separated kinds; omit `--kinds` to inspect the preference. MCP exposes `get_backup_preferences` and `set_backup_preferences`; `kinds=[]` means conversations only, and setting requires `--allow-write`. Immediate copying remains a separate `plan_attachment_migration` → `migrate_attachments` operation.

## Raw text, classification, and ChatGPT

Source and model are independent. `origin_kind/tool` identifies ChatGPT, Codex, Claude Code, Claude Desktop, WorkBuddy, OpenClaw, or DeepSeek Harness; `models` preserves model names from source records. A Codex session using a Claude-named model is still Codex. Project IDs, pinning, archive flags, original sources, entry points, session types, and recognized tags are retained. Original session metadata stays in local `manifest.json`; Claude Desktop keeps session-related fields rather than account configuration.

`dialogue.jsonl` preserves original textual user/assistant records, message fields, and related IDs without summarization. It also retains WorkBuddy context wrappers, OpenClaw internal messages, and DeepSeek Harness runtime events excluded from Markdown. Recognized embedded-image binaries are replaced with content-hash references, so this is not a byte-for-byte source JSONL copy. Source files remain unchanged. Alternative response branches from ChatGPT exports remain in local raw records, while the reader displays the current branch.

ChatGPT cloud history and local Codex JSONL are different sources. ChatGPT import accepts `conversations.json`, an export ZIP containing it, or a desktop-interface snapshot in this tool's format:

```sh
python3 vault.py import-chatgpt /path/to/conversations.json
python3 vault.py sync --tool chatgpt
```

Snapshots show coverage markers. Missing fields, such as model identity, remain unknown rather than inferred from names. Conversations visible in an app do not represent all account history; new cloud content needs another import. Scheduled tasks synchronize files already imported, without signing in to ChatGPT or fetching cloud history.

## Select local attachments by space

In “Backup & Migration → Images & Attachments”, choose images, GLB / Blender, documents, code, commands/logs, and other attachments for the current or all sessions. Estimate space before incremental copying. For all-session operations, enabling the future-scheduled-backup option saves types in local `.migration.json`; the legacy default is images only.

Manifests record original paths, message positions, type, size, copy location, and SHA-256. Command logs include source-JSONL byte offsets, record positions, time, and call IDs, and are extracted into `operations.jsonl` on request. Associations survive uncopied or missing files, with unavailable sources marked. Identical content reuses objects; changed files create new copies while old ones remain. Collection recognizes session references without recursively copying projects or promising every external Blender dependency.

Existing local snapshots use relative `source_copy` paths, allowing log extraction after moving the entire archive. Old absolute archive paths are resolved against the current session directory. Compressed snapshots validate log offsets against decompressed bytes; bad hashes do not overwrite migrated logs. For ordinary JSONL without a full source copy, migrate required logs before moving computers. An old computer's path in a manifest is not itself a backup.

```sh
python3 vault.py migrate --kinds models,logs --plan
python3 vault.py migrate --kinds models,logs --branch MyLaptop-codex --session SESSION_ID
python3 vault.py migrate --kinds all --plan
python3 vault.py migrate --kinds images,models,logs --remember
```

Images go into `images/`, other files into `attachments/`, with associations reconstructed through `records/`. Low disk space or failed attachment copies do not block conversation-text backups; errors are recorded in backup status. Space estimates for logs or missing embedded images may conservatively use the source-record size. Commands, logs, and original metadata never enter conversation Git branches.

## Collect and restore Skills across computers

“Backup & Migration → Skill backup & restore” collects packages containing `SKILL.md` from these default locations:

- Codex: `~/.codex/skills`, preferring configured `codex_home`, otherwise `CODEX_HOME`.
- Claude: `~/.claude/skills`, preferring configured `claude_home`, otherwise `CLAUDE_CONFIG_DIR`.
- Shared conventions: `~/.agents/skills`.
- Current project: `.agents/skills`, `.codex/skills`, and `.claude/skills`. The CLI uses its working directory; the desktop app defaults to the tool-code directory.

`~` refers to the current user's home directory on every platform; the original computer's username is not hardcoded. Plugin caches and every project on disk are outside the default scan. Add more folders individually or one per line; spaces and Chinese characters work.

Estimate before backing up. Instructions, scripts, references, and assets are saved together, deduplicated by content with a new version on change. Missing sources do not delete existing backups. Direct child symlinks in a Skill collection are resolved and deduplicated; generated directories such as `.git`, `node_modules`, and virtual environments, plus links inside packages, are skipped with notices. Restoration validates content and paths, rejecting Windows reserved names, traversal, and case collisions.

```sh
# macOS / Linux: an explicit local archive needs no prior GitHub configuration.
python3 vault.py skills --archive "$HOME/ChatHistoryBackup" --defaults --plan
python3 vault.py skills --archive "$HOME/ChatHistoryBackup" --defaults --remember
python3 vault.py skills --archive "$HOME/ChatHistoryBackup" --list
# Restore the latest version using an ID from --list; add --version HASH for an older one.
python3 vault.py skills --archive "$HOME/ChatHistoryBackup" --restore ID --destination "$HOME/RestoredSkills"
# Collect only selected folders; --source may be repeated.
python3 vault.py skills --archive "$HOME/ChatHistoryBackup" --no-defaults --source "/path/to/skills"
```

```powershell
# Windows PowerShell
py -3 vault.py skills --archive "$HOME\ChatHistoryBackup" --defaults --plan
py -3 vault.py skills --archive "$HOME\ChatHistoryBackup" --defaults --remember
py -3 vault.py skills --archive "$HOME\ChatHistoryBackup" --restore ID --destination "$HOME\RestoredSkills"
```

Enabling updates alongside existing scheduled backups, or using `--remember`, adds incremental collection to existing `export` / `sync` operations without creating a separate schedule. Sources are stored in archive-root `.skills.json`, isolated by platform and device name. `--forget` or clearing the option disables automatic collection on this computer while retaining backups. Choose sources again after moving computers rather than reusing another computer's absolute paths.

Move the entire `skills/` directory, including `index.json` and `objects/`. Restore creates `destination/SkillName-shortID/` and does not overwrite a different existing directory. A tool's Skill directory can be the parent destination. Package text/scripts stay unchanged: restoration does not rewrite absolute paths, install dependencies, or run scripts. Satisfy the Skill's platform requirements on the destination. Python backup/restoration uses the cross-platform standard library; real Windows/Linux Skill migration has not been verified.

## Connect through MCP

`chat-history-vault mcp`, also available through `vault_mcp.py`, is a local stdio MCP server reading the same archive as the desktop app. It follows MCP [stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) and [initialization](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle), supporting protocol versions `2025-11-25`, `2025-06-18`, `2025-03-26`, and `2024-11-05`. The client launches it and exchanges JSON through standard input/output. It opens no network port and writes diagnostics to stderr.

After installing the CLI, run `chat-history-vault mcp --print-config`. Source entry points are shown below. Generated configuration includes absolute paths for your interpreter, script, and archive, plus the configuration-directory environment variable:

```sh
# macOS / Linux: use the configured archive by default.
python3 vault_mcp.py --print-config
# Select another archive.
python3 vault_mcp.py --archive "/path/to/backup" --print-config
```

```powershell
# Windows PowerShell; replace the example archive location as needed.
py -3 vault_mcp.py --archive "D:\ChatHistoryBackup" --print-config
```

Output uses the common `mcpServers` JSON structure. Add the `chat-history-vault` entry to your client's existing configuration. For other formats, carry over `command`, `args`, and `env`. The generator does not overwrite client settings. Use the generated argument array directly for paths containing spaces, Chinese characters, or Windows backslashes instead of joining it into a shell command.

The current server exposes eight query and estimation tools by default:

| Tool | Purpose |
| --- | --- |
| `vault_status` | Session, source, and Skill counts, plus reading notices |
| `search_conversations` | Multi-term full-text search filtered by source, project, computer, and archive state |
| `read_conversation` | Paginated Markdown, raw messages, metadata, or migrated operation logs |
| `list_attachments` | Paginated session attachment associations and copy status |
| `list_skill_backups` | Paginated Skill packages and saved versions |
| `get_backup_preferences` | Inspect attachment types selected for future backups |
| `plan_attachment_migration` | Estimate copy space for selected attachment types |
| `plan_skill_backup` | Scan default/custom Skill sources and estimate space |

To let the client perform local backup and restoration, generate configuration with `--allow-write`:

```sh
python3 vault_mcp.py --allow-write --print-config
```

This adds five tools: `backup_conversations`, `migrate_attachments`, `set_backup_preferences`, `backup_skills`, and `restore_skill`. `backup_conversations` uses local source settings saved by `vault.py init`. Its `tool=all` shares CLI discovery, including existing Claude Desktop, WorkBuddy, OpenClaw, DeepSeek Harness, and imported ChatGPT directories. The other tools work directly with `--archive`. Operations reuse existing implementations and the synchronization lock. MCP has no tool to push to GitHub, delete archives, or execute historical commands. Retrieved history enters the requesting client's context and is governed by that client's data settings.

Queries and attachment selection identify sessions with both `branch` and `session_id`, distinguishing identical IDs across computers. Lists return at most 100 items per page; raw text at most 24,000 characters, continued with `next_offset`. `warnings_total` counts all notices, with the first 100 returned. Operation logs are readable only after migration. Search snippets are not whole conversations, and commands or Skill text found in the archive are reference data rather than current instructions.

Without an MCP client, use the same interfaces as one-shot CLI calls:

```sh
python3 vault_mcp.py --call vault_status
python3 vault_mcp.py --call search_conversations --arguments '{"query":"migration","limit":10}'
python3 vault_mcp.py --list-tools
```

For Windows or complex arguments, use a UTF-8 JSON file to avoid shell quoting. PowerShell UTF-8 BOMs are supported:

```powershell
'{"query":"migration","limit":10}' | Set-Content -Encoding UTF8 request.json
py -3 vault_mcp.py --call search_conversations --arguments-file request.json
```

Requests are processed sequentially; allow sufficient client tool-call timeouts for long backups. Local stdio subprocess communication, read-only boundaries, Chinese paths, and local backup/restoration have been tested. Real Windows/Linux MCP client integration has not been verified.

## A Skill for AI clients

The distributable user Skill is in [skills/use-chat-history-vault](skills/use-chat-history-vault/SKILL.md). Copy the entire folder to a Skill directory supported by your client. Compare an existing same-named directory first and preserve your changes. It ships with source packages and Python wheels. After CLI installation, `chat-history-vault skill-path` prints its absolute location without installing or overwriting client Skills.

The Skill guides AI clients through history search, paginated verification, attachment migration, and Skill restoration with MCP. Without MCP, use `chat-history-vault call`; legacy `vault_mcp.py --call` still works. Connection settings and user authorization stay separate, with no automatic changes to global client configuration. Example request: “Use StarVault to find our earlier Windows migration discussion and read the original text to verify it.”

The repository's `.agents/skills/chat-history-vault` is for developing the software; `use-chat-history-vault` is for operating it.

## Set up a new computer

Local collection and portable archive export do not require GitHub. For optional repository synchronization, authenticate first with `gh auth login` or a system Git credential manager, and use a **private** backup repository separate from the public software repository.

The example below clones the public software. Replace `YOUR-ACCOUNT/YOUR-PRIVATE-BACKUP` with your own private backup repository before running `init`:

```sh
mkdir -p "$HOME/Library/Application Support/ChatHistoryVault"
git clone --single-branch --branch main https://github.com/StarDreamTech/StarVault.git "$HOME/Library/Application Support/ChatHistoryVault/tool"
cd "$HOME/Library/Application Support/ChatHistoryVault/tool"
python3 vault.py init --repo https://github.com/YOUR-ACCOUNT/YOUR-PRIVATE-BACKUP.git --device MyLaptop
python3 vault.py export   # Generate local text and images without uploading
python3 vault.py sync     # Incrementally export, commit, and push enabled device-tool branches
```

Give each computer a different `--device`. Do not reuse one computer's configuration directory on another. Reinstall and initialize on the new computer, or select a separate `CHAT_HISTORY_VAULT_CONFIG_DIR`; the image folder can be moved as a whole. The default device name is the hostname, which you may replace with an English name. On Windows/Linux, choose a suitable local tool directory instead of the macOS path in this example.

## Incremental backup and scheduling

```sh
python3 vault.py install-schedule  # macOS: run hourly after login, and once on installation
python3 vault.py status
python3 vault.py remove-schedule
python3 vault.py sync --tool codex   # codex / claude / claude-desktop / workbuddy / openclaw / dsh / chatgpt
```

macOS uses a LaunchAgent; source apps need not stay open. Nothing runs while the computer is asleep or shut down; the system resumes scheduling afterward. The default tool and backup location is `~/Library/Application Support/ChatHistoryVault/`, avoiding background access issues with Documents/Desktop privacy controls. On other platforms, choose a code directory and use the system task scheduler to run `python3 /path/to/vault.py sync`.

Logs are `schedule.log` and `schedule-error.log` in the selected configuration directory, or `.local/` for older source installs. A shared lock prevents overlap between manual and scheduled operations. Network/push failures return nonzero status while keeping local results for retry.

JSONL / zstd changes are detected using file path, size, nanosecond modification time, file identity/state, and session metadata. OpenClaw uses each session's event-content hash, detecting SQLite WAL-only updates even when record counts remain unchanged. SQLite is read in a read-only transaction. Temporary database copies are checked against DB/WAL state; persistent change reports a retry instead of accepting an inconsistent copy.

Unchanged sessions are skipped. Changed sessions are parsed again; existing images reuse content hashes, and text is rewritten only when it actually changes. Archived records are exported too. Source-app cleanup never deletes backed-up sessions. SQLite/compressed sources are prepared and parsed in temporary storage before publishing local copies. Corrupt completed JSONL records or truncated compressed frames preserve the existing snapshot/cache, report failure, and prevent upload. A partial final JSON record still being written is deferred until the next read. Log signatures include operation contents, detecting changes even when call counts remain equal.

Desktop startup, manual refresh, and one-minute refreshes incrementally update timelines in the background. Changed sessions regenerate nodes; unchanged sessions reuse caches. Caches live in the local app's `timeline/` directory (`~/Library/Application Support/ChatHistoryVault/timeline/` on macOS), outside backup Git branches. They can be regenerated from the archive. Timelines read existing backups; new source-app conversations must first enter the archive through import or the existing `export` / `sync` flow, subject to the saved import policy.

## Move a backup

Local folder layout:

```text
ChatHistoryBackup/
  README.md
  images/<sha256>.png
  attachments/<sha256>.blend
  skills/
    index.json
    objects/<version-hash>.zip
  records/<device-tool>/<session-id>/
    dialogue.jsonl
    manifest.json
    operations.jsonl  # Created when command/log migration is selected
    source.jsonl      # Optional full local-session/event snapshot
    source.jsonl.zst  # Optional original compressed Codex snapshot
  MyLaptop-codex/
    README.md
    index.json
    sessions/<project>/<session-id>.md
  MyLaptop-claude/
    README.md
    index.json
    sessions/<project>/<session-id>.md
  MyLaptop-claude-desktop/
    index.json
    sessions/<project>/<session-id>.md
  MyLaptop-workbuddy/
    index.json
    sessions/<project>/<session-id>.md
  MyLaptop-openclaw/
    index.json
    sessions/<project>/<session-id>.md
  MyLaptop-dsh/
    index.json
    sessions/<project>/<session-id>.md
  MyLaptop-chatgpt/   # Created after ChatGPT import
    index.json
    sessions/<project>/<session-id>.md
```

**Copy the entire backup folder.** On macOS the default actual directory is `~/Library/Application Support/ChatHistoryVault/backup/`; copy that directory itself, rather than a shortcut or symlink. Markdown uses relative image paths and remains readable after moving. Cloning GitHub branches alone cannot recover local raw records, images, models, logs, or Skills. Include `records/`, `images/`, `attachments/`, and `skills/`. Original chat directories are never moved, modified, or deleted.

To download only a computer's text from GitHub, place its branch checkout inside the same backup root. Replace the private-repository placeholder:

```sh
git clone --single-branch --branch MyLaptop-codex https://github.com/YOUR-ACCOUNT/YOUR-PRIVATE-BACKUP.git "$HOME/Library/Application Support/ChatHistoryVault/backup/MyLaptop-codex"
```

## What is preserved

Git stores user/assistant conversation text, times, titles, projects, working paths, classification tags, archive state, subagent markers, and local-image references. Original messages and metadata remain local. Commands, tool arguments, output logs, and GLB/Blend files can optionally be copied locally. Full event snapshots for OpenClaw / DeepSeek Harness use local `source.jsonl`; compressed Codex uses `source.jsonl.zst`. Markdown displays conversation text only, excluding internal reasoning and system prompts. Credential files and whole SQLite databases are not migrated as attachments.

Exported text is preserved as written; passwords pasted directly into messages are not automatically detected or redacted. Images can contain information visible in screenshots, so they are stored in your local backup folder.

Remote images are not downloaded. Missing local images cannot be recovered; their paths appear in `index.json` under `unavailable_local_images`. Embedded media other than PNG/JPEG/GIF/WebP is not guaranteed to be preserved. Images still embedded in source JSONL can be extracted losslessly, but data already deleted by the source app cannot be reconstructed from text.

This is a **reading and search archive**. Importing it back into the original application to continue the same session is not guaranteed. Native conversation continuation across computers requires separate handling of the original app's databases, paths, and session formats. Branches share the private repository's storage allowance; StarVault uploads no images and requires no Git LFS quota.

After changing code, run checks appropriate to the change:

```sh
python3 -m unittest -v
python3 vault_mcp.py --call vault_status
cd desktop
cargo test --locked
```

## Project development Skill

The repository's [chat-history-vault Skill](.agents/skills/chat-history-vault/SKILL.md) documents code entry points, data boundaries, UI conventions, validation, and packaging for future development.
