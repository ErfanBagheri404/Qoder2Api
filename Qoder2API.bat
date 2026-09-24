@echo off
setlocal
cd /d "%~dp0"
py qoder2api.py %*
