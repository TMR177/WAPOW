@echo off
rem WAPOW desktop demo — the real dash, in a window, driven by SimEngine.
rem Same code that runs on the Pi; with no sensors present every source
rem fails over to the scripted sim drive (modes, alerts, triage, knock).
rem The console window stays open behind the dash — errors land there.
cd /d "%~dp0"
set WAPOW_WINDOWED=1
py -3.10 wapow_dash.py
if errorlevel 1 pause
