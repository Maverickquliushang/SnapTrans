. (Join-Path $PSScriptRoot 'env.ps1')
Set-Location -LiteralPath $snapRoot
$python = Join-Path $snapRoot '.venv/Scripts/python.exe'
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Invoke-Checked 'uv' @('pip', 'compile', '--quiet', 'requirements.in', '--python', $python, '--generate-hashes', '--find-links', 'vendor/wheels', '--emit-find-links', '--output-file', 'requirements.lock')
    Invoke-Checked 'uv' @('pip', 'compile', '--quiet', 'requirements-dev.in', '--python', $python, '--constraint', 'requirements.lock', '--generate-hashes', '--find-links', 'vendor/wheels', '--emit-find-links', '--output-file', 'requirements-dev.lock')
} else {
    Invoke-Checked $python @('-m', 'piptools', 'compile', '--quiet', '--generate-hashes', '--find-links=vendor/wheels', '--output-file=requirements.lock', 'requirements.in')
    Invoke-Checked $python @('-m', 'piptools', 'compile', '--quiet', '--generate-hashes', '--find-links=vendor/wheels', '--constraint=requirements.lock', '--output-file=requirements-dev.lock', 'requirements-dev.in')
}
