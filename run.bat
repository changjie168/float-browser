@echo off
cd /d %~dp0
python -c "import webview" >nul 2>&1 || pip install -r requirements.txt
python float_browser.py
