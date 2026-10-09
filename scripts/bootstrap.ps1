param([switch]$Resolve)
. (Join-Path $PSScriptRoot 'env.ps1')
Set-Location -LiteralPath $snapRoot
$python = Join-Path $snapRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Invoke-Checked 'uv' @('venv', '--python', '3.12', '--seed', (Join-Path $snapRoot '.venv'))
    } else {
        Invoke-Checked 'py' @('-3.12', '-m', 'venv', (Join-Path $snapRoot '.venv'))
    }
}
Invoke-Checked $python @('-c', 'import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize("P")==8')
if ($Resolve -or -not (Test-Path 'requirements-dev.lock')) {
    Invoke-Checked $python @('-m', 'pip', 'install', 'pip-tools>=7,<8')
    . (Join-Path $PSScriptRoot 'lock.ps1')
}
Invoke-Checked $python @('-m', 'pip', 'install', '--require-hashes', '-r', 'requirements-dev.lock')
Invoke-Checked $python @('-m', 'pip', 'check')
if (Test-Path 'scripts/prepare_models.py') { Invoke-Checked $python @('scripts/prepare_models.py') }
