# Run only the login test (test_login_success).
. "$PSScriptRoot\scripts\TestRun.ps1"
$pytestArgs = @("src/tests/test_login.py", "-v") + $args
Invoke-CareAiPytest -PytestArgs $pytestArgs
