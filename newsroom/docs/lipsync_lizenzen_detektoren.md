# Kommerziell freie Gesichtserkennung im Lipsync (Task 767c, 22.10.2026)

Anlass: Lizenzprüfung (`jarvis/reports/lipsync_lizenzen_20261022.md`): LatentSync 1.6 selbst ist kommerziell nutzbar
(Apache 2.0 + OpenRAIL++), aber der Detektor lud InsightFace buffalo_l (Modelle nur nicht-kommerziell). Der Kanal soll
ins YouTube-Partnerprogramm.

## Umbau
- `video/lipsync_detektoren.py`: Detektoren `mediapipe` (Face Mesh, Apache 2.0, Standard), `mediapipe_bild`, `yunet`
  (OpenCV, MIT), `insightface` (alt, nur Vergleich). Schalter: Umgebungsvariable `LIPSYNC_DETEKTOR`; Standard steht in
  `STANDARD`. Feste Versatzwerte in `models/lipsync_detektoren/kalib.json` (6 Zahlen, einmalig gegen InsightFace-Ausgaben
  auf den Testclips bestimmt mit `tools/lipsync_detektor_kalibrieren.py`; zur Laufzeit kein InsightFace).
- `vendor/LatentSync/latentsync/utils/face_detector.py` delegiert an das Modul (Original: `face_detector.insightface_orig.py`).
  `vendor/` ist nicht in Git: nach einem neuen Klon diese Datei erneut anpassen.
- `video/gesicht_hd.py: kps_of()` (GFPGAN-Gesichtspunkte) nutzt bei freiem Detektor MediaPipe (5 Punkte aus dem Mesh).
- `tools/latentsync_ref_inference.py` braucht nichts: es ruft denselben FaceDetector (Mundpunkte kommen aus den Lippenpunkten).
- Tests: `tests/test_lipsync_detektoren.py`. Messwerkzeuge: `tools/lipsync_detektor_test.py` (LatentSync je Detektor über
  die GPU-Warteschlange), `tools/lipsync_detektor_messen.py` (SyncNet + Vergleichsclip), `lipsync_messung.py` liefert jetzt auch `lse_d`.

## Messung (je 6 s, Stufe 2 = 5 Schritte, guidance 1,5, Referenz Mund zu; Clips von Task c49b: Nahaufnahme sitzend, stehende Totale)
| Clip | Detektor | LSE-C | LSE-D | Versatz | Flackern Oberkopf (Eingang 7,95 / 5,45) | Mundschärfe |
|---|---|---|---|---|---|---|
| sitz | InsightFace (alt) | 3,95 | 8,30 | 0 ms | 7,65 | 11,8 |
| sitz | MediaPipe | 4,10 | 8,17 | 0 ms | 7,63 | 11,5 |
| sitz | YuNet | 4,15 | 8,27 | 0 ms | 7,65 | 11,4 |
| stehend | InsightFace (alt) | 5,87 | 7,89 | 0 ms | 5,39 | 9,6 |
| stehend | MediaPipe | 5,85 | 7,93 | 0 ms | 5,45 | 9,5 |
| stehend | YuNet | 5,58 | 7,98 | 0 ms | 5,36 | 8,9 |

Detektor allein (150 Bilder, 512er-Raster, Anker Braue/Nase): Trefferquote überall 100 %; Zittern der Anker (Std. 2. Differenz, px)
sitz 5,2 alt / 5,6 MediaPipe / 11,7 YuNet, stehend 6,4 / 6,6 / 8,7; Abweichung zu alt 2,6-3,2 px (MediaPipe), 6,6-8,1 px (YuNet);
Zeit pro Bild 21-25 ms MediaPipe, ~240 ms YuNet (mit Randauffüllung), 680-760 ms alt (nur CPU, ONNX-CUDA fehlt im venv).
Folge: MediaPipe spart bei 25 fps rund 0,65 s pro Bild = ca. 16 min pro Minute Lipsync-Video Detektorzeit (bei einem Aufruf pro Bild).
Entscheid: MediaPipe (Video-Modus) ist Standard; gleiche Qualität, viel schneller. YuNet hat keine Mundpunkte (Referenzbild-Wahl
schlechter) und zittert doppelt so stark. Vergleichsclip: `jarvis/reports/lipsync_detektor_vergleich_20261022.mp4`.

## Lizenzstand der übrigen Pipeline (Quellen: Code/Modellkarten/Projektdoku, keine Rechtsberatung)
| Baustein | Lizenz | Stand |
|---|---|---|
| LatentSync 1.6 Code/UNet | Apache 2.0 / OpenRAIL++ | ok |
| InsightFace buffalo_l | nur nicht-kommerziell | **ersetzt** (Dateien liegen noch in vendor/LatentSync/checkpoints/auxiliary, unbenutzt) |
| Real-ESRGAN x2/x4plus, GFPGAN 1.4 (spandrel) | BSD-3 / Apache 2.0 | ok (Trainingsdaten FFHQ bei GFPGAN: Restunsicherheit) |
| CodeFormer | S-Lab, nur nicht-kommerziell | **nicht in Weltlage**, aber Standard in `cinema_factory/cinema/face.py` (Kanal Reel Revival), Job «CodeFormer s1» lief heute |
| Chatterbox (Latara-Stimme), Referenz Piper Ramona/M-AILABS | MIT / M-AILABS frei kommerziell | ok |
| Kokoro, Piper-Engine, faster-whisper | Apache 2.0 / MIT / MIT | ok |
| XTTS-v2, F5-TTS-German, Fish/OpenAudio, MusicGen | NC | im Code ausgeschlossen bzw. ersetzt durch ACE-Step 1.5 (MIT) |
| Stable Audio Open 1.0 (alte Intro-Version) | Stability Community (kommerziell unter 1 Mio. USD Jahresumsatz) | historisch, Intro seit 29.09. ACE-Step; prüfen, ob Reste aktiv |
| Wan 2.2 TI2V-5B, FLUX.2 klein 4B | Apache 2.0 | ok (FLUX.2 dev/klein 9B gesperrt) |
| Depth-Anything-V2-Small (Outro) | Apache 2.0 | ok, nur Small (Base/Large/Giant sind CC-BY-NC) |
| BiRefNet | MIT (nicht neu geprüft) | gegenprüfen |
| SyncNet (nur Messung) | nicht im Produkt | unkritisch |
| B-Roll | Filter `lizenz_pruefen`: CC0/PD/CC-BY(-SA), NC/ND verworfen, Pexels/Pixabay | ok, Attribution in broll_attribution.txt |
| MuseTalk (Test c49b) | MIT; nutzt face_alignment (BSD) + S3FD-Gewichte | S3FD-Gewichte-Lizenz vor Produktionseinsatz klären |
