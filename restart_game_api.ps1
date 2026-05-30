# 杀掉占用 8787 的旧 Python 再起 API（PowerShell）
# 若双击 / 执行被策略拦截，请用其一：
#   powershell -NoProfile -ExecutionPolicy Bypass -File ".\restart_game_api.ps1"
#   或双击仓库根目录 restart_game_api.cmd（推荐，无需改 ExecutionPolicy）
$ErrorActionPreference = "Continue"
$port = 8787
$listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
foreach ($conn in $listeners) {
    $procId = [int]$conn.OwningProcess
    Write-Host "[restart_game_api] 结束占用端口 $port 的进程 PID=$procId"
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 700
Set-Location -LiteralPath $PSScriptRoot
# 默认开启开发者调试 API（$env:GAME_DEBUG_API=0 可关闭）
$env:GAME_DEBUG_API = "1"
Write-Host "[restart_game_api] cwd=$(Get-Location)"
Write-Host "[restart_game_api] GAME_DEBUG_API=$env:GAME_DEBUG_API"
python -u -m game
