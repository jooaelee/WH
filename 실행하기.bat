@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title 창고 수요예측 - 실행 중
cd /d "%~dp0"

echo ============================================
echo   창고 수요예측 프로그램을 시작합니다
echo ============================================
echo.

REM ---- 1) Python 설치 여부 확인 -------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo.
    echo   1. https://www.python.org/downloads/ 접속
    echo   2. "Download Python" 버튼으로 설치파일 다운로드 후 실행
    echo   3. 설치 화면 맨 아래 "Add python.exe to PATH" 체크박스를 반드시 체크
    echo   4. 설치가 끝나면 이 파일을 다시 더블클릭하세요.
    echo.
    pause
    exit /b 1
)

REM ---- 2) 가상환경이 없으면 최초 1회 자동 설치 ------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo 처음 실행이시네요. 필요한 프로그램을 준비합니다. ^(수 분 정도 걸릴 수 있습니다^)
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo [오류] 가상환경 생성에 실패했습니다.
        pause
        exit /b 1
    )

    echo 필요한 라이브러리를 설치하는 중입니다...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [오류] 라이브러리 설치에 실패했습니다. 인터넷 연결을 확인해주세요.
        pause
        exit /b 1
    )
    echo.
    echo 준비가 완료되었습니다.
    echo.
)

REM ---- 3) 실행: 잠시 후 브라우저가 자동으로 열립니다 ------------------------
echo 프로그램을 시작합니다. 잠시 후 브라우저 창이 자동으로 열립니다...
echo ^(이 검은 창은 프로그램이 켜져있는 동안 계속 열려 있어야 합니다^)
echo ^(끄시려면 이 창을 닫거나 Ctrl+C 를 누르세요^)
echo.

".venv\Scripts\python.exe" -m streamlit run app.py

pause
