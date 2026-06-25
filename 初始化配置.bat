@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "初始化配置.py" || py "初始化配置.py"
pause
