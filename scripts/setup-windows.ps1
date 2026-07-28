# One-time Windows setup: Python, virtual environment, and test dependencies.
# Usage (from repo root):  .\scripts\setup-windows.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Get-PythonCommand {
    foreach ($cmd in @("python", "py")) {
        $exe = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($exe) {
            return $exe.Source
        }
    }
    return $null
}

$python = Get-PythonCommand
if (-not $python) {
    Write-Host "Python not found. Installing Python 3.12 via winget..."
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
        [System.Environment]::GetEnvironmentVariable("Path", "User")
    $python = Get-PythonCommand
    if (-not $python) {
        throw "Python install finished but python is still not on PATH. Open a new PowerShell window and rerun this script."
    }
}

Write-Host "Using Python: $(& $python --version)"
Write-Host "Creating virtual environment at .venv ..."
& $python -m venv .venv

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete. Run tests with PowerShell scripts at the repo root, for example:"
Write-Host "  .\run_vm.ps1"
Write-Host "  .\run_ida_5376.ps1"
Write-Host ""
Write-Host "Optional: create a .env file in the repo root to override BROWSER, HEADLESS, etc."
Write-Host "Default browser is Edge (already installed). Selenium downloads the matching driver on first run."
