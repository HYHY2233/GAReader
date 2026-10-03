@echo off
call "%~dp0run.cmd" account %*
set "RUN_RESULT=%errorlevel%"
if not defined PAPER_LIBRARY_NO_PAUSE pause
exit /b %RUN_RESULT%
