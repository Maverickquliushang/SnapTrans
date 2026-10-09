. (Join-Path $PSScriptRoot 'env.ps1')
$python = Join-Path $snapRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { . (Join-Path $PSScriptRoot 'bootstrap.ps1') }
Set-Location -LiteralPath $snapRoot
Invoke-Checked $python @('main.py')
