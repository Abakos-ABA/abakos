"""Masken-Moderator Modus rede (tools/maske_bewegung.py, 07.11.2026): Steuerkurven ohne Spruenge, Rueckfall bei Fehlern."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import maske_bewegung as mb  # noqa: E402
import weltlage_maskenformat as mf  # noqa: E402


def _huellkurve(sek=12.0):
    n = int(sek * mb.FPS)
    env = np.zeros(n, np.float32)
    acc = np.zeros(n, np.float32)
    for a, b in ((25, 100), (130, 220), (260, 290)):          # drei Phrasen mit Pausen dazwischen
        env[a:b] = 0.8
    for i in (40, 80, 150, 200):
        acc[i] = 0.9
    return np.stack([env, acc], 1)


def test_phrasen_und_betonungen():
    hk = _huellkurve()
    sprech = np.clip(mb._glatt(hk[:, 0], 0.3) / 0.4, 0, 1)
    assert len(mb.phrasen(sprech)) == 3
    assert [i for i, _ in mb.betonungen(hk[:, 1])] == [40, 80, 150, 200]


def test_steuerung_weich_und_begrenzt():
    hk = _huellkurve()
    n = len(hk)
    s = mb.steuerung_rede(hk, n, seed=3)
    for k in ("dx", "dy", "roll", "k_dx", "k_dy"):
        v = np.asarray(s[k])
        assert v.shape == (n,) and np.isfinite(v).all()
        assert np.abs(np.diff(v)).max() < 1.5, k                # keine Spruenge von Bild zu Bild (Loop-Spruenge)
    assert np.abs(s["dx"]).max() < 12 and np.abs(s["roll"]).max() < 3
    assert 1.0 <= float(s["skala"].min()) and float(s["skala"].max()) <= 1.011


def test_rede_spur_rueckfall(tmp_path, monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("Absicht")
    monkeypatch.setattr(mb, "render", kaputt)
    assert mf.rede_spur(tmp_path / "ton.wav", 5.0, tmp_path / "host_spur.mp4", 1) is None
    assert not (tmp_path / "host_spur.mp4").exists()


def test_rede_aktiv(monkeypatch):
    monkeypatch.setenv("NEWS_MASKEN_ANIM", "rede")
    assert mf.rede_aktiv()
    monkeypatch.setenv("NEWS_MASKEN_ANIM", "")
    assert not mf.rede_aktiv()
