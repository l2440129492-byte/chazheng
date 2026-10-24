@echo off
chcp 65001 >nul
cd /d %~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File probe.ps1 > ps_log.txt 2>&1
type ps_log.txt
pause
