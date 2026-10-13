@echo off
echo ========================================================
echo Launching SKIPP'D Solar Forecasting Studio Web App
echo URL: http://127.0.0.1:5000
echo ========================================================
start http://127.0.0.1:5000
.\.venv\Scripts\python.exe web_server.py
pause
