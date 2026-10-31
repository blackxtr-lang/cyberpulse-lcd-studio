@echo off
cd /d "%~dp0"
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PYEXE%" set "PYEXE=pythonw.exe"
start "" "%PYEXE%" main_gui.py
