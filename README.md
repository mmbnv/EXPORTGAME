# EXPORTGAME

Turn **any game folder into an installable Android game**. Pick a folder, and
EXPORTGAME analyzes it, chooses a port route, rebuilds it and packages a real,
signed **APK** that installs on a phone and adapts to the device it runs on
(64-bit **arm64-v8a** and older 32-bit **armeabi-v7a** native libraries in one
APK, plus DPI/layout-agnostic assets and device-aware graphics tuning).

It runs **locally on Windows 11** with everything bundled — no cloud, no Gradle,
no manual PATH editing.

## Quick start (Windows 11)

1. Install [Python 3.10+](https://www.python.org/downloads/windows/) (tick
   *Add python.exe to PATH*).
2. **Double-click `run.bat`** (or `python run.py`).
   * On first run it prepares the toolchain once into the app's `tools\` folder
     (portable JDK + Android SDK/NDK, one-time download).
3. In the menu:
   * `1` – choose the game folder,
   * `2` – **Analyze** (engine, architecture, feasibility),
   * `3` – **Convert to Android** → a signed `.apk` appears in `exportgame_out\`.
4. Copy the `.apk` to the phone and install it (allow "install unknown apps").

Prefer a window? Run `python run.py --gui`.

## What it does

The pipeline is a real loop, not a mock:

```
ANALYZE -> CHOOSE -> DECOMPILE -> EXECUTE -> VERIFY -> LEARN   (repeat)
```

* **ANALYZE** — pure-Python PE/ELF parsing identifies the engine (Unity,
  Unreal, Godot, GameMaker, RPG Maker, Source, custom native, .NET, …),
  runtime APIs (D3D9/11/12, Vulkan, OpenGL, XAudio, …), architecture, DRM and
  anti-cheat. Kernel-level DRM/anti-cheat is reported as **impossible**, never
  faked.
* **CHOOSE** — ranks port strategies per title (native engine export, IL2CPP,
  Mono embed, .NET transpile, HTML5 wrap, Box64 DBT, Wine+DXVK) using learned
  experience.
* **DECOMPILE** — recovers code with the real tools when present
  (`monodis`/`objdump`/`readelf`/`jadx`/`Il2CppDumper`).
* **EXECUTE** — translates Windows APIs into compilable C shims, plans the
  Android runtime, and builds a **signed, aligned APK directly with the Android
  build-tools** (`aapt2` → `javac` → `d8` → `zip` → `zipalign` → `apksigner`).
* **VERIFY** — determinism/scene equivalence; reports `UNKNOWN` honestly when no
  oracle is supplied.
* **LEARN** — records outcomes in a SQLite memory store to improve future picks.

## "Works on any phone"

* One APK carries both **arm64-v8a** and **armeabi-v7a** native libraries, so it
  installs on modern 64-bit phones and older 32-bit ones alike.
* Layout is resolution/DPI independent (no fixed orientations or densities), so
  the port adapts to any screen.
* Graphics backend (Vulkan/GLES3) and heap/thread/audio settings are chosen
  automatically for the detected title and device class.

## Layout

```
run.py                      interactive menu (Windows-first entry point)
run.bat                     one-click Windows launcher
portagent/                  the engine (ANALYZE..LEARN pipeline)
  analyzer.py               engine/API/DRM detection + impossibility
  planner.py                strategy choice
  decompiler.py             real code recovery
  translator.py             API mapping -> generated C shims
  optimizer.py              Android tuning (ABIs/backend/heap/DBT) + env
  runtime.py                runtime-class planning + payload bundling
  packager.py               real signed APK (aapt2/d8/zipalign/apksigner)
  tools.py                  self-contained toolchain discovery (Windows-first)
  launcher.py / gui.py      headless API + optional Tkinter window
scripts/bootstrap_android.ps1   one-time toolchain prep (downloads into tools\)
tools/                      bundled JDK + Android SDK/NDK + optional tools
exportgame_out/             build output (the .apk lands here)
```

## Command line (optional)

```bash
python -m portagent analyze <game-folder>
python -m portagent port <game-folder> -o MyGame.apk     # one command -> signed APK
python -m portagent portall --work-dir ./all             # build all built-in fixtures
```

No third-party Python packages are required (stdlib only).

## Honest limits

EXPORTGAME ports what can legally and technically be ported. Games whose
protection or anti-cheat runs in the kernel (Denuvo, EAC, BattlEye, …) are
reported as **impossible**. Emulation routes (Box64/Wine+DXVK) are slower than
native; the heavy ARM64 runtime payloads are not vendored and are reported by
name if missing — the app never pretends a runtime is present.

## Docs

See `docs/ARCHITECTURE.md`, `docs/TOOLCHAIN.md` and `docs/USAGE.md`.
