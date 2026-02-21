@echo off
setlocal

:: Create a virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

:: Activate the virtual environment
call venv\Scripts\activate.bat

:: Install requirements
pip install -r requirements.txt -q

:: Run the migration script with all passed arguments
python migrate.py %*
