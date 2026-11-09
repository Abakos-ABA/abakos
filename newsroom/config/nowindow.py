"""No console popups on Windows (2026-09-23).

The scheduled tasks run the pipeline and the bot under pythonw.exe, which has no console. Every
console program started from there without CREATE_NO_WINDOW (ffmpeg, ffprobe, tasklist, nvidia-smi,
the lipsync/TTS pythons) got a brand-new *visible* console window that popped up on Marlon's main
monitor for the length of the call. install() makes CREATE_NO_WINDOW the default for every
subprocess.Popen (subprocess.run/check_output and asyncio subprocesses go through it too), but only
while this process has no console of its own, so manual runs in a terminal keep their output there.
Callers that explicitly ask for a console (CREATE_NEW_CONSOLE, DETACHED_PROCESS) are left alone.
Imported by config/settings.py, which every newsroom entry point loads.
"""
import os
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000
_OWN_CONSOLE_FLAGS = 0x00000008 | 0x00000010   # DETACHED_PROCESS | CREATE_NEW_CONSOLE


def install():
    if os.name != "nt" or getattr(subprocess.Popen, "_nowindow", False):
        return
    if os.path.basename(sys.executable).lower() != "pythonw.exe":
        return   # python.exe always has a console (visible or hidden), children share it, nothing pops up
    import ctypes
    if ctypes.windll.kernel32.GetConsoleWindow():
        return
    orig = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):
        flags = kwargs.get("creationflags", 0) or 0
        if not flags & _OWN_CONSOLE_FLAGS:
            kwargs["creationflags"] = flags | CREATE_NO_WINDOW
        orig(self, *args, **kwargs)

    subprocess.Popen.__init__ = __init__
    subprocess.Popen._nowindow = True


install()
