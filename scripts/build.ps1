param([switch]$SkipPackage, [switch]$SkipInteractive)
. (Join-Path $PSScriptRoot 'env.ps1')
Set-Location -LiteralPath $snapRoot
$python = Join-Path $snapRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { . (Join-Path $PSScriptRoot 'bootstrap.ps1') }
$version = (& $python -c 'from snaptrans import __version__; print(__version__)').Trim()
if (Test-Path "output/SnapTrans-$version-win-x64.zip") { throw 'Release ZIP already exists; preserve it before rebuilding.' }
if (-not (Test-Path 'requirements-dev.lock')) { throw 'Run bootstrap.ps1 to generate dependency locks.' }
Invoke-Checked $python @('-m', 'pip', 'install', '--require-hashes', '-r', 'requirements-dev.lock')
Invoke-Checked $python @('-m', 'pip', 'check')
Invoke-Checked $python @('scripts/generate_assets.py')
Invoke-Checked $python @('scripts/prepare_models.py')
Invoke-Checked $python @('scripts/collect_licenses.py')
Invoke-Checked $python @('scripts/collect_webengine_credits.py')
Invoke-Checked $python @('-m', 'pytest', '-q', '--basetemp', '.tmp/build-tests')
Invoke-Checked $python @('scripts/smoke_ocr.py')
Invoke-Checked $python @('-m', 'PyInstaller', '--clean', '--noconfirm', '--workpath', 'build', '--distpath', "output/v$version", 'SnapTrans.spec')
if (-not $SkipInteractive) { . (Join-Path $PSScriptRoot 'smoke_package.ps1') }
if (-not $SkipPackage) { Invoke-Checked $python @('scripts/package_release.py') }
