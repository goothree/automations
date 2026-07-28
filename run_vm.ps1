# Run the virtual monitoring test (login + VM flow).
. "$PSScriptRoot\scripts\TestRun.ps1"
$pytestArgs = @(
    "src/tests/virtual_monitoring.py::test_login_with_extra_step",
    "-v"
) + $args
Invoke-CareAiPytest -PytestArgs $pytestArgs -ScreenshotEnvVar "VM_SCREENSHOT_RUN_DIR" -LogFileName "run_vm.log"
