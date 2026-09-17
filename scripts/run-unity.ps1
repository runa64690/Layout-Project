param(
    [ValidateSet('LayoutProjectSetup.SmokeChecks', 'LayoutProjectSetup.BuildWeb', 'LayoutProjectSetup.BuildAndroid')]
    [string]$Method = 'LayoutProjectSetup.SmokeChecks',
    [switch]$Graphics
)
$ErrorActionPreference = 'Stop'
$layoutRoot = Split-Path -Parent $PSScriptRoot
$layoutProject = Join-Path $layoutRoot 'unity'
$layoutLog = Join-Path $layoutRoot ('outputs/' + $Method + '.log')
$layoutEditor = 'C:/Program Files/Unity/Hub/Editor/6000.3.6f1/Editor/Unity.exe'
if (-not (Test-Path -LiteralPath $layoutEditor)) { throw "Unity 6000.3.6f1 is not installed at $layoutEditor" }
New-Item -ItemType Directory -Force -Path (Join-Path $layoutRoot 'outputs') | Out-Null
$layoutArgs = @('-batchmode', '-projectPath', ('"' + $layoutProject + '"'), '-executeMethod', $Method, '-logFile', ('"' + $layoutLog + '"'))
$layoutArgs += '-quit'
if ($Method -eq 'LayoutProjectSetup.BuildAndroid') { $layoutArgs += @('-buildTarget', 'Android') }
if ($Method -eq 'LayoutProjectSetup.BuildWeb') { $layoutArgs += @('-buildTarget', 'WebGL') }
if (-not $Graphics) { $layoutArgs += '-nographics' }
$layoutProcess = Start-Process -FilePath $layoutEditor -ArgumentList $layoutArgs -WindowStyle Hidden -PassThru
Write-Output "Unity PID: $($layoutProcess.Id)"
Write-Output "Log: $layoutLog"
