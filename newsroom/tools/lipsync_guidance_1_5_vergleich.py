"""Lipsync-Vergleich 2,0 (bisheriger Standard) gegen 1,5 (neuer Standard, Task 20261002-002731-6861).

Faehrt dieselbe Mechanik wie lipsync_guidance_vergleich.py (Task 0180), nur mit den aktuellen zwei Werten.

    .venv-lipsync\\Scripts\\python.exe tools\\lipsync_guidance_1_5_vergleich.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lipsync_guidance_vergleich as lgv  # noqa: E402

lgv.WORK = ROOT / "data" / "lipsync_guidance_1_5_20261002"
lgv.REPORT = Path(r"C:\Users\Marlon\projekte\jarvis\reports\lipsync_guidance_1_5_vergleich_20261002")
lgv.PROGRESS = Path(r"C:\Users\Marlon\projekte\jarvis\tasks\20261002-002731-6861.progress.md")
lgv.VARIANTEN = [("bisher_2_0", 2.0, "BISHER  (guidance 2,0)"), ("neu_1_5", 1.5, "NEU  (guidance 1,5)")]

if __name__ == "__main__":
    lgv.main()
