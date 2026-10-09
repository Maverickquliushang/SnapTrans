param([string]$OllamaModel = '')
. (Join-Path $PSScriptRoot 'env.ps1')
$stage = Join-Path $snapRoot "output/v$snapVersion/SnapTrans"
$relocation = Join-Path $snapRoot ('.tmp/中文 路径验证-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $relocation | Out-Null
Copy-Item -LiteralPath $stage -Destination $relocation -Recurse
$exe = Join-Path $relocation 'SnapTrans/SnapTrans.exe'
# Restrict only this process and its children; no global environment changes.
$env:PATH = (Join-Path $env:SystemRoot 'System32') + ';' + $env:SystemRoot
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
$report = Join-Path $snapRoot '.tmp/relocated-ui-test.json'
$arguments = @('--self-test-ui', '--report', ('"' + $report + '"'))
if ($OllamaModel) { $arguments += @('--ollama-model', $OllamaModel) }
$process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $snapRoot -WindowStyle Hidden -PassThru
$deadline = [DateTime]::UtcNow.AddSeconds(150)
while (-not $process.WaitForExit(1000)) {
    if ([DateTime]::UtcNow -gt $deadline) {
        Stop-Process -Id $process.Id
        throw 'Relocated portable UI test timed out'
    }
}
if ($process.ExitCode -ne 0) { throw 'Relocated portable UI test failed' }
$result = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $result.ok -or $result.children_after_shutdown -ne 0) { throw 'Portable runtime did not pass' }
$result | ConvertTo-Json
