@echo off
echo Installing Cloud AI's No Recoil Tool...
python -m venv venv
call venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
echo Done! Run the script with: venv\Scripts\python.exe "CLOUDAIV1RECOIL.py"
pause
