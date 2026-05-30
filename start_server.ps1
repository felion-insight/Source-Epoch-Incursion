# ============================================================
#  源纪元 · 岸线侵入  —  一键启动（PowerShell）
#  同时启动 游戏API(8787) + 静态文件服务(8080)
# ============================================================
#  右键本文件 -> "使用 PowerShell 运行"
#  或在终端： .\start_server.ps1
# ============================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  源纪元 · 岸线侵入  服务器启动中..." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  游戏 API  : http://127.0.0.1:8787" -ForegroundColor Green
Write-Host "  大地图页面 : http://127.0.0.1:8080/web/explorer/" -ForegroundColor Green
Write-Host "  状态检查   : http://127.0.0.1:8787/api/health" -ForegroundColor Green
Write-Host ""
Write-Host "  按 Ctrl+C 停止所有服务" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 加载 .env 文件（如果存在）
$envPath = Join-Path $ScriptDir ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line -split "=", 2
            $key = $parts[0].Trim()
            $value = $parts[1].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
    Write-Host "  [OK] 已加载 .env 配置" -ForegroundColor DarkGray
}

# 生产模式：关闭调试 API
$env:GAME_DEBUG_API = "0"

# 启动游戏 API（后台窗口）
Write-Host "  [1/2] 启动游戏 API (端口 8787)..." -ForegroundColor Cyan
$apiJob = Start-Process -FilePath "python" -ArgumentList "-u", "-m", "game" -WorkingDirectory $ScriptDir -WindowStyle Minimized -PassThru
Write-Host "  [OK] 游戏 API 已启动 (PID: $($apiJob.Id))" -ForegroundColor Green

# 等待 API 就绪
Start-Sleep -Seconds 2

# 启动静态文件服务器（当前窗口）
Write-Host "  [2/2] 启动静态文件服务 (端口 8080)..." -ForegroundColor Cyan
Write-Host ""

try {
    python -m http.server 8080 --bind 127.0.0.1
} finally {
    Write-Host "`n正在停止游戏 API..." -ForegroundColor Yellow
    Stop-Process -Id $apiJob.Id -Force -ErrorAction SilentlyContinue
    Write-Host "服务已全部停止。" -ForegroundColor Gray
}
