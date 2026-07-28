# Run the Virtual Monitoring * test (login + open VM* from overflow menu).
. "$PSScriptRoot\scripts\TestRun.ps1"
$pytestArgs = @("src/tests/vmbeta.py::test_vmbeta", "-v") + $args
Invoke-CareAiPytest -PytestArgs $pytestArgs -ScreenshotEnvVar "VMBETA_SCREENSHOT_RUN_DIR" -LogFileName "run_vmbeta.log"
