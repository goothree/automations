# Run care.ai HL7 message templates.
# Setup: copy scripts/hl7/.env.example to scripts/hl7/.env and fill in values.
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)
Set-Location $PSScriptRoot
if (Test-Path ".venv\Scripts\python.exe") {
    & .venv\Scripts\python.exe scripts/hl7_runner.py @Args
} else {
    python scripts/hl7_runner.py @Args
}
