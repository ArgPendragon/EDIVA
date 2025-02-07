# MASTER.ps1
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
 # 1) Activate virtual environment:
. .\.venv\Scripts\activate
# 2) Run your python script
python autogen_go.py
