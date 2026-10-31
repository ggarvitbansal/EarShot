@echo off
REM Earshot - double click, then open http://127.0.0.1:8010
cd /d "%~dp0"
if not exist backend\.venv (
  pushd backend && uv venv --python 3.12 .venv && uv pip install fastapi "uvicorn[standard]" && popd
)
if not exist frontend\dist (
  pushd frontend && call npm install && call npm run build && popd
)
pushd backend
call .venv\Scripts\activate.bat
python -m uvicorn app:app --host 127.0.0.1 --port 8010
popd
