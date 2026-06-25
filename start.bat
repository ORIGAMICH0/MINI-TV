@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo   正在启动 MiniTV 本地代理...
echo   保持本窗口开着，然后用浏览器打开 MiniTV.html
echo   关闭本窗口 = 停止代理
echo ============================================
python proxy.py
pause
