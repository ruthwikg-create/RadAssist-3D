@echo off
setlocal
cd /d "%~dp0"
if exist "frontend\.next" rmdir /s /q "frontend\.next"
call start-radassist.cmd
