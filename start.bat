@echo off
rem ============================================================
rem  Fibula - inicia o servidor do jogo
rem  Depois de iniciado, abra http://localhost:7777 no navegador
rem ============================================================
cd /d "%~dp0"

rem gera os assets na primeira execucao (sprites + mapa)
if not exist "client\assets\sprites.png" (
    echo [setup] gerando sprites...
    python tools\gensprites.py
)
if not exist "data\map.json" (
    echo [setup] gerando mapa...
    python tools\genmap.py
)

rem abre o navegador (2s depois, dando tempo do servidor subir)
start "" cmd /c "timeout /t 2 >nul & start "" http://localhost:7777"

python server\main.py
pause
