@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0git_sync.ps1" %*
