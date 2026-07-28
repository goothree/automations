# Run all tests.
. "$PSScriptRoot\scripts\TestRun.ps1"
$pytestArgs = @("src/tests/", "-v") + $args
Invoke-CareAiPytest -PytestArgs $pytestArgs
