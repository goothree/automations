function Invoke-CareAiPytest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$PytestArgs,

        [string]$ScreenshotEnvVar = "",
        [string]$LogFileName = "pytest.log"
    )

    $ErrorActionPreference = "Stop"
    $Root = Resolve-Path (Join-Path $PSScriptRoot "..")
    Set-Location $Root

    $pytest = Join-Path $Root ".venv\Scripts\pytest.exe"
    if (-not (Test-Path $pytest)) {
        throw "Virtual environment not found at $Root\.venv. Run: .\scripts\setup-windows.ps1"
    }

    # Avoid UnicodeEncodeError when piping pytest output (e.g. checkmarks in test logs).
    $env:PYTHONIOENCODING = "utf-8"

    if ($ScreenshotEnvVar) {
        $runDir = Join-Path $Root "screenshots\$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        New-Item -ItemType Directory -Path $runDir -Force | Out-Null
        Set-Item -Path "env:$ScreenshotEnvVar" -Value $runDir
        $logFile = Join-Path $runDir $LogFileName
        Write-Host "Screenshots and log: $runDir"
        & $pytest @PytestArgs 2>&1 | Tee-Object -FilePath $logFile
    }
    else {
        & $pytest @PytestArgs
    }

    exit $LASTEXITCODE
}
