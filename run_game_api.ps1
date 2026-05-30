# 在仓库根启动剧情 API（避免 PowerShell 里误用 cmd 的 `cd /d`）
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }
Set-Location -LiteralPath $root
# 默认开启开发者调试 API（$env:GAME_DEBUG_API=0 可关闭）
$env:GAME_DEBUG_API = "1"
Write-Host "cwd=$(Get-Location)"
Write-Host "GAME_DEBUG_API=$env:GAME_DEBUG_API"
Write-Host '启动 python -u -m game （停止请 Ctrl+C）'
python -u -m game
