# Lipsync-Qualität Latara – Ursachen und Verbesserung (30.09.2026)

Auftrag: rexemre fand die Mundsynchronisation in den Testclips vom 29.09. «nicht immer ganz schön». Bild und Ablauf
bleiben unverändert. Gemessen mit SyncNet (`tools/lipsync_messung.py`, CPU, geeicht: Ton +120 ms → 3 Bilder Versatz).
`offset` > 0 = Mund kommt nach dem Ton. `conf` = SyncNet-Sicherheit (höher = besser).

## Messung alt (Testfassung 29.09., `weltlage_rohschnitt_20260929_freisteller_lipsync_TEST.mp4`)

| Stelle | Versatz | conf |
|---|---|---|
| LatentSync-Ausgabe selbst (Freisteller, s4/s5/s6) | 0 ms | 6,5 / 7,6 / 5,4 |
| Szene 4 stehend im fertigen Schnitt | **+120 ms** | 6,0 |
| Sitz-Meldung 1 im fertigen Schnitt (gerechnet aus Teillängen) | **+80…95 ms** | 6,3 |
| Verabschiedung im fertigen Schnitt | −40 ms | 4,6 |

## Ursachen (nach Gewicht)

1. **Bild-Ton-Versatz im Schnitt (Hauptursache, alle Szenen).** `tools/weltlage_rohschnitt.py` legt pro Teil den Ton
   auf die Soll-Länge L, das Bild hat aber `round(L·24)` Bilder bzw. was xfade/clip liefern. Schon der erste Teil
   (Cold Open + Bumper) war im Bild 98 ms länger als im Ton → alles danach lief ~100 ms hinter dem Ton her, danach
   wanderte der Versatz je Teil um bis zu 58 ms (Ende −56 ms). Ab ~45 ms sieht man den Unterschied.
2. **Sitz-Szene: Quellvideo «spricht» selbst mit.** Der Sitz-Master (Wan-Take v3) bewegt den Mund. LatentSync
   (`scripts/inference.py`) nimmt als Referenzbild jedes Eingangsbild selbst; im Training ist die Referenz ein anderes
   Bild. So sickert die fremde Mundbewegung ins Ergebnis (Mund halb offen in Pausen, Lippen gegen den Ton).
3. Stellenweise flau: SyncNet-Fenster mit conf 1–4 fallen auf Pausen, Satzenden und Stückgrenzen (7-s-Stücke).
   Das ist LatentSync-typisch und bleibt teilweise.

## Geprüft, keine (relevante) Ursache

- **Framerate:** Quellen 16 fps (stehend v6, Sitz-Rohmaster) → 25 fps für LatentSync (Pflicht, Modell ist auf 25 fps
  trainiert) → 24 fps im Schnitt. Der 25→24-Schritt lässt 1 Bild pro Sekunde weg, Zeitstempel bleiben, kein Versatz.
  16→25 wiederholt Bilder des Körpers, der Mund wird pro 25-fps-Bild neu erzeugt. Nicht die Ursache.
- **Auflösung Gesichtsausschnitt:** stehend Gesicht ~105 px im Freisteller, Fenster 230 px → 768 px hochskaliert,
  LatentSync arbeitet intern auf 512 px (1.6). Sitz: Gesicht ~243 px, Fenster 534 px. Im Studio ist das Gesicht danach
  nur ~60 px gross (stehend Skala 0,60, sitzend 0,25) – mehr Eingangsauflösung würde man im Endbild nicht sehen.
- **Zweites Skalieren nach dem Lipsync:** gibt es nicht mehr – Freisteller wird direkt in 1920x1080 ins Studio gesetzt
  (Regel 29.09.). SyncNet sinkt vom Freisteller zum Studio (7,9 → 7,0) nur, weil das Gesicht klein wird.
- **Ramona-Stimme:** 16 kHz mono (passt zu Whisper in LatentSync), Pegel −15 dB mittel, Spitze 0 dBFS mit 2–7 geclippten
  Samples pro Datei (hörbar kaum, für Lipsync egal), 0,13–0,15 s Stille am Anfang + 0,25 s Vorlauf der Pipeline: gut.
- **LatentSync-Einstellungen:** Modell ist LatentSync 1.6 (neueste, `models/latentsync/config.json`), guidance 2,5
  (Probe 29.09.), Seed fest 1247. 30 statt 20 Schritte und ohne DeepCache: conf 7,88 statt 7,90 bei 2,2-facher
  Rechenzeit (236 s statt 108 s pro 6,6-s-Stück) → bringt nichts, bleibt bei 20 Schritten mit DeepCache.
- **Alternativen** (MuseTalk, Wav2Lip-HQ): nicht installiert; MuseTalk arbeitet auf 256 px und ist in SyncNet-Vergleichen
  schwächer als LatentSync 1.6, Wav2Lip-HQ wirkt verwaschen. Nicht realistisch besser in wenigen Stunden → nicht verfolgt.

## Verbesserung (Messung neu)

| Clip (15 s bzw. 14,2 s) | Versatz alt → neu | conf alt → neu |
|---|---|---|
| sitzend, im Studio 1920x1080 | +80 ms → **0 ms** | 6,34 → **6,98** |
| sitzend, Freisteller (nur LatentSync) | 0 → 0 | 7,57 → **7,90** |
| stehend (Szene 4), im Studio | +120 ms → **0 ms** | 6,24 → **7,39** |
| stehend, Freisteller (nur LatentSync) | 0 → 0 | 6,53 → 6,54 (Idle-Mund bewegt sich kaum, Gewinn kommt vom Versatz) |

Neue Bausteine (neue Dateien, nichts Bestehendes geändert):
- `tools/latentsync_ref_inference.py` – LatentSync-Inferenz wie `scripts.inference`, aber Referenzbild = Bild mit dem
  geschlossensten Mund im Stück (insightface-106-Landmarken, Kopf nahe Stückmitte). `--ref_mode self` = altes Verhalten.
- `tools/av_sync.py` – `align_parts(parts, FPS, SR, work)`: Ton jedes Teils auf exakt Bildanzahl/FPS vor dem Verketten.
- `tools/lipsync_v2_test.py` – Vergleichslauf mit wählbaren Einstellungen (eigener Cache `data/_latentsync_cache_v2/`).
- `tools/lipsync_messung.py` – SyncNet-Messung (Versatz + conf, auch pro 2-s-Fenster).

## Einbau in die Pipeline (offen, sobald kein Render/Umbau mehr an den Dateien arbeitet)

1. `video/freisteller_lipsync.py`, `sync_chunk`: statt `"-m", "scripts.inference"` den Pfad
   `ROOT / "tools" / "latentsync_ref_inference.py"` aufrufen und `"--ref_mode", "closed"` anhängen; im Cache-Hash
   (`h.update(json.dumps([...]))`) `"refclosed"` ergänzen, damit alte Stücke nicht wiederverwendet werden.
   Nur für die Sitz-Pose zwingend; stehend (Mund im Idle geschlossen) schadet es nicht.
2. `tools/weltlage_rohschnitt.py`, Abschnitt «Zusammenfügen», vor `audio.txt`: `parts = align_parts(parts, FPS, SR, work)`.
3. Danach mit `tools/lipsync_messung.py` den fertigen Schnitt stichprobenweise messen: Versatz muss 0 (±1 Bild) sein.

## Vergleichsclips für rexemre (`data\weltlage_test_20260929\`)

- `vergleich_sitzend_ALT.mp4` / `vergleich_sitzend_NEU.mp4` – 15 s Sitz-Meldung Fairford im Studio. ALT = alter
  Lipsync (`_schnitt_freisteller_TEST\_freisteller\s5_studio.mp4`) mit dem Versatz, den der Voll-Render an dieser Stelle
  hatte (Bild 95 ms hinter dem Ton). NEU = Referenzbild-Fix + bildgenauer Ton.
- `vergleich_stehend_ALT.mp4` / `vergleich_stehend_NEU.mp4` – 14,2 s Szene 4 stehend. ALT = direkt aus dem Voll-Render
  geschnitten (mit Abo-Symbol), NEU = gleicher Ausschnitt/Ton neu (ohne Abo-Symbol, das kommt erst im Schnitt).
- `vergleich_sitzend_gesicht_ALT_NEU.mp4`, `vergleich_stehend_gesicht_ALT_NEU.mp4` – Gesicht 4,8-fach vergrössert,
  links ALT, rechts NEU, gleicher Ton; so sieht man Versatz und Mundform direkt nebeneinander.
- Arbeitsdateien: `data\weltlage_test_20260929\_lipsync_v2\` (Varianten A = gewählt, B = 30 Schritte ohne DeepCache).

Hinweis: Der parallel laufende Render `weltlage_rohschnitt_20260929_ramona_TEST.mp4` (30.09.) ist noch ohne diese
Verbesserung gebaut und hat denselben Schnitt-Versatz.
