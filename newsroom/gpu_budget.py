"""VRAM budget for all newsroom GPU work (Weltlage Kompakt + Steel & Ledger), shared by every wait point.

Old rule: "GTA runs -> nothing touches the GPU". New rule (2026-09-23, Marlon: zocken UND Fortschritt):

    budget = free VRAM (nvidia-smi) - reserve
    reserve = NEWS_GPU_RESERVE_GB (default 3 GB) while a game runs,
              NEWS_GPU_IDLE_RESERVE_GB (default 1 GB) when no game runs (2026-09-24: the 3 GB game reserve
              plus wan_clip's need exceeded the whole 4090 (23 GB), so the Weltlage render waited forever)

A step whose need (STEP_MB) fits into the budget starts right away; bigger steps wait. While a game is
running, GPU work also gets:
  - ComfyUI with --vram-headroom <reserve>: DynamicVRAM keeps that much VRAM free *counting other apps*,
    so a 14B Wan model streams its weights from RAM instead of pushing the game out of VRAM;
  - CPU priority "below normal" and Windows GPU scheduling priority "idle" for every render process
    (set_below_normal; the game's frames get the GPU first, renders take the gaps);
  - a duty cycle: after each item the caller sleeps duty_pause(seconds_worked) so CUDA never saturates
    the card for long stretches (batch 1, strictly sequential);
  - a pressure watchdog: under_pressure() -> True when free VRAM drops under 1 GB (the game grew);
    callers interrupt the ComfyUI job and wait again.

gpu_sparmodus (NEWS_GPU_SPARMODUS): "0" = old behaviour (any game -> every GPU step waits),
"stills" (default) = single-frame Wan images + small steps run next to a game, Wan video waits,
"clips" = Wan video clips too (slow, streamed weights; see docs in the memory note / README).

Central GPU queue (2026-09-29, after four Weltlage renders polled the full card in parallel and three workers timed
out): every GPU wait point also takes a place in Jarvis' queue (projekte/jarvis/tools/gpu_queue.py,
state in jarvis/state/gpu_queue.json): priority first, then arrival, VRAM accounting across all processes, dead
processes freed automatically. slot(step) = context manager, hold(step) = until the process exits; wait_for() now
takes a hold. The game rules above stay here and act as the queue's gate. Queue unreachable -> old behaviour + warning.
Priority: NEWS_GPU_PRIO (default 3 = normal render; 2 = Marlon waits, 4 = background).

CLI:  python gpu_budget.py            -> status line (free, budget, game, what may run)
      python gpu_budget.py log 600    -> log VRAM every 5 s for 600 s to state/gpu_budget_vram.log
"""
import contextlib
import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import config.settings  # noqa: F401  (loads .env so NEWS_GPU_* settings apply however this is imported)
except Exception:
    pass

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BELOW_NORMAL = 0x00004000                                  # BELOW_NORMAL_PRIORITY_CLASS (Popen creationflags too)

GAMES = ("GTA5_Enhanced.exe", "GTA5.exe", "PlayGTAV.exe")
RESERVE_MB = int(float(os.environ.get("NEWS_GPU_RESERVE_GB", "3")) * 1024)               # kept free next to a game
IDLE_RESERVE_MB = int(float(os.environ.get("NEWS_GPU_IDLE_RESERVE_GB", "1")) * 1024)     # kept free without a game
SPARMODUS = os.environ.get("NEWS_GPU_SPARMODUS", "stills").strip().lower()
DUTY = float(os.environ.get("NEWS_GPU_GAME_DUTY", "0.5"))  # share of wall time the GPU works while a game runs
PRESSURE_MB = 1024

# Minimum free VRAM a step needs to start (MB). Measured/estimated 2026-09-23 on the RTX 4090 (23 028 MB):
# Wan 14B fp8 = 13.6 GB weights per expert, but ComfyUI 0.37 DynamicVRAM streams weights from RAM (128 GB),
# so a still runs in a few GB; a 81-frame clip needs activations + VAE decode on top.
STEP_MB = {
    "encode": 300,         # ffmpeg (libx264 = CPU; NVENC ~0.3 GB)
    "cpu": 0,              # captions, cards, mixing, compositing
    "tts": 1200,           # Kokoro
    "whisper": 1000,       # faster-whisper base.en
    "upscale": 1500,       # realesrgan-ncnn-vulkan (tiled)
    "wan_still": 6000,     # Wan 2.2 14B fp8, length=1, streamed weights
    "wan_clip_spar": 9000, # Wan 2.2 14B fp8, 81 frames, streamed weights (only with sparmodus=clips)
    "wan_clip": 18000,     # Wan 2.2 14B fp8, 81 frames, normal (whole card; was 20000 = more than the 4090 has free
                           # next to the desktop apps' ~2.7 GB, ComfyUI DynamicVRAM offloads the rest itself)
    "lipsync": 18000,      # LatentSync 1.6 (own torch process, no offloading)
    "ollama_8b": 6500,     # qwen3:8b
    "enhance": 4200,       # Resemble Enhance (.venv-enhance), gemessen 01.10.: ~3,9 GB Spitze (Task 98b7)
}
HEAVY = {"wan_clip", "lipsync"}                         # never next to a game

# What a step books in the central queue (MB on top of the desktop + Jarvis' voice, which hold ~6-9 GB for good):
# STEP_MB above is "free VRAM needed" and would never fit next to them (lipsync 18 GB + reserve, 29.09.)
QUEUE_MB = {"lipsync": 14000, "wan_clip": 16000, "wan_clip_spar": 9000}
QUEUE_PRIO = int(os.environ.get("NEWS_GPU_PRIO", "3"))
JARVIS_TOOLS = Path(r"C:\Users\Marlon\projekte\jarvis\tools")
_queue_mod = None


def _run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", creationflags=NO_WINDOW).stdout
    return out or ""                                       # stdout is None if the reader thread failed to decode


def vram() -> tuple[int, int, int]:
    """(total, used, free) in MB; (0, 0, 0) if nvidia-smi fails."""
    try:
        t, u, f = (int(x) for x in _run(["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free",
                                          "--format=csv,noheader,nounits"]).strip().splitlines()[0].split(","))
        return t, u, f
    except Exception:
        return 0, 0, 0


def gpu_util() -> int:
    try:
        return int(_run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]).split()[0])
    except Exception:
        return 0


_game_cache: tuple[float, str | None] = (0.0, None)


def game_running() -> str | None:
    global _game_cache
    if time.monotonic() - _game_cache[0] < 5:
        return _game_cache[1]
    out = _run(["tasklist", "/NH", "/FO", "CSV"]).lower()
    found = next((name for name in GAMES if f'"{name.lower()}"' in out), None)
    _game_cache = (time.monotonic(), found)
    return found


def reserve_mb() -> int:
    """VRAM to keep free: the big reserve protects a running game, without a game 1 GB is enough."""
    return RESERVE_MB if game_running() else IDLE_RESERVE_MB


def budget_mb() -> int:
    return vram()[2] - reserve_mb()


def resolve(step: str) -> str:
    """Maps a wish to the variant that is allowed right now (wan_clip -> wan_clip_spar next to a game)."""
    if step == "wan_clip" and SPARMODUS == "clips" and game_running():
        return "wan_clip_spar"
    return step


def policy(step: str) -> str | None:
    """Game rules only (no VRAM measurement): may `step` run next to the game at all? None = yes."""
    step = resolve(step)
    need = STEP_MB[step]
    game = game_running()
    if game:
        if SPARMODUS in ("0", "off", "aus") and need > 0:
            return f"{game.split('.')[0]} läuft (Sparmodus aus)"
        if step == "wan_clip_spar" and SPARMODUS != "clips":
            return f"{game.split('.')[0]} läuft und Videoclips warten (Sparmodus {SPARMODUS})"
        if step in HEAVY:
            return f"{game.split('.')[0]} läuft und der Schritt braucht rund {need // 1024} GB"
    return None


def check(step: str) -> str | None:
    """None if `step` may start now (game rules + free VRAM - reserve), else a German reason for progress notes."""
    reason = policy(step)
    if reason:
        return reason
    need = STEP_MB[resolve(step)]
    free, reserve = vram()[2], reserve_mb()
    if need and free - reserve < need:
        return f"nur {free / 1024:.1f} GB frei, der Schritt braucht {need / 1024:.1f} GB plus {reserve / 1024:g} GB Reserve"
    return None


def wait_for(step: str, progress=None, poll: int = 30, calm: int = 2, note_every: int = 240,
             prio: int | None = None, name: str | None = None) -> str:
    """Blocks until `step` fits; returns the resolved step name. `calm` = free samples in a row needed.
    With the central queue: takes a place until the process exits (hold); without it: polls free VRAM as before."""
    if queue() is not None and hold(step, name=name, prio=prio, progress=progress) is not None:
        return resolve(step)
    t0, ok, last = time.monotonic(), 0, 0.0
    while True:
        why = check(step)
        if why is None:
            ok += 1
            if ok >= calm:
                return resolve(step)
        else:
            ok = 0
            if progress and time.monotonic() - last > note_every:
                last = time.monotonic()
                progress(why, (time.monotonic() - t0) / 60)
        time.sleep(poll)


# ---------------------------------------------------------------- central queue (Jarvis tools/gpu_queue.py)
def queue():
    """The gpu_queue module or None (then everything runs as before, with one warning)."""
    global _queue_mod
    if _queue_mod is None:
        try:
            if str(JARVIS_TOOLS) not in sys.path:
                sys.path.append(str(JARVIS_TOOLS))
            import gpu_queue
            _queue_mod = gpu_queue
        except Exception as e:                                  # noqa: BLE001
            print(f"WARNUNG gpu_budget: GPU-Warteschlange nicht erreichbar ({e}), laufe ohne", file=sys.stderr)
            _queue_mod = False
    return _queue_mod or None


def queue_mb(step: str) -> int:
    return QUEUE_MB.get(step, STEP_MB.get(step, 4000))


def gate(step: str):
    """Game rules as the queue's gate: None = may run; next to a game also the big VRAM reserve (check)."""
    STEP_MB.setdefault(step, queue_mb(step))
    return lambda: policy(step) or (check(step) if game_running() else None)


def _job_name(step: str, name: str | None) -> str:
    return name or f"newsroom {step} ({Path(sys.argv[0]).stem or 'python'})"


def _note(progress):
    if progress:
        return progress
    return lambda why, m: print(f"  warte auf GPU ({m:.0f} min): {why}", flush=True)


@contextlib.contextmanager
def slot(step: str, name: str | None = None, prio: int | None = None, progress=None, vram_mb: int | None = None):
    """Place in the central GPU queue for the with-block (waits for game rules + queue). Fallback: no waiting."""
    q = queue()
    t = None
    if q is not None:
        try:
            t = q.acquire(_job_name(step, name), prio or QUEUE_PRIO, vram_mb or queue_mb(step), gate=gate(step),
                          progress=_note(progress))
        except q.GpuQueueTimeout:
            raise
        except (OSError, TimeoutError) as e:
            print(f"WARNUNG gpu_budget: Warteschlange gestört ({e}), laufe ohne", file=sys.stderr)
    try:
        yield t
    finally:
        if t is not None:
            try:
                q.release(t)
            except Exception as e:                              # noqa: BLE001  (Leichenprüfung räumt sonst auf)
                print(f"WARNUNG gpu_budget: Freigabe gestört ({e})", file=sys.stderr)


def hold(step: str, name: str | None = None, prio: int | None = None, progress=None, vram_mb: int | None = None):
    """Place in the central queue until this process exits (idempotent per name). None = queue unreachable."""
    q = queue()
    if q is None:
        return None
    try:
        return q.hold(_job_name(step, name), prio or QUEUE_PRIO, vram_mb or queue_mb(step), gate=gate(step),
                      progress=_note(progress))
    except q.GpuQueueTimeout:
        raise
    except (OSError, TimeoutError) as e:
        print(f"WARNUNG gpu_budget: Warteschlange gestört ({e}), laufe ohne", file=sys.stderr)
        return None


def under_pressure() -> bool:
    """True when a game runs and free VRAM fell under 1 GB (stop the current job, wait again)."""
    return bool(game_running()) and vram()[2] < PRESSURE_MB


def duty_pause(worked_s: float) -> float:
    """Sleeps so the GPU works only DUTY of the time while a game runs; returns the sleep in s."""
    if not game_running() or DUTY >= 1:
        return 0.0
    pause = min(worked_s * (1 - DUTY) / max(DUTY, 0.05), 300)
    time.sleep(pause)
    return pause


def comfy_args() -> list[str]:
    """Extra ComfyUI CLI args: keep RESERVE free (counting the game) while a game runs."""
    if game_running():
        return ["--vram-headroom", f"{RESERVE_MB / 1024:g}", "--disable-smart-memory"]
    return []


def set_below_normal(pid: int | None = None, gpu_prio: int | None = None) -> bool:
    """CPU priority 'below normal' + Windows GPU scheduling priority for pid (default: this process).
    gpu_prio: D3DKMT class 0=idle, 1=below normal (default: idle while a game runs, else below normal).
    The GPU class is honoured by the WDDM scheduler for CUDA contexts too, so the game's frames win."""
    from ctypes import wintypes as w
    try:
        k, g = ctypes.windll.kernel32, ctypes.windll.gdi32
        k.OpenProcess.restype = w.HANDLE
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        g.D3DKMTSetProcessSchedulingPriorityClass.argtypes = [w.HANDLE, ctypes.c_int]
        h = k.OpenProcess(0x0200 | 0x0400, False, pid or os.getpid())       # SET_ | QUERY_INFORMATION
        if not h:
            return False
        ok = bool(k.SetPriorityClass(h, BELOW_NORMAL))
        if gpu_prio is None:
            gpu_prio = 0 if game_running() else 1
        ok = g.D3DKMTSetProcessSchedulingPriorityClass(h, gpu_prio) == 0 and ok
        k.CloseHandle(h)
        return ok
    except Exception:
        return False


def status() -> str:
    t, u, f = vram()
    game = game_running()
    runs = [s for s in STEP_MB if check(s) is None and not (s == "wan_clip_spar" and SPARMODUS != "clips")]
    return (f"VRAM {u}/{t} MB belegt, {f} MB frei, Budget {f - reserve_mb()} MB (Reserve {reserve_mb()} MB), "
            f"Spiel: {game or '-'}, Sparmodus: {SPARMODUS}, darf jetzt: {', '.join(runs) or '-'}")


def log_vram(seconds: int, path: Path, every: float = 5.0) -> None:
    """Appends 'time used free util game_dedicated_mb' lines (game = GTA's dedicated VRAM via perf counter)."""
    end = time.monotonic() + seconds
    with open(path, "a", encoding="utf-8") as fh:
        while time.monotonic() < end:
            t, u, f = vram()
            fh.write(f"{time.strftime('%H:%M:%S')} used={u} free={f} util={gpu_util()} game={_game_dedicated_mb()}\n")
            fh.flush()
            time.sleep(every)


def _game_dedicated_mb() -> int:
    ps = ("$t=0; (Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage' -ea 0).CounterSamples | % { "
          "if ($_.InstanceName -match 'pid_(\\d+)') { $p = Get-Process -Id $matches[1] -ea 0; "
          "if ($p.ProcessName -like 'GTA5*') { $t += $_.CookedValue } } }; [int]($t/1MB)")
    try:
        return int(_run(["powershell", "-NoProfile", "-Command", ps]).strip() or 0)
    except ValueError:
        return -1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "log":
        log_vram(int(sys.argv[2]) if len(sys.argv) > 2 else 600, Path(__file__).parent / "state" / "gpu_budget_vram.log")
    else:
        print(status())
