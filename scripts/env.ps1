$ErrorActionPreference = 'Stop'
$snapRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$versionLine = Get-Content -LiteralPath (Join-Path $snapRoot 'snaptrans/__init__.py') | Where-Object { $_ -match '^__version__ = ' }
$snapVersion = ($versionLine -split '"')[1]
$parentEnv = [IO.Path]::GetFullPath((Join-Path $snapRoot '../../project-env.ps1'))
$nestedProject = Test-Path -LiteralPath $parentEnv
if ($nestedProject) { . $parentEnv } else { . (Join-Path $snapRoot 'project-env.ps1') }
# Short junctions stay inside the parent project; their contents live in SnapTrans.
# This avoids pip's long extraction paths without changing Windows policy.
$snapAliases = @{}
foreach ($kind in $(if ($nestedProject) { @('.tmp', '.cache') } else { @() })) {
    $target = Join-Path $snapRoot $kind
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    $alias = Join-Path (Split-Path $parentEnv) "$kind/st"
    if (-not (Test-Path -LiteralPath $alias)) {
        New-Item -ItemType Junction -Path $alias -Target $target | Out-Null
    }
    $linked = Get-Item -LiteralPath $alias
    if ($linked.LinkType -ne 'Junction' -or [IO.Path]::GetFullPath([string]$linked.Target) -ne $target) {
        throw "SnapTrans cache alias is already occupied: $alias"
    }
    $snapAliases[$kind] = $alias
}
$snapEnvironment = @{
    TEMP = '.tmp'; TMP = '.tmp'; TMPDIR = '.tmp'
    PIP_CACHE_DIR = '.cache/pip'; UV_CACHE_DIR = '.cache/uv'
    UV_PYTHON_INSTALL_DIR = '.cache/python'; UV_PYTHON_BIN_DIR = '.cache/bin'
    PYTHONPYCACHEPREFIX = '.cache/pycache'; PYINSTALLER_CONFIG_DIR = '.cache/pyinstaller'
    XDG_CACHE_HOME = '.cache'; MPLCONFIGDIR = '.cache/matplotlib'
}
foreach ($entry in $snapEnvironment.GetEnumerator()) {
    $resolved = Join-Path $snapRoot $entry.Value
    foreach ($kind in $snapAliases.Keys) {
        if ($entry.Value.StartsWith($kind)) {
            $resolved = $snapAliases[$kind] + $entry.Value.Substring($kind.Length).Replace('/', '\')
        }
    }
    New-Item -ItemType Directory -Path $resolved -Force | Out-Null
    [Environment]::SetEnvironmentVariable($entry.Key, $resolved, 'Process')
}
$env:PYTHONUTF8 = '1'
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Executable" }
}
