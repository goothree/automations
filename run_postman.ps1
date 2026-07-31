# Run care.ai dev Postman collection requests.
# Setup: copy scripts/postman/.env.example to scripts/postman/.env and fill in values.
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)
Set-Location $PSScriptRoot
if (Test-Path ".venv\Scripts\python.exe") {
    & .venv\Scripts\python.exe scripts/postman_runner.py @Args
} else {
    python scripts/postman_runner.py @Args
}
