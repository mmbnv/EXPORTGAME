"""Turn a PC game folder into an installable Android game (a signed APK).

    um android scan "C:\\Games\\MyGame"                 # reconnaissance only (engine, arch, blockers)
    um android build "C:\\Games\\MyGame" -o MyGame.apk  # full pipeline -> a signed, aligned APK
    um android env                                      # what toolchain (JDK + Android SDK/NDK) is found

This is the one-command path: pick a folder, get an Android game. It drives the
same iterative porter the desktop app uses (`portagent` package): ANALYZE ->
CHOOSE -> DECOMPILE -> EXECUTE -> VERIFY. The build runs locally and offline and
needs a JDK + Android SDK; the APK carries both `arm64-v8a` and `armeabi-v7a`
native libraries, so it installs on any modern phone.

Fails honestly: a title with a kernel-level anti-cheat/DRM is reported as
`impossible` (never faked), and a missing toolchain is reported as `fail` with
the reason, not a generic crash.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from um.common import die, emit


def _launcher():
    from portagent import launcher
    return launcher


def _progress(stage: str, message: str) -> None:
    print(f"  [{stage}] {message}", file=sys.stderr)


def _scan(game: str, as_json: bool) -> int:
    launcher = _launcher()
    try:
        profile = launcher.analyze(game)
    except FileNotFoundError:
        die(f"no such file or directory: {game}")
        return 2
    if as_json:
        emit(profile, True)
        return 0
    print(f"target      : {game}")
    print(f"engine      : {profile.get('engine')}")
    print(f"arch        : {profile.get('arch')}  managed={profile.get('managed')} il2cpp={profile.get('il2cpp')}")
    print(f"graphics    : {profile.get('graphics_api')}  audio={profile.get('audio_api')}")
    print(f"feasible    : {profile.get('feasible')}")
    blockers = profile.get("blockers") or []
    if blockers:
        print("blockers:")
        for b in blockers:
            print(f"  - {b.get('kind')}: {b.get('detail')}")
        print("\nverdict: IMPOSSIBLE - no Android-compatible path (will not be faked)")
    else:
        print("\nverdict: portable - run `um android build <folder>` to make the APK")
    return 0


def _env(as_json: bool) -> int:
    launcher = _launcher()
    info = launcher.environment()
    if as_json:
        emit(info, True)
        return 0
    tc = info.get("android_toolchain") or {}
    print(f"python      : {info.get('python')}  ({info.get('platform')})")
    if tc:
        print("toolchain   : ready")
        for k in ("sdk", "build_tools", "platform", "ndk", "java"):
            if tc.get(k):
                print(f"  {k:<11}: {tc[k]}")
    else:
        print("toolchain   : NOT ready")
        print("  install once:  scripts\\bootstrap_android.ps1   (Windows, in-place)")
        print("             or:  scripts/bootstrap_android.sh    (Linux/macOS)")
    tools = info.get("tools") or {}
    found = {k: v for k, v in tools.items() if v}
    if found:
        print("helpers     : " + ", ".join(f"{k}={v}" for k, v in found.items()))
    return 0 if tc else 1


def _build(game: str, output: str | None, work_dir: str, decompile: bool, as_json: bool) -> int:
    launcher = _launcher()
    game_path = Path(game)
    if not game_path.exists():
        die(f"no such file or directory: {game}")
        return 2
    if not as_json:
        print(f"porting {game} -> Android (this builds a real signed APK) ...", file=sys.stderr)
    summary = launcher.run_port(
        game_path,
        work_dir=work_dir,
        output=output,
        decompile=decompile,
        progress=None if as_json else _progress,
    )
    if as_json:
        emit(summary, True)
    else:
        status = summary.get("status")
        print()
        print(f"status      : {status}")
        print(f"engine      : {summary.get('engine')}   strategy: {summary.get('strategy')}")
        apk = summary.get("apk")
        if apk:
            print(f"APK         : {apk}")
            print(f"size        : {summary.get('apk_size')} bytes   signed={summary.get('signed')} aligned={summary.get('aligned')}")
            print(f"abis        : {', '.join(summary.get('abis') or [])}  (installs on any modern phone)")
        if status != "ok":
            print(f"reason      : {summary.get('message')}")
    return 0 if summary.get("status") == "ok" else 3


def main(args) -> int:
    cmd = getattr(args, "cmd", None)
    if cmd == "scan":
        return _scan(args.game, args.json)
    if cmd == "env":
        return _env(args.json)
    if cmd == "build":
        return _build(args.game, args.output, args.work_dir, not args.no_decompile, args.json)
    die("choose a subcommand: scan, build or env")
    return 2


def register(sub):
    import argparse
    p = sub.add_parser("android", help="turn a PC game folder into an installable Android game (APK)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")

    s = cs.add_parser("scan", help="reconnaissance: engine, arch, DRM/anti-cheat, feasibility")
    s.add_argument("game", help="game folder or installer file")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=main)

    b = cs.add_parser("build", help="analyze -> translate -> build a signed, installable APK")
    b.add_argument("game", help="game folder or installer file")
    b.add_argument("-o", "--output", default=None, help="output .apk path")
    b.add_argument("--work-dir", default="exportgame_out")
    b.add_argument("--no-decompile", action="store_true", help="skip code recovery")
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=main)

    e = cs.add_parser("env", help="show the discovered JDK / Android SDK / NDK toolchain")
    e.add_argument("--json", action="store_true")
    e.set_defaults(func=main)
