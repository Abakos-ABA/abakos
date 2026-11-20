# Weltlage Kompakt – Masken-Format (Spezifikation, 27.10.2026)

> **Seit 20.11.2026: Maskenmann abgeschafft** (Marlon: «Masken-Animation sieht schlecht aus, Maskenmann komplett raus»).
> Folgen und eigene Shorts haben keinen Moderator mehr (`NEWS_MODERATOR=0`, Standard). Die Bildspur baut
> `tools/weltlage_bildspur.py` Satz für Satz aus Kapitelkarten, Satz-/Zahlen-/Zitatkarten auf bewegtem Hintergrund,
> Filmmaterial vollflächig (B-Roll aus `broll/plan.json`, nur kleines «Symbolbild», Lizenzen weiter in der Beschreibung)
> und höchstens 3 Quellen-Screenshots je Folge (nur Domain als Etikett). Shorts: grosse Stichwortkarten je Satz
> (Modell liefert Stichworte + Suchbegriffe, Clipwahl so streng wie in den Folgen), Markenfläche statt unscharfer
> Vergrösserung über/unter dem Band. Stimme: Profil I «Thorsten ruhig» (exaggeration 0.3, temperature 0.7, Tempo 1.05).
> Uhr, Logo, Ton-Master und Abnahme bleiben wie unten beschrieben; alles zum Sprecher/Moderator gilt nur noch mit
> `NEWS_MODERATOR=1` (Rückweg).

Neues Format neben dem Latara-Format. Umsetzung: `tools/weltlage_maskenformat.py`, Schalter `NEWS_MASKENFORMAT=1`
(`config/settings.py`, Standard 0 = altes Latara-Format unverändert). Marlons Vorgaben vom 27.10.2026 sind hier 1:1 umgesetzt.

## 1. Bild
- **Sprecher gross**: der maskierte Moderator füllt das Bild (Marlons Bild «Masked Cyber-Noir Podcaster», `config/brand/maskenmoderator/host.png`).
  Bewegung = animierter 5-s-Loop, **kein Lipsync** (Maske ohne Mund). Loop-Quelle in dieser Reihenfolge:
  `config/brand/maskenmoderator/loop.mp4` (Task ea56, Wan-I2V) → sonst CPU-Loop aus dem Standbild (Kopf/Kapuze nicken und rollen
  dezent, Oberkörper atmet, rotes Licht links und Fensterlicht pulsieren; alle Bewegungen mit ganzen Perioden → Anfang = Ende).
  Die Maske bewegt sich nur starr mit dem Kopf, keine Verformung.
- **Uhr** (oben mittig, ca. 330×118 px = 17 % der Breite, Cyber-Noir: dunkles Glas, Cyan-Rahmen mit Eckklammern, Cyan-Glow,
  rote Live-Marke, Consolas): «LIVE-STAND · MO 26.10.2026 · 10:00 MEZ». Start = Slot-Zeit der Folge, läuft mit der Folgenzeit
  weiter (Wechsel an der Minutengrenze). Immer sichtbar, auch bei Vollbild-B-Roll. Logo oben rechts.
- Alles andere kommt aus dem Cyber-Noir-Farbraum: Cyan `#00E5FF`, Alarm-Rot `#FF2A3D`, Dunkelgrau `#060A10`.

## 2. Layouts (je Szenenwechsel eines)
| Layout | Bild | Dauer |
|---|---|---|
| `sprecher` | Moderator allein, wechselnde Kamera (weit/push/links/rechts/nah) | 5–10 s |
| `pip` | Moderator + B-Roll-Clip im Cyan-Rahmen links oder rechts, weich ein-/ausgeblendet | 6–12 s |
| `voll` | B-Roll vollflächig (langsamer Zoom), Bauchbinde «SYMBOLBILD · Urheber · Quelle · Lizenz» | 3,5–6 s |
| `quelle` | Schlagzeilen-Screenshot gross (Moderator abgedunkelt dahinter), Bauchbinde «QUELLE · Sender Domain» + Schlagzeile | 4–7 s |
| `split` | links Moderator-Ausschnitt, rechts B-Roll, Cyan-Trennlinie | 5–9 s |

## 3. Material (nur Freigegebenes)
- B-Roll: ausschliesslich Clips aus `<folge>/broll/` **mit Eintrag in `broll_lizenzen.json`** (Pexels/Pixabay/Commons/NASA/DVIDS nach
  `weltlage_broll.py`; nie Sender, Agenturen, Social Media, YouTube). Attribution → `<out>.attribution.txt` und weiterhin
  `broll_attribution.txt` der Folge (Videobeschreibung). Clip ohne Lizenzeintrag wird nie eingesetzt.
- Quellenbilder: Schlagzeilen-Screenshots aus `bilder.json` (`bilder_holen`); sie erscheinen als Zitat mit Quellenangabe.
- Jeder Clip und jedes Bild höchstens **einmal pro Folge**. Clips der gerade besprochenen Meldung haben Vorrang (Szene = `meldung`).

## 4. Szenenwechsel-Regeln (Gegen «reused/repetitious content»)
1. Schnitt nur an Satzpausen (`silencedetect` ≥ 0,28 s, Pausenmitte) oder Szenengrenzen; Dauern nach Tabelle in 2.
2. Start und letzte 14 s immer `sprecher`; sonst nie dasselbe Layout zweimal hintereinander; `voll` nie dreimal in Serie.
3. Sprecher-allein-Abschnitte werden nach einem Sprecher-Abschnitt stark abgewertet (Gewicht ×0,3): Ziel Fremdanteil
   (alles ausser `sprecher`) **≥ 45 %** der Laufzeit, gemessen im Plan (`fremdanteil` in `plan.json`).
4. Kamera des Moderators wechselt bei jedem Segment, nie zweimal dieselbe hintereinander; PiP-Seite zufällig.
5. **Pro Folge eigene Abfolge**: Zufalls-Seed = SHA1 aus Ordnername (Datum+Slot) → Layoutreihenfolge, Längen, Clip-/Bildwahl und
   Kameras unterscheiden sich in jeder Folge; `--seed` für Neuwürfeln. Der Plan jeder Folge steht in `_maskenformat/plan.json`.
6. Inhalt ist pro Folge neu: Stimme, Skript, Quellenbilder und B-Roll stammen aus der jeweiligen Meldungslage; nur der Moderator und
   das Cyber-Noir-Design sind der feste Rahmen (wie ein Studio).
7. Mindestlänge/Abnahme wie Latara-Format (`weltlage_abnahme.py`, ≥ 8 min).

## 5. Ton
`audio/*.wav` in Reihenfolge Cold Open → Themen → Meldungen (s5_*) → Outro, unverändert zusammengesetzt, Lautheit −16 LUFS / −1,5 dBTP.

## 6. Einbau / Schalter
- `tools/weltlage_tageslauf.py`: bei `NEWS_MASKENFORMAT=1` ersetzt der Maskenformat-Aufruf Rohschnitt und Lipsync im Schritt `schnitt`;
  der Schritt `broll` entfällt (B-Roll ist im Format). Latara-Pfad bleibt Code-unverändert; Abschalten = Schalter auf 0.
- Nur CPU (ffmpeg libx264); Sprecher-Loop braucht höchstens einmalig die GPU (Task ea56, über `gpu_queue.py`).
- Offen bis Marlons Abnahme: Schalter bleibt aus, Weltlage-Produktion bleibt pausiert, nichts wird hochgeladen.
