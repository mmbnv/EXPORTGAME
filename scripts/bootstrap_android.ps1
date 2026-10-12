# Prepare EXPORTGAME's Android toolchain on Windows 11.
#
# EXPORTGAME runs self-contained: it looks for a JDK and an Android SDK in its
# own `tools\` folder first, so no PATH editing and no separate installs are
# required after this one-time preparation step.
#
# This script (re)builds that `tools\` folder:
#   * downloads a portable JDK (Adoptium Temurin 17) and unpacks it to tools\jdk
#   * downloads Android command-line tools and uses sdkmanager to install
#     platform-tools, build-tools, platforms;android-34 and the NDK into
#     tools\android-sdk
#
# It is idempotent: re-running only fills in what is missing.  Requires only
# PowerShell 5+ and an internet connection for the one-time download.
#
# Usage (from the repo root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap_android.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap_android.ps1 -Full
#
# -Full additionally downloads jadx + Il2CppDumper + apktool into tools\ (used by
# the decompile stage; the APK build itself does not need them).

param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"

# Install next to the app so the app finds it automatically.
$RepoRoot   = Split-Path -Parent $PSScriptRoot
$Tools      = if ($env:EXPORTGAME_TOOLS) { $env:EXPORTGAME_TOOLS } else { Join-Path $RepoRoot "tools" }
$JdkDir     = Join-Path $Tools "jdk"
$AndroidSdk = Join-Path $Tools "android-sdk"
$NdkVersion = if ($env:NDK_VERSION) { $env:NDK_VERSION } else { "26.1.10909125" }
$BtVersion  = if ($env:BT_VERSION) { $env:BT_VERSION } else { "34.0.0" }
$Platform   = "android-34"

$CmdlineUrl = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
# Portable JDK (no installer, no registry changes).
$JdkUrl     = "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse"

function Log($msg) { Write-Host "[bootstrap] $msg" -ForegroundColor Cyan }
function Have($cmd) { $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue) }

New-Item -ItemType Directory -Force -Path $Tools | Out-Null

# --- JDK (portable, downloaded) -------------------------------------------
$javac = Join-Path $JdkDir "bin\javac.exe"
if (-not (Test-Path $javac)) {
    Log "downloading portable JDK (Temurin 17) ..."
    $tmp = Join-Path $env:TEMP ("eg_jdk_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $zip = Join-Path $tmp "jdk.zip"
    try {
        Invoke-WebRequest -Uri $JdkUrl -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $inner = Get-ChildItem $tmp -Directory | Where-Object { $_.Name -like "jdk*" } | Select-Object -First 1
        if (-not $inner) { throw "JDK archive did not contain a jdk* folder" }
        if (Test-Path $JdkDir) { Remove-Item -Recurse -Force $JdkDir }
        Move-Item $inner.FullName $JdkDir
    } catch {
        Log "automatic JDK download failed: $_"
        if (Have "javac") {
            $sys = Split-Path -Parent (Split-Path -Parent (Get-Command javac).Source)
            Log "using the JDK already on PATH: $sys"
            $JdkDir = $sys
        } else {
            Log "Install a JDK 17 manually (https://adoptium.net) and re-run."
        }
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
} else {
    Log "JDK already present: $JdkDir"
}
$env:JAVA_HOME = $JdkDir
$env:PATH = (Join-Path $JdkDir "bin") + ";" + $env:PATH

# --- Android command-line tools -------------------------------------------
$cmdline = Join-Path $AndroidSdk "cmdline-tools\latest"
if (-not (Test-Path (Join-Path $cmdline "bin\sdkmanager.bat"))) {
    Log "downloading Android command-line tools ..."
    $tmp = Join-Path $env:TEMP ("eg_cmdline_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $zip = Join-Path $tmp "cmdline.zip"
    Invoke-WebRequest -Uri $CmdlineUrl -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $AndroidSdk "cmdline-tools") | Out-Null
    Move-Item (Join-Path $tmp "cmdline-tools") $cmdline
    Remove-Item -Recurse -Force $tmp
}

$env:ANDROID_HOME = $AndroidSdk
$env:ANDROID_SDK_ROOT = $AndroidSdk
$sdkmanager = Join-Path $cmdline "bin\sdkmanager.bat"

if (Test-Path $sdkmanager) {
    Log "accepting licenses ..."
    # sdkmanager writes progress to stderr; don't let that abort the script.
    $ErrorActionPreference = "Continue"
    1..30 | ForEach-Object { "y" } | & $sdkmanager "--sdk_root=$AndroidSdk" --licenses 2>&1 | Out-Null
    Log "installing platform-tools, build-tools:$BtVersion, platforms;$Platform ..."
    & $sdkmanager "--sdk_root=$AndroidSdk" "platform-tools" "build-tools;$BtVersion" `
        "platforms;$Platform" 2>&1 | Out-Null
    Log "installing NDK $NdkVersion (for native libs / any-phone builds) ..."
    & $sdkmanager "--sdk_root=$AndroidSdk" "ndk;$NdkVersion" 2>&1 | Out-Null
    if (-not (Test-Path (Join-Path $AndroidSdk "ndk\$NdkVersion"))) {
        Log "NDK $NdkVersion not listed; installing the newest available ..."
        $latest = (& $sdkmanager "--sdk_root=$AndroidSdk" --list 2>&1 |
            Select-String "^\s*ndk;" | Select-Object -Last 1)
        if ($latest) {
            $pkg = ($latest.ToString().Trim() -split "\s+")[0]
            Log "installing $pkg ..."
            & $sdkmanager "--sdk_root=$AndroidSdk" $pkg 2>&1 | Out-Null
        }
    }
    $ErrorActionPreference = "Stop"
} else {
    Log "sdkmanager not found at $sdkmanager"
}

# --- optional decompilers (bundled into tools\) ----------------------------
if ($Full) {
    if (-not (Test-Path (Join-Path $Tools "jadx"))) {
        Log "downloading jadx ..."
        $j = Join-Path $Tools "jadx.zip"
        Invoke-WebRequest -Uri "https://github.com/skylot/jadx/releases/download/v1.5.1/jadx-1.5.1.zip" -OutFile $j -UseBasicParsing
        Expand-Archive -Path $j -DestinationPath (Join-Path $Tools "jadx") -Force
        Remove-Item $j -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path (Join-Path $Tools "Il2CppDumper"))) {
        Log "downloading Il2CppDumper ..."
        $z = Join-Path $Tools "il2cppdumper.zip"
        Invoke-WebRequest -Uri "https://github.com/Perfare/Il2CppDumper/releases/download/v6.7.46/Il2CppDumper-net6-v6.7.46.zip" -OutFile $z -UseBasicParsing
        Expand-Archive -Path $z -DestinationPath (Join-Path $Tools "Il2CppDumper") -Force
        Remove-Item $z -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path (Join-Path $Tools "apktool.jar"))) {
        Log "downloading apktool ..."
        Invoke-WebRequest -Uri "https://github.com/iBotPeaches/Apktool/releases/download/v2.11.1/apktool_2.11.1.jar" -OutFile (Join-Path $Tools "apktool.jar") -UseBasicParsing
    }
}

# --- summary ---------------------------------------------------------------
Log "done. Self-contained tools are in: $Tools"
Write-Host ""
Write-Host "The app finds these automatically - no PATH or env vars needed." -ForegroundColor Green
Write-Host "Start it with:" -ForegroundColor Cyan
Write-Host "  python run.py            # pick a game folder -> Convert to Android"
Write-Host "  python run.py --gui      # same, in a desktop window"
Write-Host ""
Write-Host "Check the toolchain inside the app: menu option 8 (Show environment / tools)." -ForegroundColor Cyan
