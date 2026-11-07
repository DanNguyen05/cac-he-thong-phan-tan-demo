@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\kv-demo.ps1" -Action up
exit /b %ERRORLEVEL%
