# AGENTS.md

Repository-specific knowledge for future agent sessions on **EXPORTGAME**
(a rework of PCEXPORTAND / PortAgent: turn any game folder into an installable
Android game APK).  Target host: **Windows 11, local, self-contained**.

## What this repo is

A dependency-free Python package (`portagent/`) implementing the loop
`ANALYZE → CHOOSE → DECOMPILE → EXECUTE → VERIFY → LEARN`, plus `run.py`
(Windows-first menu), `run.bat` (one-click launcher), tests (`tests/`), a
toolchain bootstrap (`scripts/bootstrap_android.ps1` for Windows,
`scripts/bootstrap_android.sh` for Linux/macOS), and docs (`docs/`).

## Environment facts (verified in the dev container)

- Base image: Debian 13, Python 3.13, `sudo` works, network works.
- There is **no** `/dev/kvm` → the Android emulator cannot run here.
- Cross compilers for tests: `sudo apt-get install -y mingw-w64 gcc-aarch64-linux-gnu`.
- A managed .NET assembler for analyzer tests: `sudo apt-get install -y mono-mcs`
  (provides `mcs`).  Without it, `test_godot_dotnet` and
  `test_managed_detection_via_clr_header` fail — the Mono fixtures fall back to
  PE stubs that carry no CLR header.
- A JDK is required to build APKs: `sudo apt-get install -y openjdk-21-jdk-headless`
  (sets `/usr/lib/jvm/java-21-openjdk-amd64`).
- Android SDK (build-tools 34 + platform 34 + NDK 26) installs via
  `scripts/bootstrap_android.sh` (large download) or, for a bundled layout,
  into `$HOME/exportgame-tools/android-sdk` and exposed with `EXPORTGAME_TOOLS`.

## Commands

```bash
python -m unittest discover -s tests -v     # full suite (builds real fixtures)
python run.py                                # interactive menu (Windows-first)
python run.py --gui                          # desktop GUI (Tkinter, optional)
python -m portagent analyze <game-folder>    # reconnaissance only
python -m portagent port <game> -o out.apk   # one command -> signed APK
python -m portagent portall --work-dir ./all # every strategy class -> summary
```

Run the suite with a JDK + Android SDK on PATH/`ANDROID_HOME` so the packager
tests execute instead of skipping:

```bash
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=$HOME/exportgame-tools/android-sdk ANDROID_SDK_ROOT=$ANDROID_HOME
python -m unittest discover -s tests
```

## Conventions & gotchas

- **Stdlib only** for the package. Do not add third-party runtime deps.
- Generated C (Translator output) must compile with plain C11 and `-Wall -Wextra`.
- `portagent/tools.py` is the single source of truth for toolchain discovery.
  Order: bundled `tools/` (or `EXPORTGAME_TOOLS`/`PAGENT_TOOLS`) → standard env
  (`ANDROID_HOME`/`ANDROID_SDK_ROOT`/`JAVA_HOME`) → common machine installs.
  `prepare_environment()` prepends the discovered JDK/bin + build-tools +
  platform-tools to `PATH`; `find_android_toolchain()` calls the same discovery.
  Tests isolate discovery with `tools.isolated_discovery(...)` (sets
  `EXPORTGAME_NO_DISCOVERY=1` so no machine scanning happens).
- Never invent machine install paths in discovery. On Windows only
  `%LOCALAPPDATA%\Android\Sdk` and `C:\Android\Sdk` are probed; Linux probes
  `~/Android/Sdk` and `~/Library/Android/sdk`.
- The verifier must never report `PASS` without an oracle; keep `UNKNOWN`.
- PE data directories start at optional-header offset `0x70` (PE32+) / `0x60`
  (PE32). `_has_clr_header` needs the real CLR metadata (`mcs`-built fixtures)
  to see `BSJB`.
- `_tool_in()` probes `.exe/.bat/.cmd/.sh` so Windows build-tools work.
- The APK is built **without Gradle and without network**: `aapt2 compile` →
  `aapt2 link` → `javac` → `d8` → zip → `zipalign` → `apksigner`.
- Universal build: `Optimizer` emits `abis = ["arm64-v8a", "armeabi-v7a"]` so one
  APK installs on any phone; `packager._build_native` also handles `x86_64` when
  requested. The native step is best-effort — the APK is valid without it.
- `README.md`/`run.py`/GUI/`pyproject.toml`/generated APK label+package are
  branded EXPORTGAME; the Python package is still named `portagent` (import
  path unchanged) — do not rename it without updating every import and `tests/`.
  Internal runtime identifiers (`PAGENT_*` env vars,
  `assets/game/portagent_runtime/`, `libportagent.so`) are intentionally kept
  stable — they are the runtime contract the generated launcher reads and
  tests assert on.

## Where things live

- `portagent/parsers.py` – PE/ELF parsing.
- `portagent/tools.py` – Windows-first, self-contained toolchain discovery.
- `portagent/launcher.py` – shared headless API (analyze/run_port/run_loop/report).
- `portagent/gui.py` – Tkinter desktop window (optional; degrades gracefully).
- `run.py` / `run.bat` – interactive menu + one-click Windows launcher.
- `portagent/analyzer.py` – engine/API/DRM detection + impossibility.
- `portagent/planner.py` – strategy choice + memory weighting.
- `portagent/decompiler.py` – real code recovery (monodis/objdump/jadx/Il2CppDumper).
- `portagent/translator.py` – API mapping + generated C shims.
- `portagent/optimizer.py` – Android tuning (ABIs/backend/heap/DBT) + env.
- `portagent/runtime.py` – runtime-class planning + payload bundling.
- `portagent/packager.py` – real signed APK (aapt2/javac/d8/zipalign/apksigner).
- `portagent/verifier.py` – determinism + scene equivalence.
- `portagent/memory.py` – SQLite experience store.
- `portagent/orchestrator.py` – the loop and JSON step reports.

## Packaging / self-contained notes

- `run.bat` and the menu call `tools.prepare_environment()` so the bundled JDK
  and Android SDK are used with no PATH editing.
- `scripts/bootstrap_android.ps1` downloads a **portable Temurin JDK** plus the
  Android cmdline-tools/SDK/NDK into the repo's `tools/` folder (no winget/choco
  needed). `-Full` also fetches jadx/Il2CppDumper/apktool there.
- Heavy ARM64 runtime payloads (Box64/Wine/DXVK) are **not** vendored;
  `RuntimeBundler` copies whatever is present in `tools/runtime/<class>/` (or
  `~/.portagent-tools/runtime/<class>/`) and never fakes a runtime as present.
- `tools/`, `exportgame_out/`, `*.apk` are git-ignored — never commit build
  outputs or the bundled toolchain.
