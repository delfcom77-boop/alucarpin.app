@echo off
setlocal
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo No encuentro el Python de la aplicacion en .venv\Scripts\python.exe.
  echo Abre la carpeta de Alucarpin y comprueba que existe .venv.
  pause
  exit /b 1
)
"%PYTHON%" -c "import cryptography" >nul 2>&1
if errorlevel 1 (
  echo Instalando la dependencia necesaria para cifrar las copias de OneDrive...
  "%PYTHON%" -m pip install -r "%~dp0requirements-copias.txt"
  if errorlevel 1 (
    echo No se pudo instalar la dependencia de cifrado.
    pause
    exit /b 1
  )
)
"%PYTHON%" "%~dp0copias_diarias.py" --configurar
if errorlevel 1 (
  echo.
  echo La copia diaria no ha quedado configurada. Lee el error y vuelve a intentarlo.
)
pause
