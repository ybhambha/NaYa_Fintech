@echo off
set PYTHONIOENCODING=utf-8
cd /d C:\Users\bhamb\Yash\NaYa_Fintech_Code\projects\semisector
C:\Users\bhamb\anaconda3\python.exe -X utf8 main.py --email sw2cfa@hotmail.com --no-options --summary-only
cd /d C:\Users\bhamb\Yash\NaYa_Fintech_Code
git add -f projects/semisector/reports/
git commit -m "Daily report auto-push %date%"
git push