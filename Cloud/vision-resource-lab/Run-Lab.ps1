param(
    [Parameter(Mandatory=$true)][string]$Video,
    [ValidateSet('full', 'right-half')][string]$Crop = 'full',
    [string]$Distribution = 'Ubuntu-24.04',
    [string]$RunName = ('local-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
)
$ErrorActionPreference = 'Stop'
if ($RunName -notmatch '^[A-Za-z0-9_-]+$') { throw 'Invalid run name' }
$TaskVideoPath = (Resolve-Path -LiteralPath $Video).Path
$TaskWslRoot = (& wsl -d $Distribution --exec wslpath -a $PSScriptRoot).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve WSL project path' }
$TaskWslVideo = (& wsl -d $Distribution --exec wslpath -a $TaskVideoPath).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve WSL video path' }
& wsl -d $Distribution --exec bash "$TaskWslRoot/setup_wsl.sh"
if ($LASTEXITCODE -ne 0) { throw 'Environment setup failed' }
& wsl -d $Distribution --exec python3 "$TaskWslRoot/prepare_models.py"
if ($LASTEXITCODE -ne 0) { throw 'Model preparation failed' }
$TaskVenvPython = (& wsl -d $Distribution --exec bash -c 'printf "%s/.cache/evidenceguard-vision-lab/venv/bin/python" "$HOME"').Trim()
& wsl -d $Distribution --exec $TaskVenvPython "$TaskWslRoot/prepare_input.py" $TaskWslVideo --crop $Crop --sample-fps 6
if ($LASTEXITCODE -ne 0) { throw 'Input preparation failed' }
& wsl -d $Distribution --exec bash "$TaskWslRoot/run_bench.sh" $RunName
if ($LASTEXITCODE -ne 0) { throw 'Benchmark failed; inspect results logs' }
& wsl -d $Distribution --exec bash "$TaskWslRoot/run_sustained.sh" $RunName 60
if ($LASTEXITCODE -ne 0) { throw 'Paced replay failed; inspect results logs' }
& wsl -d $Distribution --exec $TaskVenvPython "$TaskWslRoot/report.py" $RunName
if ($LASTEXITCODE -ne 0) { throw 'Report generation failed' }
Write-Host "Finished: $PSScriptRoot\results\$RunName\REPORT.md"
