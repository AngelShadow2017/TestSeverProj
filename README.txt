TestSeverProj - Compile and Run Guide (Windows PowerShell)

1) Prerequisites
- Python 3.12+ installed
- Use PowerShell in project root:
  E:\Projects\TestSeverProj

2) Compile
This project is Python-based, so no manual compile step is required.
Python will run .py files directly and generate __pycache__ automatically.

Optional syntax check / bytecode compile:
python -m py_compile .\server.py .\test2.py

3) Run the HTTP server
Default run:
python .\server.py

Default behavior:
- host: 0.0.0.0
- port: 16666
- root: .\httpRoot

Custom host/port/root example:
python .\server.py --host 127.0.0.1 --port 8080 --root .\httpRoot

4) Access in browser
If running locally with port 16666:
- http://127.0.0.1:16666/
- http://127.0.0.1:16666/index.html

5) Run parser split test script
The test script feeds HTTP requests in random chunk boundaries to validate stream parsing.

Run:
python .\test2.py

Notes:
- test2.py currently runs 3000 trials with verbose output by default.
- If output is too large, reduce `trials` or set `verbose=False` in test2.py.

6) Quick troubleshooting
- "python is not recognized": install Python and add it to PATH.
- Port already in use: change port with --port.
- 404 or unexpected file response: verify --root points to the correct folder.

