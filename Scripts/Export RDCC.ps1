# Builds a minimal, portable Red Dust Control Center bundle for any OS.
# Output: ../export/red_dust/ and ../export/red_dust.zip
#
# Includes application source, all platform setup/launch scripts, and requirements files.
# Excludes .venv, cache, sessions, __pycache__, IDE folders, and other machine-local data.
#
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File "Scripts/Export RDCC.ps1"

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$AppDir = Join-Path $RepoRoot "Red Dust Control Center"
$ScriptsDir = Join-Path $RepoRoot "Scripts"
$ExportRoot = Join-Path $RepoRoot "export"
$BundleName = "red_dust"
$BundleDir = Join-Path $ExportRoot $BundleName
$ZipPath = Join-Path $ExportRoot "$BundleName.zip"

$ExcludeDirNames = @(
    ".venv", "venv", "env", "ENV",
    "cache", "sessions",
    "__pycache__",
    ".vscode", ".idea",
    "build", "dist", "develop-eggs", "downloads", "eggs", ".eggs",
    "lib", "lib64", "parts", "sdist", "var", "wheels"
)

$ExcludeFilePatterns = @(
    "Export RDCC*"
)

function Should-SkipPath {
    param([string]$RelativePath)

    foreach ($part in $RelativePath -split '[\\/]') {
        if ($ExcludeDirNames -contains $part) {
            return $true
        }
    }

    $leaf = Split-Path -Leaf $RelativePath
    foreach ($pattern in $ExcludeFilePatterns) {
        if ($leaf -like $pattern) {
            return $true
        }
    }
    if ($leaf -match '\.(pyc|pyo|log)$') {
        return $true
    }
    if ($leaf -in @(".DS_Store", "Thumbs.db")) {
        return $true
    }

    return $false
}

function Copy-FilteredTree {
    param(
        [string]$SourceRoot,
        [string]$DestRoot
    )

    if (-not (Test-Path $SourceRoot)) {
        throw "Source folder not found: $SourceRoot"
    }

    Get-ChildItem -Path $SourceRoot -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($SourceRoot.Length).TrimStart('\', '/')
        if (Should-SkipPath $relative) {
            return
        }

        $destFile = Join-Path $DestRoot $relative
        $destParent = Split-Path -Parent $destFile
        if (-not (Test-Path $destParent)) {
            New-Item -ItemType Directory -Path $destParent -Force | Out-Null
        }
        Copy-Item -Path $_.FullName -Destination $destFile -Force
    }
}

function Write-TextFile {
    param(
        [string]$Path,
        [string]$Content
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Copy-ShellScriptFile {
    param(
        [string]$SourcePath,
        [string]$DestPath
    )

    $content = [System.IO.File]::ReadAllText($SourcePath) -replace "`r`n", "`n" -replace "`r", "`n"
    Write-TextFile -Path $DestPath -Content $content
}

function Copy-FilteredFiles {
    param(
        [string]$SourceRoot,
        [string]$DestRoot
    )

    if (-not (Test-Path $SourceRoot)) {
        throw "Source folder not found: $SourceRoot"
    }

    New-Item -ItemType Directory -Path $DestRoot -Force | Out-Null

    Get-ChildItem -Path $SourceRoot -File | ForEach-Object {
        if (Should-SkipPath $_.Name) {
            return
        }

        $destPath = Join-Path $DestRoot $_.Name
        if ($_.Extension -in @(".sh", ".command")) {
            Copy-ShellScriptFile -SourcePath $_.FullName -DestPath $destPath
        } else {
            Copy-Item -Path $_.FullName -Destination $destPath -Force
        }
    }
}

Write-Host "=== Export Red Dust Control Center ===" -ForegroundColor Cyan
Write-Host "Repo:   $RepoRoot"
Write-Host "Output: $BundleDir"
Write-Host ""

if (Test-Path $BundleDir) {
    Remove-Item -Path $BundleDir -Recurse -Force
}
New-Item -ItemType Directory -Path $BundleDir -Force | Out-Null

Write-Host "Copying Red Dust Control Center (source only)..."
Copy-FilteredTree -SourceRoot $AppDir -DestRoot (Join-Path $BundleDir "Red Dust Control Center")

Write-Host "Copying setup and launch scripts..."
Copy-FilteredFiles -SourceRoot $ScriptsDir -DestRoot (Join-Path $BundleDir "Scripts")

foreach ($rootFile in @("README.md", "LICENSE")) {
    $src = Join-Path $RepoRoot $rootFile
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $BundleDir $rootFile) -Force
    }
}

$Readme = @"
Red Dust Control Center — quick install
=======================================

Full documentation: README.md in this folder.

Windows
-------
  Scripts\Setup venv win.bat
  Scripts\Launch RDCC win.cmd

macOS
-----
  Scripts/Setup venv mac.command
  Scripts/Launch RDCC mac.command

Raspberry Pi
------------
  cd Scripts
  chmod +x setup-raspberrypi.sh launch-raspberrypi.sh
  ./setup-raspberrypi.sh

  Launch: ./launch-raspberrypi.sh
  Or search "Red Dust Control Center" in the application menu.

  sudo apt install python3-venv python3-pip
  sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1 libglib2.0-0

Seismic data downloads into Red Dust Control Center/cache/ on first use.
"@

Set-Content -Path (Join-Path $BundleDir "README-install.txt") -Value $Readme -Encoding UTF8

if (Test-Path $ZipPath) {
    Remove-Item -Path $ZipPath -Force
}

Write-Host "Creating zip archive..."
# Zip contents at archive root so "Extract Here" does not create red_dust/red_dust/
Compress-Archive -Path (Join-Path $BundleDir '*') -DestinationPath $ZipPath -Force

$folderBytes = (Get-ChildItem -Path $BundleDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
$zipBytes = (Get-Item $ZipPath).Length
$fileCount = (Get-ChildItem -Path $BundleDir -Recurse -File).Count

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Files:  $fileCount"
Write-Host "  Folder: $([math]::Round($folderBytes / 1MB, 2)) MB  ->  $BundleDir"
Write-Host "  Zip:    $([math]::Round($zipBytes / 1MB, 2)) MB  ->  $ZipPath"
Write-Host ""
Write-Host "One bundle for Windows, macOS, and Raspberry Pi." -ForegroundColor Cyan
Write-Host ""
Write-Host "On Raspberry Pi after copying red_dust.zip:"
Write-Host "  unzip red_dust.zip"
Write-Host "  cd Scripts"
Write-Host "  chmod +x setup-raspberrypi.sh launch-raspberrypi.sh"
Write-Host "  ./setup-raspberrypi.sh"
