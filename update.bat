@echo off
REM 抓最新抽選連結並重新產生 index.html / checklist.txt / checklist.csv
setlocal
cd /d "%~dp0"

echo [1/2] 下載並解析最新抽選連結...
python extract.py
if errorlevel 1 goto fail

echo.
echo [2/2] 產生 index.html 與清單...
python build.py
if errorlevel 1 goto fail

echo.
echo 完成。用瀏覽器開啟 index.html 即可。
goto end

:fail
echo.
echo 失敗了。請確認已安裝 Python 並且網路正常。

:end
pause
endlocal
