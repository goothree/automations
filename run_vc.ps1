# Run the Virtual Care test (login + open VC from overflow menu).
. "$PSScriptRoot\scripts\TestRun.ps1"
$pytestArgs = @("src/tests/virtual_care.py::test_vc", "-v") + $args
Invoke-CareAiPytest -PytestArgs $pytestArgs -ScreenshotEnvVar "VC_SCREENSHOT_RUN_DIR" -LogFileName "run_vc.log"
