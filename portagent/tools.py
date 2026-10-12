"""Windows-first, self-contained toolchain discovery for EXPORTGAME.

The app is meant to run on a plain Windows 11 machine with everything already
bundled, so it must not depend on the user editing PATH or installing a JDK and
Android SDK by hand.  This module locates the tools in a fixed priority order:

    1. bundled, next to the app      <app>/tools/{jdk,android-sdk}
    2. EXPORTGAME_TOOLS / PAGENT_TOOLS  (explicit override)
    3. standard environment          ANDROID_HOME / ANDROID_SDK_ROOT / JAVA_HOME
    4. common machine installs       %LOCALAPPDATA%\\Android\\Sdk, Program Files JDKs, ...

and then puts the JDK + Android build-tools + platform-tools on ``PATH`` for the
current process, so ``javac`` / ``aapt2`` / ``d8`` / ``apksigner`` just work when
the packager shells out.  Everything here is stdlib-only and safe to call on any
OS (it degrades to plain environment discovery off Windows).
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")


def app_root() -> Path:
    """Root of the running app: the frozen exe's folder, or the repo root."""
    if getattr(sys, "frozen", False):  # PyInstaller onefile/onedir
        return Path(sys.executable).resolve().parent
    # portagent/tools.py -> portagent/ -> repo root
    return Path(__file__).resolve().parent.parent


def bundled_tools_root() -> Path:
    """Folder that ships the self-contained tools (JDK + Android SDK)."""
    for key in ("EXPORTGAME_TOOLS", "PAGENT_TOOLS"):
        val = os.environ.get(key)
        if val:
            return Path(val).expanduser()
    return app_root() / "tools"


def _discovery_enabled() -> bool:
    """Machine scanning is on by default; tests can disable it for determinism."""
    return not os.environ.get("EXPORTGAME_NO_DISCOVERY")


def _android_sdk_candidates() -> list[Path]:
    cands: list[Path] = []
    root = bundled_tools_root()
    cands += [root / "android-sdk", root / "android-sdk-sdk", root / "Android"]
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(key):
            cands.append(Path(os.environ[key]).expanduser())
    if not _discovery_enabled():
        return cands
    if IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA")
        if local:
            cands.append(Path(local) / "Android" / "Sdk")
        cands.append(Path(r"C:\Android\Sdk"))
    else:
        cands += [Path.home() / "Android" / "Sdk",
                  Path.home() / "Library" / "Android" / "sdk"]
    return cands


def _jdk_candidates() -> list[Path]:
    cands: list[Path] = []
    root = bundled_tools_root()
    cands.append(root / "jdk")
    if os.environ.get("JAVA_HOME"):
        cands.append(Path(os.environ["JAVA_HOME"]).expanduser())
    if not _discovery_enabled():
        return cands
    if IS_WINDOWS:
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                     os.environ.get("LOCALAPPDATA")):
            if not base:
                continue
            b = Path(base)
            for vendor in ("Eclipse Adoptium", "Java", "Microsoft", "Amazon Corretto",
                           "Zulu", "BellSoft"):
                d = b / vendor
                if d.is_dir():
                    cands += sorted((p for p in d.iterdir() if p.is_dir()),
                                    key=lambda p: p.name, reverse=True)
    else:
        for base in ("/usr/lib/jvm", "/opt/java", str(Path.home() / ".sdkman/candidates/java")):
            d = Path(base)
            if d.is_dir():
                cands += sorted((p for p in d.iterdir() if p.is_dir()),
                                key=lambda p: p.name, reverse=True)
    return cands


def _javac_in(home: Path) -> str | None:
    """The javac for a JDK home (handles the extra wrapper folder on macOS)."""
    for sub in ("bin/javac", "Contents/Home/bin/javac"):
        exe = home / sub
        if IS_WINDOWS:
            win = exe.with_name(exe.name + ".exe")
            if win.is_file():
                return str(win)
        if exe.is_file():
            return str(exe)
    return None


def find_jdk() -> Path | None:
    """Return a JDK home that contains ``javac``, or ``None``."""
    for c in _jdk_candidates():
        try:
            if c.is_dir() and _javac_in(c):
                return c
        except OSError:
            continue
    return None


def find_android_sdk() -> Path | None:
    """Return an Android SDK folder containing ``build-tools``, or ``None``."""
    for c in _android_sdk_candidates():
        try:
            if (c / "build-tools").is_dir() and (c / "platforms").is_dir():
                return c
        except OSError:
            continue
    return None


def tool_dirs() -> list[Path]:
    """Folders that may hold optional helper tools (jadx, Il2CppDumper, ...)."""
    root = bundled_tools_root()
    dirs = [root, root / "tools"]
    home_tools = Path.home() / ".portagent-tools"
    if home_tools != root:
        dirs.append(home_tools)
    return [d for d in dirs if d.is_dir()]


def find_tool(name: str, *rel_candidates: str) -> str | None:
    """Locate an optional helper tool: PATH first, then bundled tool dirs.

    ``rel_candidates`` are tried under each :func:`tool_dirs` entry, e.g.
    ``find_tool("jadx", "jadx/bin/jadx", "jadx/bin/jadx.bat")``.
    """
    import shutil as _shutil

    found = _shutil.which(name)
    if found:
        return found
    names = [name]
    if IS_WINDOWS:
        names += [f"{name}.exe", f"{name}.bat", f"{name}.cmd"]
    for d in tool_dirs():
        for rel in rel_candidates:
            p = d / rel
            if p.is_file():
                return str(p)
        for n in names:
            p = d / n
            if p.is_file():
                return str(p)
    return None


@dataclass
class ToolchainStatus:
    ready: bool = False
    sdk: str | None = None
    jdk: str | None = None
    parts: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ready:
            return f"ready\n     sdk : {self.sdk}\n     jdk : {self.jdk}"
        return "NOT READY - missing: " + ", ".join(self.missing)


def prepare_environment() -> ToolchainStatus:
    """Put the discovered JDK + Android tools on PATH for this process.

    Safe and idempotent.  Returns what was found so the UI/menu can explain the
    state.  When nothing is bundled and nothing is installed, it simply returns
    a not-ready status without raising -- analysis still works without the SDK.
    """
    st = ToolchainStatus()
    sdk = find_android_sdk()
    jdk = find_jdk()

    extra: list[str] = []
    if jdk:
        st.jdk = str(jdk)
        st.parts["java_home"] = str(jdk)
        os.environ["JAVA_HOME"] = str(jdk)
        extra.append(str(jdk / "bin"))
    else:
        st.missing.append("JDK (javac)")
    if sdk:
        st.sdk = str(sdk)
        st.parts["android_home"] = str(sdk)
        os.environ["ANDROID_HOME"] = str(sdk)
        os.environ.setdefault("ANDROID_SDK_ROOT", str(sdk))
        for sub in ("platform-tools",):
            d = sdk / sub
            if d.is_dir():
                extra.append(str(d))
        bt_root = sdk / "build-tools"
        if bt_root.is_dir():
            versions = sorted((p for p in bt_root.iterdir() if p.is_dir()),
                              key=lambda p: p.name, reverse=True)
            if versions:
                extra.append(str(versions[0]))
        ndk_root = sdk / "ndk"
        if ndk_root.is_dir():
            ndks = sorted((p for p in ndk_root.iterdir() if p.is_dir()),
                          key=lambda p: p.name, reverse=True)
            if ndks:
                os.environ.setdefault("ANDROID_NDK_HOME", str(ndks[0]))
    else:
        st.missing.append("Android SDK (build-tools + platforms)")

    if extra:
        sep = os.pathsep
        current = os.environ.get("PATH", "")
        parts = [p for p in extra if p not in current.split(sep)]
        os.environ["PATH"] = sep.join(parts + [current]) if parts else current

    st.ready = bool(sdk and jdk)
    return st


def status() -> ToolchainStatus:
    """Report the current toolchain state without mutating the environment."""
    sdk = find_android_sdk()
    jdk = find_jdk()
    st = ToolchainStatus(ready=bool(sdk and jdk),
                         sdk=str(sdk) if sdk else None,
                         jdk=str(jdk) if jdk else None)
    if not jdk:
        st.missing.append("JDK (javac)")
    if not sdk:
        st.missing.append("Android SDK (build-tools + platforms)")
    return st


@contextlib.contextmanager
def isolated_discovery(bundle_dir: str | Path | None = None,
                       android_home: str | None = None):
    """Temporarily pin toolchain discovery for tests.

    Sets ``EXPORTGAME_NO_DISCOVERY`` (disable machine scanning), points the
    bundled-tools folder at ``bundle_dir``, and sets/clears ``ANDROID_HOME``.
    """
    keys = ("EXPORTGAME_NO_DISCOVERY", "EXPORTGAME_TOOLS", "PAGENT_TOOLS",
            "ANDROID_HOME", "ANDROID_SDK_ROOT")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["EXPORTGAME_NO_DISCOVERY"] = "1"
    if bundle_dir is not None:
        os.environ["EXPORTGAME_TOOLS"] = str(bundle_dir)
        os.environ.pop("PAGENT_TOOLS", None)
    else:
        os.environ.pop("EXPORTGAME_TOOLS", None)
        os.environ.pop("PAGENT_TOOLS", None)
    if android_home is None:
        os.environ.pop("ANDROID_HOME", None)
        os.environ.pop("ANDROID_SDK_ROOT", None)
    else:
        os.environ["ANDROID_HOME"] = android_home
        os.environ.pop("ANDROID_SDK_ROOT", None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
