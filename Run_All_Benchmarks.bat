@echo off
REM ============================================================================
REM  GEEKOM A9 Max - full local AI benchmark suite.
REM  Runs on the configured GEEKOM host (the machine with Lemonade + Radeon 890M + NPU).
REM  This runs ALL enabled models across ALL categories - it is long-running.
REM  For a quick staged validation use:  python scripts\run_all.py --models gemma-4-E2B-it
REM ============================================================================
setlocal
cd /d "%~dp0"
if errorlevel 1 (
  echo [FATAL] Could not cd to the repo root.
  exit /b 1
)

set PY=python

echo === [1/10] Environment check ===
%PY% scripts\check_environment.py
if errorlevel 1 (
  echo [FATAL] Environment check FAILED. Aborting so we do not run a broken suite.
  exit /b 1
)

echo === [2/10] Speed benchmarks ===
%PY% scripts\run_benchmarks.py --models all

echo === [3/10] Tool reliability ===
%PY% scripts\run_tool_reliability.py --models all --trials 20

echo === [4/10] Structured output ===
%PY% scripts\run_structured.py --models all

echo === [5/10] Coding ===
%PY% scripts\run_coding_tasks.py --models all

echo === [6/10] Vision ===
%PY% scripts\run_vision_tasks.py --models vision

echo === [7/10] Long context ===
%PY% scripts\run_longcontext.py --models all

echo === [8/10] Agent workflow ===
%PY% scripts\run_agent_workflow.py --models all

echo === [9/10] Generate report ===
%PY% scripts\generate_report.py

echo === [10/10] Open report ===
start "" "%CD%\results\reports\latest_report.html"

echo Done.
endlocal
