Combat Lab Workbench
====================

1. Unzip this folder anywhere, for example D:\Claude\Model viewer.
2. Double-click start_workbench.bat.
   - It needs Python 3 (https://www.python.org/downloads/ - tick "Add python.exe to PATH" when installing).
   - The first start downloads four libraries (numpy, scipy, trimesh, python-fcl); later starts are quick.
   - The first build also unpacks the unit library once (a few seconds).
3. Your browser opens http://127.0.0.1:8765/ . If it opens before the server is ready, refresh the page.
4. Keep the black window open while you use the page. Close it to stop the workbench.

The page only talks to this computer (127.0.0.1); nothing is sent anywhere else.
