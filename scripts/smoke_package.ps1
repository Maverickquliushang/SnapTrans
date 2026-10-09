. (Join-Path $PSScriptRoot 'env.ps1')
$exe = Join-Path $snapRoot "output/v$snapVersion/SnapTrans/SnapTrans.exe"
$report = Join-Path $snapRoot '.tmp/package-self-test.json'
$process = Start-Process -FilePath $exe -ArgumentList @('--self-test', '--report', ('"' + $report + '"')) -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(60000)) {
    Stop-Process -Id $process.Id
    throw 'Packaged OCR self-test timed out'
}
if ($process.ExitCode -ne 0) { throw 'Packaged OCR self-test failed' }
$result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if (-not $result.ok) { throw 'Packaged OCR did not pass' }
$result | ConvertTo-Json
$workerReport = Join-Path $snapRoot '.tmp/package-worker-test.json'
$worker = Start-Process -FilePath $exe -ArgumentList @('--self-test-worker', '--report', ('"' + $workerReport + '"')) -WindowStyle Hidden -PassThru
if (-not $worker.WaitForExit(60000)) {
    Stop-Process -Id $worker.Id
    throw 'Packaged worker test timed out'
}
if ($worker.ExitCode -ne 0) { throw 'Packaged worker test failed' }
Get-Content -LiteralPath $workerReport -Raw
$uiReport = Join-Path $snapRoot '.tmp/package-ui-test.json'
$ui = Start-Process -FilePath $exe -ArgumentList @('--self-test-ui', '--report', ('"' + $uiReport + '"')) -WindowStyle Hidden -PassThru
if (-not $ui.WaitForExit(60000)) {
    Stop-Process -Id $ui.Id
    throw 'Packaged UI test timed out'
}
if ($ui.ExitCode -ne 0) { throw 'Packaged UI test failed' }
Get-Content -LiteralPath $uiReport -Raw
$hotkeyReport = Join-Path $snapRoot '.tmp/package-hotkeys.json'
$hotkeyProcess = Start-Process -FilePath $exe -ArgumentList @('--self-test-hotkeys', '--report', ('"' + $hotkeyReport + '"')) -WindowStyle Hidden -PassThru
if (-not $hotkeyProcess.WaitForExit(55000)) {
    Stop-Process -Id $hotkeyProcess.Id
    throw 'Packaged native hotkey test timed out'
}
if ($hotkeyProcess.ExitCode -ne 0) { throw 'Packaged native hotkey test failed' }
Copy-Item -LiteralPath $hotkeyReport -Destination (Join-Path $snapRoot "output/hotkey-verification-$snapVersion.json")
Get-Content -LiteralPath $hotkeyReport -Raw
$workspaceReport = Join-Path $snapRoot '.tmp/package-ocr-workspace.json'
$workspaceProcess = Start-Process -FilePath $exe -ArgumentList @('--self-test-ocr-workspace', '--report', ('"' + $workspaceReport + '"')) -WindowStyle Hidden -PassThru
if (-not $workspaceProcess.WaitForExit(55000)) {
    Stop-Process -Id $workspaceProcess.Id
    throw 'Packaged OCR workspace test timed out'
}
if ($workspaceProcess.ExitCode -ne 0) { throw 'Packaged OCR workspace test failed' }
Copy-Item -LiteralPath $workspaceReport -Destination (Join-Path $snapRoot "output/ocr-workspace-verification-$snapVersion.json")
Get-Content -LiteralPath $workspaceReport -Raw
$onboardingReport = Join-Path $snapRoot '.tmp/package-onboarding.json'
$onboardingProcess = Start-Process -FilePath $exe -ArgumentList @('--self-test-onboarding', '--report', ('"' + $onboardingReport + '"')) -WindowStyle Hidden -PassThru
if (-not $onboardingProcess.WaitForExit(55000)) {
    Stop-Process -Id $onboardingProcess.Id
    throw 'Packaged onboarding test timed out'
}
if ($onboardingProcess.ExitCode -ne 0) { throw 'Packaged onboarding test failed' }
Copy-Item -LiteralPath $onboardingReport -Destination (Join-Path $snapRoot "output/onboarding-verification-$snapVersion.json")
Get-Content -LiteralPath $onboardingReport -Raw
