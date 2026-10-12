# Toolchain

EXPORTGAME is built to run **self-contained on Windows 11**: it looks for its
JDK and Android SDK/NDK inside its own `tools\` folder first, so there is no
PATH editing and no separate install once that folder is prepared.

Analysis and verification need **no external tools** (stdlib Python only). The
APK build needs a JDK + Android SDK; the decompile stage uses optional helpers
when present.

## One-time preparation (Windows 11)

```powershell
# from the repo root, in PowerShell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap_android.ps1
powershell -ExecutionPolicy Bypass -File scripts\bootstrap_android.ps1 -Full
```

`run.bat` runs the simple form automatically the first time.

The script downloads, with **no winget/choco and no registry changes**:

- a **portable Temurin JDK 17** unpacked to `tools\jdk\`
- Android **command-line tools** + `platform-tools`, `build-tools;34.0.0`,
  `platforms;android-34` and the **NDK 26** into `tools\android-sdk\`
- with `-Full`, also jadx, Il2CppDumper and apktool into `tools\`

Everything lands under `tools\` (override with `EXPORTGAME_TOOLS`). On
Linux/macOS use `scripts/bootstrap_android.sh`.

## How discovery works

`portagent/tools.py` is the single source of truth. It searches, in order:

1. the bundled `tools\` folder (or `EXPORTGAME_TOOLS` / `PAGENT_TOOLS`),
2. the standard environment: `ANDROID_HOME` / `ANDROID_SDK_ROOT` / `JAVA_HOME`,
3. common machine installs (Windows: `%LOCALAPPDATA%\Android\Sdk`,
   `C:\Android\Sdk`; Linux/macOS: `~/Android/Sdk`, `~/Library/Android/sdk`).

`tools.prepare_environment()` prepends the discovered `jdk\bin`, build-tools and
platform-tools to `PATH`, so the build-tools are callable by name — including on
Windows where they are `aapt2.exe` / `d8.bat`.

## What each tool is for

| Tool | Stage | Purpose |
|---|---|---|
| `readelf` / `objdump` | Analyzer | augment pure-Python PE/ELF parsing |
| `monodis` (Mono) | Decompiler | .NET assemblies → IL |
| jadx | Decompiler | DEX/APK → Java |
| Il2CppDumper | Decompiler | IL2CPP metadata → types/methods |
| JDK (`javac`) | Builder | compile the Android glue |
| Android build-tools | Builder | `aapt2`, `d8`, `zipalign`, `apksigner` |
| Android NDK (clang) | Builder | arm64-v8a / armeabi-v7a / x86_64 native libs |
| DXVK / VKD3D / Box64 / Wine | Runtime | emulation paths (payloads, not vendored) |

The APK is built **directly** with the build-tools — **no Gradle, no CMake, no
Ninja, no network at build time**.

## Environment variables (optional)

Only needed if you keep the tools somewhere other than `tools\`:

```powershell
set EXPORTGAME_TOOLS=C:\path\to\tools
set ANDROID_HOME=%EXPORTGAME_TOOLS%\android-sdk
set JAVA_HOME=%EXPORTGAME_TOOLS%\jdk
```

## Test requirements

The unit tests build real PE/ELF fixtures. Install the cross compilers with:

```bash
sudo apt-get install -y mingw-w64 gcc-aarch64-linux-gnu mono-mcs
```

Tests skip cleanly when the Android SDK/NDK is missing; with a JDK + SDK
present the packager tests build a real signed APK. There is no `/dev/kvm` in
this container, so on-device performance verification is out of scope.
