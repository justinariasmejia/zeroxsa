@echo off
echo ==========================================
echo    SUBIENDO CAMBIOS A GITHUB (DEPLOY)
echo ==========================================
echo.
echo 1. Agregando archivos...
git add .
echo.

set /p commit_msg="2. Describe brevemente los cambios: "
git commit -m "%commit_msg%"
echo.

echo 3. Subiendo a GitHub...
git push origin main
echo.

echo ==========================================
echo    LISTO!
echo    Ahora ve a tu Apollo Panel y dale a
echo    [RESTART] para que se actualice.
echo ==========================================
pause
