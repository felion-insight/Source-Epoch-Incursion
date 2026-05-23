@echo off
REM 先结束占用 8787 的旧进程再起 API（不重设系统脚本策略；等价于 Bypass 跑一次 inline PowerShell）
cd /d "%~dp0"
echo cwd=%CD%

powershell -NoProfile -ExecutionPolicy Bypass -Command "$port=8787; $c=@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue); foreach ($x in $c) { $p=[int]$x.OwningProcess; Write-Host '[restart]' 'Kill PID' $p 'on port' $port; Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 700"

echo 启动 python -u -m game （Ctrl+C 结束）
python -u -m game
pause
