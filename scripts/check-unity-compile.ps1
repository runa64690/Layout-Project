# Type-check against actual installed Unity assemblies; does not run the Editor.
param([string]$EditorData = 'C:/Program Files/Unity/Hub/Editor/6000.3.6f1/Editor/Data')
$ErrorActionPreference = 'Stop'
$layoutRoot = Split-Path -Parent $PSScriptRoot
$layoutOutput = Join-Path $layoutRoot 'outputs/unity-static'
New-Item -ItemType Directory -Force -Path $layoutOutput | Out-Null
$layoutTemplate = Get-ChildItem -LiteralPath (Join-Path $EditorData 'Resources/PackageManager/ProjectTemplates/libcache') -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'ScriptAssemblies/Unity.RenderPipelines.Universal.Runtime.dll') } | Select-Object -First 1
if (-not $layoutTemplate) { throw 'No URP template assemblies available; run the Unity Editor compile instead.' }
$layoutRefs = @((Join-Path $EditorData 'NetStandard/ref/2.1.0/netstandard.dll'))
$layoutRefs += Get-ChildItem -LiteralPath (Join-Path $EditorData 'Managed/UnityEngine') -Filter '*.dll' | Select-Object -ExpandProperty FullName
$layoutRefs += Get-ChildItem -LiteralPath (Join-Path $layoutTemplate.FullName 'ScriptAssemblies') -Filter '*.dll' |
    Where-Object { $_.Name -match '^(UnityEngine\.UI\.dll|Unity\.(ugui|RenderPipelines\.(Core|Universal)\.(Runtime|Config)|Mathematics))' } | Select-Object -ExpandProperty FullName
$layoutSources = Get-ChildItem -LiteralPath (Join-Path $layoutRoot 'unity/Assets/Scripts') -Filter '*.cs' | Select-Object -ExpandProperty FullName
$layoutSources += Get-ChildItem -LiteralPath (Join-Path $layoutRoot 'unity/Assets/Editor') -Filter '*.cs' | Select-Object -ExpandProperty FullName
$layoutResponse = @('-nologo','-target:library','-nostdlib+','-langversion:9','-define:UNITY_EDITOR,UNITY_6000_3_OR_NEWER',('-out:"' + (Join-Path $layoutOutput 'Layout.Check.dll') + '"'))
$layoutResponse += $layoutRefs | ForEach-Object { '-r:"' + $_ + '"' }
$layoutResponse += $layoutSources | ForEach-Object { '"' + $_ + '"' }
$layoutResponseFile = Join-Path $layoutOutput 'compile.rsp'
[System.IO.File]::WriteAllLines($layoutResponseFile, $layoutResponse, [System.Text.UTF8Encoding]::new($false))
& (Join-Path $EditorData 'NetCoreRuntime/dotnet.exe') (Join-Path $EditorData 'DotNetSdkRoslyn/csc.dll') ('@' + $layoutResponseFile)
if ($LASTEXITCODE -ne 0) { throw 'Unity C# static compilation failed.' }
Write-Output 'UNITY_STATIC_COMPILE_OK (runtime and editor sources; no Editor execution)'
