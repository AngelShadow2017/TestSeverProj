TestSeverProj - Compile and Run Guide (Windows PowerShell)

1) Prerequisites
- Python 3.12+ installed
- Use PowerShell in project root:
  E:\Projects\TestSeverProj

2) Project structure update (important)
Runtime entry files have moved under `src/`:
- Server entry: `src/server.py`
- Parser test entry: `src/test2.py`

Recommended run style (from project root):
- `python -m src.server`
- `python -m src.test2`

Do not use old commands anymore:
- `python .\server.py`
- `python .\test2.py`

3) Optional compile/syntax check
This project is Python-based, so no manual compile step is required.
Python runs `.py` files directly and generates `__pycache__` automatically.

Optional syntax check / bytecode compile:
python -m py_compile .\src\server.py .\src\test2.py

4) Run the HTTP server
Default run:
python -m src.server

Default behavior:
- host: 0.0.0.0
- port: 16666
- root: .\httpRoot

Custom host/port/root example:
python -m src.server --host 127.0.0.1 --port 8080 --root .\httpRoot

5) Access in browser
If running locally with port 16666:
- http://127.0.0.1:16666/
- http://127.0.0.1:16666/index.html

6) Run parser split test script
The test script feeds HTTP requests in random chunk boundaries to validate stream parsing.

Run:
python -m src.test2

Notes:
- `src/test2.py` currently runs 3000 trials with verbose output by default.
- If output is too large, reduce `trials` or set `verbose=False` in `src/test2.py`.

7) External reference (submodule)
The project includes an external repository as a Git submodule:
- Path: `test_files/The-Open-Source-Version-Of-PvZ-Travel`
- URL: `https://github.com/jiangnangame/The-Open-Source-Version-Of-PvZ-Travel.git`
- Tracking branch: `main`

Why submodule:
- The code is pulled locally for use/reference.
- Main repository stores only a submodule pointer (gitlink), not full external source history.

8) Submodule usage
If you clone this project for the first time:
git clone --recurse-submodules <your-main-repo-url>

If already cloned without submodules:
git submodule update --init --recursive

Update submodule to latest `main`:
git submodule update --remote -- test_files/The-Open-Source-Version-Of-PvZ-Travel

After update, record the new pointer in main repo:
git add test_files/The-Open-Source-Version-Of-PvZ-Travel
git commit -m "Update PvZ Travel submodule"

9) Quick troubleshooting
- "python is not recognized": install Python and add it to PATH.
- Port already in use: change port with `--port`.
- 404 or unexpected file response: verify `--root` points to the correct folder.
- Submodule folder is empty: run `git submodule update --init --recursive`.

