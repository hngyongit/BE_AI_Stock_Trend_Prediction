param(
    [int]$Port = 5567
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$HomeDir = Join-Path $ProjectRoot ".data_formulator"
$PluginDir = Join-Path $ProjectRoot "tools\data-formulator\plugins"

New-Item -ItemType Directory -Force $HomeDir | Out-Null
New-Item -ItemType Directory -Force $PluginDir | Out-Null

$env:DATA_FORMULATOR_HOME = $HomeDir
$env:DF_PLUGIN_DIR = $PluginDir
$env:WORKSPACE_BACKEND = "local"

Write-Host "Starting Data Formulator..."
Write-Host "URL: http://localhost:$Port"
Write-Host "DATA_FORMULATOR_HOME=$env:DATA_FORMULATOR_HOME"
Write-Host "DF_PLUGIN_DIR=$env:DF_PLUGIN_DIR"

uvx data_formulator --port $Port --sandbox local
