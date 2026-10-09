# Standalone checkout environment. Changes affect this process and its children only.
$snapProjectRoot = $PSScriptRoot
foreach ($entry in @{
    TEMP='.tmp'; TMP='.tmp'; TMPDIR='.tmp'; PIP_CACHE_DIR='.cache/pip';
    UV_CACHE_DIR='.cache/uv'; UV_PYTHON_INSTALL_DIR='.cache/python';
    UV_PYTHON_BIN_DIR='.cache/bin'; PYTHONPYCACHEPREFIX='.cache/pycache';
    PYINSTALLER_CONFIG_DIR='.cache/pyinstaller'; XDG_CACHE_HOME='.cache';
    MPLCONFIGDIR='.cache/matplotlib'
}.GetEnumerator()) {
    $directory = Join-Path $snapProjectRoot $entry.Value
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    [Environment]::SetEnvironmentVariable($entry.Key, $directory, 'Process')
}
$env:PYTHONUTF8='1'
