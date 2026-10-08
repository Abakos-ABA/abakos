"""Stimmen-Endpruefung: Korrelation findet den richtigen Versatz auch fuer Szenen ab 0 s (Vorfall 08.10.2026)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from weltlage_stimmpruefung import SR, korrelation  # noqa: E402


def _stimme(sek: float, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0, 3000, int(sek * SR))


def _video(quelle: np.ndarray, start: float, pre: float, laenge: float, gesamt: float) -> np.ndarray:
    ton = np.random.default_rng(99).normal(0, 50, int(gesamt * SR))
    a = int((start + pre) * SR)
    teil = quelle[:int((laenge - pre) * SR)]  # Szene kappt die Quelle am Ende (Bumper)
    ton[a:a + len(teil)] += teil
    return ton


def test_coldopen_ab_null_quelle_laenger_als_szene():
    quelle = _stimme(29.58)
    video = _video(quelle, 0.0, 0.25, 28.78, 45.0)
    assert korrelation(video, 0.0, 28.78, quelle, 0.25) > 0.95


def test_szene_mitten_im_video():
    quelle = _stimme(20.0, seed=2)
    video = _video(quelle, 49.375, 0.25, 20.945, 80.0)
    assert korrelation(video, 49.375, 20.945, quelle, 0.25) > 0.95


def test_fremde_aufnahme_faellt_durch():
    quelle = _stimme(29.58)
    video = _video(_stimme(29.58, seed=7), 0.0, 0.25, 28.78, 45.0)
    assert korrelation(video, 0.0, 28.78, quelle, 0.25) < 0.3
