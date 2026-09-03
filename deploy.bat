@echo off
REM ============================================================
REM  One-click update + deploy
REM  Fetch latest links -> rebuild index.html -> push to GitHub
REM ============================================================
setlocal
cd /d "%~dp0"

echo ============================================
echo [1/4] Fetching latest draw links...
echo ============================================
python extract.py
if errorlevel 1 goto fail

echo.
echo ============================================
echo [2/4] Building index.html...
echo ============================================
python build.py
if errorlevel 1 goto fail

echo.
echo ============================================
echo [3/4] Committing changes...
echo ============================================
git add -A
git commit -m "update %date% %time%"
if errorlevel 1 (
  echo No changes detected, skipping upload.
  goto done
)

echo.
echo ============================================
echo [4/4] Pushing to GitHub...
echo ============================================
git branch -M main
git push -u origin main
if errorlevel 1 goto pushfail

:done
echo.
echo ============================================
echo  Done! Wait about 1 minute, then refresh:
echo  https://yang-hua-11.github.io/funbox-line/
echo ============================================
goto end

:fail
echo.
echo [ERROR] Failed to fetch data or build page.
echo  Make sure you have internet and Python installed.
goto end

:pushfail
echo.
echo [ERROR] Upload failed.
echo  If a login window appeared, finish login then run this again.
goto end

:end
echo.
pause
endlocal
