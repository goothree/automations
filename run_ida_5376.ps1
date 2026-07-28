# Run IDA-5376 automated test suite (auth resilience during Virtual Monitoring).
. "$PSScriptRoot\scripts\TestRun.ps1"
$markers = if ($env:IDA5376_MARKERS) { $env:IDA5376_MARKERS } else { "ida_5376" }
$pytestArgs = @("-v", "src/tests/test_ida_5376.py", "-m", $markers) + $args
Invoke-CareAiPytest -PytestArgs $pytestArgs -ScreenshotEnvVar "IDA5376_SCREENSHOT_RUN_DIR" -LogFileName "run_ida_5376.log"
