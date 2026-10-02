# Weltlage Kompakt – verbindlicher Szenenplan Langformat

Festgelegt von Marlon in der Nacht auf den 29.09.2026. Moderatorin: **Anastasia Latara**.
Dieser Plan ist die Referenz für jede Folge. Abweichungen nur nach Marlons OK.
Ergänzt [SHOW-CONCEPT.md](SHOW-CONCEPT.md) und die Regel «Szene einfrieren, nur geänderte Szenen neu rendern»
(Memory «Weltlage Szenen-Workflow»).

**Struktur-Update 30.09.2026 (Marlon):** die alte Szene 1 «Cold Open» und die alte Szene 4 «Themenüberblick»
entfallen. An ihre Stelle treten zwei neue, klar getrennte Szenen zwischen Reinlaufen und Meldungen:
**Begrüssung** (fest eingefroren, allgemein, in jeder Folge identisch, nie neu gerendert) und **Themen**
(pro Folge neu, zählt die heutigen Schlagzeilen auf). Grund: die alte Cold-Open-Szene musste pro Folge neu
mit den Tagesthemen gerendert werden, obwohl der Begrüssungsteil selbst immer gleich war – das kostete bei
jeder Folge unnötig GPU-Zeit. Details zu Bau und Pipeline unten bei den jeweiligen Szenen.

Zielformat (wie bisheriges Langformat, z.B. `data/video/wkls01.mp4`): **1920x1080, 24 fps, H.264 + AAC, Deutsch**,
Stimme = Chatterbox mit `config/brand/voice_ref.wav` (Ramona-Referenz, exaggeration 0.4 / cfg 0.4, Text vorher durch
`tts/normalize_de.py`). **Gilt wieder seit 30.09.2026 (Marlons Entscheid nach Hörprobe Nr. 2):** die Piper-Umstellung
vom 29.09. (`de_DE-ramona-low`) ist zurückgenommen; `tools/weltlage_tts.py` spricht nur noch mit diesem Chatterbox-Klon
und schreibt pro Datei einen Engine-Nachweis (`audio/<id>.tts.json`), siehe README «Stimme der Moderatorin».

**Update 30.09.2026 abends (Marlon):** der **Cold Open ist wieder die erste Szene**, vor Bumper und Intro
(«es fehlt das Cold-Dings als erste Szene»). Er wird pro Folge neu gebaut (Text `s_coldopen` in `texte.json`,
Anriss der Top-Meldungen, fehlt er, erzeugt `tools/weltlage_update_themen.py` einen aus den ersten drei Meldungen),
mit Stimme 2 vertont und wie alle Sprechszenen auf dem Freisteller gelipsynct. Begrüssung und Themen bleiben.

## Titel beim Veröffentlichen (Regel von Marlon, 01.10.2026)

Der YouTube-Titel jeder Folge ist **überspitzt und clickbaity**, oft als Frage formuliert, und zielt auf den
**stärksten Aufhänger der Folge** – passend zum gewählten Thumbnail. Erlaubt: Zuspitzung, Dramatik, Fragezeichen,
maximal ein Wort in CAPS/Emoji. **Nie erlaubt:** falsche Behauptungen oder erfundene Ereignisse – der Inhalt der
Folge muss die Frage/Aussage tragen. Beispiel-Niveau (Marlons eigene Vorgabe): «Nordkorea: Steht der Krieg kurz
bevor?» statt eines nüchternen «Spannungen an der koreanischen Grenze». Es werden immer drei Titel-Varianten
entworfen (max. ca. 70 Zeichen), die stärkste wird gesetzt, die anderen zwei bleiben im Veröffentlichungsbericht
dokumentiert. Die Weltlage-Folgen haben kein eigenes Titel-Baustein-Skript (anders als die Shorts-Pipeline mit
`upload/metadata.py`/`script/localize.py`) – Titel, Beschreibung und Tags werden beim Veröffentlichen von Hand aus
`texte.json`/`news.json` des Folgenordners gebaut und über `upload/youtube_playwright.py` gesetzt
(`set_metadata`/`set_thumbnail` für bereits veröffentlichte Videos, `run` für den Erst-Upload). Die Beschreibung
beginnt mit dem Themen-Teaser der Folge, dessen erster Satz denselben zugespitzten Aufhänger wie der Titel trägt.

## Zweimal täglich vollautomatisch: Themenwahl + Freigabe (seit 03.10.2026, Marlons dauerhafte Freigabe 02.10. 23:03)

Marlon hat am 02.10.2026 um 23:03 dauerhaft freigegeben: Weltlage Kompakt läuft vollautomatisch inklusive
Veröffentlichung auf YouTube, wenn er nicht innerhalb einer Stunde reagiert. Ersetzt den 07:00-Lauf unten (Task fa4b).

- **Slots** `NEWS_WELTLAGE_SLOTS=11:00,19:00` (Veröffentlichungszeit), je ein anderes Video.
- **Start** des Laufs = Slot − (Themenwahl 60 min + gemessene Produktionsdauer + 30 min Puffer).
  Produktionsdauer `NEWS_WELTLAGE_PRODUKTION_STUNDEN=auto`: Rohschnitt-Dauer der letzten zwei vollen Folgen
  (`*_renderzeiten.json`, Maximum) + 1 h für Skript/Bilder/Stimme/B-Roll/Abnahme. Stand 03.10.: 6,7 h (Lipsync-HD
  der Folge vom 02.10. allein 5,7 h) → Themenwahl ab ca. 02:50 bzw. 10:50, Produktion ab 03:50 bzw. 11:50.
  `tools\weltlage_tageslauf.py zeitplan` zeigt die aktuellen Zeiten.
- **Themenwahl** (`tools/weltlage_themen.py`): Rohmeldungen der letzten 48 h → drei Storylines A/B/C (Titel als
  zugespitzte Frage, ein Satz Inhalt, grüne Bildquellen aus `config/quellen_netzwerk.json`) + Empfehlung, Stil
  Vermietertagebuch. Themenpool `state/weltlage_themenpool.json` (Storylines, die Marlon zusätzlich will) wird
  bevorzugt angeboten und nach der Wahl entfernt. Rückfrage per `tools/weltlage_entscheid.py` an Telegram (Knöpfe
  A/B/C, Antwort «B, Hinweis …») und Beta-App (Mitteilung + Push; Antwort im App-Chat «Weltlage B»). 60 min ohne
  Antwort → Empfehlung. Freitext-Hinweis geht als `vorgabe.txt` ins Skript (`weltlage_skript.py --vorgabe`).
  Vorab gewählte Storyline: im Zustand `"vorgabe": {"titel", "inhalt"}` → keine Rückfrage.
- **Produktion** wie unten (Skript → Aussprache → Bilder → Stimme → Rohschnitt → B-Roll nur echte freie Clips
  `NEWS_WELTLAGE_BROLL_OHNE_KI=1` → Abnahme → Thumbnail → Metadaten). Abnahme durchgefallen = nie veröffentlichen.
- **Freigabe** zum Slot: Telegram-Fassung (Ton kopiert) als Dokument + Thumbnail + Titel an Telegram, Text an die
  Beta-App, Knöpfe «Freigeben» (sofort öffentlich), «Feedback», «Stopp» (nicht veröffentlichen). Feedback →
  `tools/weltlage_ueberarbeiten.py` ändert nur betroffene Szenen (Verabschiedung fest), Stimme spricht nur geänderte
  Szenen neu, Lipsync-Stücke kommen aus dem Cache, Abnahme läuft erneut; neues Video, Fenster von vorn
  (max. `NEWS_WELTLAGE_MAX_FEEDBACK_RUNDEN=3`). 60 min keine Reaktion → automatisch öffentlich hochladen,
  Endscreen (Task 595e), Link an Telegram + Beta-App.
- **Trockenlauf**: `lauf ... --trocken [--themenwahl-min 3] [--freigabe-min 3]` oder `NEWS_WELTLAGE_TROCKENLAUF=1`
  = alles wie echt, aber nie ein YouTube-Upload.
- **Robust**: Zustand nur in Dateien (`state/weltlage_tageslauf.json`, `state/weltlage_entscheid/`), ein
  abgestürzter Lauf startet über den Pipeline-Tick neu (höchstens 3-mal) und setzt offene Rückfragen fort statt neu
  zu fragen. Neue Läufe starten nur, solange sie bis Slot + 5 h fertig werden können. HuggingFace läuft in den
  Unterprozessen offline (`HF_HUB_OFFLINE=1`, Vorfall 02.10.: TTS hing an einer CDN-Verbindung).

## (bis 02.10.2026) Täglich zu fixer Zeit: Tageslauf (seit 01.10.2026, Marlons Ja zur Vorbild-Analyse)

Grundlage: `reports/vorbild_vermietertagebuch_20261001/Bericht_Vorbild_Vermietertagebuch_20261001.md` (nur
Struktur-Prinzipien übernommen, keine Texte/Bilder/Thumbnails). Umgesetzt in Task 20261001-152131-dffa.

- **Zeitplan** in `.env`: `NEWS_WELTLAGE_TAEGLICH=1`, `NEWS_WELTLAGE_SLOTS=07:00` (Veröffentlichungszeit; der
  Bericht empfiehlt erst eine Folge täglich, später zwei: `07:00,18:00`), `NEWS_WELTLAGE_VORLAUF_STUNDEN=4`
  (Produktion beginnt 03:00), `NEWS_WELTLAGE_UPLOAD_VISIBILITY=public`, `NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN=5`.
- **Scheduler:** keine zweite Aufgabe. Die bestehende Aufgabe `AbakosNewsroomPipeline` (`orchestrator/pipeline.py`)
  ruft jeden Tick `tools/weltlage_tageslauf.py: pruefen_und_starten()` auf (unabhängig von der Shorts-Pause) und
  startet pro Slot einen losgelösten Lauf ohne Fenster: Skript → Bilder → Stimme → Rohschnitt/Lipsync → B-Roll →
  Abnahme → Thumbnail → Metadaten → Warten bis Slot → Upload öffentlich → Telegram-Meldung. Fällt ein Pflichtschritt
  durch (Skript-Prüfung, Stimmen-/Abnahme-Prüfung), wird **nicht** veröffentlicht und Marlon bekommt eine Meldung.
- Zustand `state/weltlage_tageslauf.json`, Log `<folge>/tageslauf.log`, Upload-Protokoll `<folge>/upload.log` +
  Bildschirmfotos `<folge>/upload_shots/`. Pause: Datei `state/weltlage_tageslauf.pause` anlegen.
  Stand ansehen: `.venv\Scripts\python.exe tools\weltlage_tageslauf.py status`.
- **Upload** (`upload/youtube_playwright.upload_datei`, auch von der Shorts-`run()` benutzt): wartet, bis der
  Dateitransfer 100 Prozent hat und die Verarbeitung gestartet ist (Text im Dialog, Deutsch/Englisch, Timeout
  `NEWS_UPLOAD_TIMEOUT_MINUTEN=60`), klickt erst dann Speichern, wartet auf Studios Bestätigung («Video
  veröffentlicht» bzw. «wird nach der Verarbeitung veröffentlicht») und prüft danach von aussen per oEmbed. Vorfall
  01.10.: Browser vor 100 Prozent geschlossen → «Upload unterbrochen» (Folge «Streit im Cockpit»).
- **Eigenes Thumbnail:** wird jedes Mal versucht; solange die Telefonbestätigung des Kanals fehlt, öffnet Studio
  statt der Dateiauswahl «Du musst deine Telefonnummer bestätigen …» → als «gesperrt» im Upload-Protokoll und in der
  Telegram-Meldung. Das Bild liegt trotzdem in `<folge>/thumbnails/thumbnail.jpg`.

## Paket-Regeln Hook, Titel, Thumbnail, Ich-Form (seit 01.10.2026)

Im Prompt `config/prompts/weltlage_analyse.md` und hart geprüft in `tools/weltlage_skript.py: paket_pruefen()`:

- **Hook/Cold Open:** nennt in ein bis zwei Sätzen **alle** Themen der Folge (jede Meldung, die ein Abschnitt
  behandelt; Feld `hook_themen` mit wörtlichem Stichwort), mit Personennamen (Ziel zwei) und einer Zahl, danach
  höchstens ein kurzer Fragesatz, Schluss «Das alles gleich in Weltlage Kompakt.». 35–75 Wörter. Der Hook ist auch
  der erste Absatz der YouTube-Beschreibung.
- **Titel:** 35–70 Zeichen, Schema «Person + Handlung (+ Zahl)», zweite Meldung mit « + » erlaubt, Zuspitzung mit «?»
  oder «!», höchstens ein Wort in Grossbuchstaben, kein Emoji, nie falsch (Regel oben bleibt).
- **Thumbnail:** feste Vorlage `video/weltlage_thumbnail.py` (1280x720, eigenes Studio weichgezeichnet, Farbcode-Leiste,
  Banderole 1–2 Wörter, zwei Zeilen Schlagwörter, Latara rechts, Markenbalken). Felder `thumbnail.banderole/zeile1/
  zeile2/farbe`; Farbcode konflikt = rot, wirtschaft = grün, politik = blau, krise = orange. Assets in
  `config/brand/thumbnail/`.
- **Ich-Form:** Latara spricht als Person, 2–4 klar markierte Meinungssätze (`meinungen`, «Ich halte …», «Meine
  Einschätzung: …»), Fakten mit hörbarer Quelle, Meinung nie als Tatsache.
- **Kommentarfrage:** genau eine, konkret (Entweder-oder oder Skala mit Zahl), letzter Satz des Abschnitts
  `schluss`, mit Einladung «Kommentare»; im Schluss kein weiteres Fragezeichen. Die feste Verabschiedung (Szene 6)
  bleibt unverändert.
- Tests: `.venv\Scripts\python.exe -m unittest tests.test_weltlage_paket -v`.

## Skript der Folge (Standard seit 01.10.2026: Analyse-Konzept)

Marlon hat am 01.10.2026 das Redaktions-/Analyse-Konzept geschickt (Redakteur, Analyst und Skriptautor: eine
Storyline statt Meldungsliste, Meldungen verbinden «A + B ergeben ein grösseres Bild», Gegenargument/alternative
Erklärung, keine Falschbehauptungen, Bild-Marker). Es liegt wörtlich in `config/prompts/weltlage_analyse.md`,
ergänzt um die Kopplung an `texte.json`. Erzeugt wird das Skript mit `tools/weltlage_skript.py`:

- holt aktuelle Meldungen (RSS + Gruppierung wie der Collector, ohne Shorts-Jobs) oder nimmt `--news`/`--transkript`,
- fragt das Modell (Standard Claude-CLI im Abo, `NEWS_WELTLAGE_SKRIPT_MODELL=opus`, keine GPU; `ollama` möglich),
- prüft deterministisch (drei Titel ≤ 75 Zeichen, Thumbnail 2–5 Wörter, Hook endet mit «Das alles gleich in
  Weltlage Kompakt.», Abschnitt «verbindung» mit ≥ 2 Meldungen, Bild-Marker vorhanden, keine News-Floskeln, ß→ss),
  bei Problemen ein Neuversuch mit Rückmeldung,
- schreibt `material.txt`, `news.json`, `skript.json`, `skript.md` und `texte.entwurf.json` (Hook → `s_coldopen`,
  Abschnitte → Szene 5 mit `bild` = erste Meldung, `marker`, `kurz`; `s_themen` automatisch; `s6_outro` fest).
  Mit `--texte` direkt `texte.json`.

Umschalten: `.env` `NEWS_WELTLAGE_SKRIPT_PROMPT=analyse` (Standard) oder `klassisch` (bisheriges Meldungsformat,
`config/prompts/weltlage_klassisch.md`), pro Lauf auch `--prompt klassisch`. Bild-Marker ([BILD], [KARTE],
[NEWS-CLIP], [GRAFIK], [HEADLINE EINBLENDEN]) werden noch nicht automatisch gerendert; der Rohschnitt nutzt weiter
die Screenshots der Meldung aus `bilder.json`. Probelauf: `reports/skript_probelauf_20261001/`.

### Personen-/Dialogformat (seit 01.10.2026 nachmittags, Teil des Prompts `analyse`)

Marlons Auftrag (Diktat 01.10.): Personen in den Mittelpunkt (Präsidenten, Kanzler, Minister, Zentralbankchefs …),
Reaktionsketten «X hat A gesagt, Y hat mit B reagiert, jetzt passiert C», echte Zitate mit Quelle und Datum,
Handlungen (Reisen, Gipfel, Telefonate, Unterschriften, Entlassungen …), dazwischen markierte Einordnung (Rolle
`einordnung`: wer hat welches Interesse, was kommt als Nächstes). Länderneutral, kein Pflichtbezug zu einem Land.

- **Originalkanäle:** `tools/weltlage_zitate.py` liest `config/aussagen_quellen.yaml` (alles ohne Login):
  Truth Social @realDonaldTrump (offizielle API per `curl.exe`, weil Cloudflare `httpx` sperrt; Ausweich-Archiv
  trumpstruth.org), Telegram-Vorschau `t.me/s/<kanal>` (Selenskyj, Medwedew, Aussenministerien RU/UA), Bluesky
  (EZB, EU-Kommission), Pressestellen-RSS (Kreml, Weisses Haus, US-Aussenministerium, Fed, EZB, Bundesregierung,
  10 Downing Street, UN News). Daraus wird der Material-Block «AUSSAGEN DER AKTEURE» (A1, A2, …) mit Person,
  Kanal, Datum UTC, Link und Originaltext; Liste auch als `aussagen.json` im Folgenordner. Ein toter Kanal hält
  die Folge nie auf (steht dann im Abschnitt «Aussagen-Kanäle» von `skript.md`).
- **X/Twitter:** ohne Login nicht erreichbar (Nitter/xcancel tot oder 451, syndication 429, rsshub 404). X-Posts
  kommen nur über Zitate in den Artikeltexten ins Skript. Folgeschritt wäre ein offizieller X-API-Zugang.
- **Artikeltexte:** Volltext-Auszug jetzt 4000 statt 2500 Zeichen und mit Link + Datum, damit Zitate aus Reden,
  Pressekonferenzen und Interviews mit genau diesem Artikel belegt werden können.
- **Zitat-Prüfung** (`zitate_pruefen` in `tools/weltlage_skript.py`, harte Fehler → Neuversuch): jedes `original`
  steht wörtlich im Block der angegebenen Quelle (sonst Quelle automatisch korrigiert oder Fehler «nicht im
  Material»), `url` steht im Material, `deutsch` steht wörtlich zwischen «» im Sprechtext, Übersetzungen tragen
  `uebersetzt: true` und «übersetzt» kurz vor dem Zitat, kein «»-Zitat (ab 4 Wörtern) ohne geprüften Beleg,
  mindestens 3 geprüfte Zitate, sobald Aussagen im Material sind. `skript.md` listet alle Zitate mit Original,
  Übersetzungs-Kennzeichnung, Link und Prüfergebnis; `texte.entwurf.json` enthält `zitate` und `handlungen`.
- Abschalten pro Lauf: `--ohne-aussagen`; das alte Meldungsformat bleibt `--prompt klassisch` bzw.
  `NEWS_WELTLAGE_SKRIPT_PROMPT=klassisch` (ohne Aussagen-Block und ohne Zitat-Pflicht).
- Tests (offline): `.venv\Scripts\python.exe -m unittest tests.test_weltlage_zitate -v`.

### Länge und Abnahme (01.10.2026, Task 20261001-144937-2805)

- **Ziellänge:** `--laenge folge` (Standard, `.env` `NEWS_WELTLAGE_SKRIPT_LAENGE`) = 380 bis 520 Wörter ohne Hook,
  höchstens 5 Abschnitte, fertige Folge rund 4 bis 5 Minuten (Kerstin Tempo 1.15 ≈ 145 Wörter/min). Gekürzt wird
  über weniger Nebenstränge, nie über Zitate (weiter mindestens 4). Mehr als 15 % daneben = harter Fehler mit
  Neuversuch. `--laenge lang` = bisherige 700 bis 1300 Wörter. Platzhalter `{{LAENGE}}` im Prompt.
- **Marken-Pegel:** `marke_angleichen` in `tools/weltlage_rohschnitt.py` senkt Bumper (gegen die Cold-Open-Stimme),
  Intro und Outro-Grafik (gegen die mittlere Meldungs-Stimme) mit einer festen Verstärkung auf höchstens
  Sprache +1,5 dB. Folge 30.09.: Musik ~9 dB über der Stimme, Master nur -15,2 statt -14 LUFS.
- **Abnahme vor dem Versand:** `tools/weltlage_abnahme.py <folgenordner> <master.mp4>` prüft Stimme (aktives Profil +
  Tempo je Sprechszene), Lautheit -14 ±1 LUFS, Szenen-Pegel und Sprünge zwischen benachbarten Szenen (≤ 4 dB),
  Ton AAC 48 kHz Stereo ≥ 230 kbps, Zitate (geprüft + wortgleich im Sprechtext); schreibt `<master>_abnahme.json`
  und `<master>_begleittext.txt` (Themen + Zitate mit Quellenliste). Exit 1 = nicht verschicken.
- Schnittbilder: `bilder_holen.py` im Folgenordner (Kopie aus der Vorfolge, nur benutzte Meldungen); Screenshots
  ansehen, Cookie-/Fusszeilen-Bilder per `bildwahl.json` ausschliessen.

## Reihenfolge (Stand 30.09.2026 abends)

| # | Szene | Bild | Ton | Status |
|---|-------|------|-----|--------|
| 1 | Cold Open | Latara **stehend am Pult** (v6-Freisteller, Lipsync) | Anriss der Top-Meldungen, endet mit «Das alles gleich in Weltlage Kompakt.» | **pro Folge neu** (30.09. abends wieder eingebaut), 0,3 s Überblendung in den Bumper |
| 1b | Welt-Bumper | Montage A2 (Weltbilder, digitale Übergänge), 4,8 s | eigener Sting | **fest eingebaut** (Marlon 29.09.) |
| 2 | Intro | bestehender Intro-Sting | Intro-Musik | vorhanden |
| 3 | Reinlaufen/Auftritt | Latara **läuft ins Bild**; ihr letzter Frame = erster Frame der stehenden v6-Pose | kein Text, nur leiser Raumton | **fest eingebaut** (29.09.), unverändert (Marlon 30.09.: «ist gut so») |
| Begr. | Begrüssung | **stehend am Pult**, gleicher Hintergrund/Platzierung wie v6 | «Willkommen bei Weltlage Kompakt, ich bin Latara. Heute kommen die folgenden Themen.» – zeitlos, kein Datum, keine Themen | **fest eingefroren** (30.09.2026, `config/brand/begruessung/`), in jeder Folge identisch, nie neu gerendert |
| Wisch | Logo-Wisch | WK-Logo + diagonaler Lichtwisch auf dunklem Studioblau, Stil von Bumper/Intro | kurzer Ton-Swoosh (aus dem aktiven Bumper) | **fest eingefroren** (30.09.2026, `config/brand/uebergang/`), ersetzt den harten Schnitt Begrüssung→Themen, in jeder Folge identisch |
| Themen | Themen | **stehend am Pult**, Fortsetzung des gleichen v6-Materials | Aufzählung der heutigen Schlagzeilen, automatisch aus den Meldungen gebaut | **pro Folge neu**, Lipsync automatisch |
| 5 | Meldungen | Latara **sitzend**, bleibt bis zum Ende sitzend | liest die Meldungen vor | Bild vorhanden, Lipsync automatisch |
| 6 | Verabschiedung | Latara **stehend am Pult**, gleicher Freisteller/Hintergrund wie Begrüssung/Themen | Abschied vom Publikum + Abo-Hinweis | **fest eingefroren seit 02.10.2026** (`config/brand/verabschiedung/`, noch nicht gebaut), Rückfall auf Pro-Folge-Render, danach Outro-Grafik |

Die alte Szene 4 «Themenüberblick» entfällt seit 30.09.2026, siehe Struktur-Update oben; ihre Funktion übernehmen
Begrüssung und Themen. Der Cold Open ist seit dem 30.09. abends wieder da (siehe oben).

## Szene «Cold Open» (wieder aktiv seit 30.09.2026 abends)

`tools/weltlage_rohschnitt.py`: Text `s_coldopen` -> Chatterbox (`tools/weltlage_tts.py`) -> Freisteller-Lipsync
stehend ab dem spätesten v6-Ruhepunkt, der noch Platz hat -> 0,3 s Bild-/Ton-Überblendung in den Welt-Bumper.
Die Stimmen-Endprüfung (`tools/weltlage_stimmpruefung.py`) prüft den Cold Open wie jede andere Sprechszene.

Früherer Stand (30.09. mittags, zurückgenommen):

Ersetzt durch die Szenen Begrüssung und Themen (siehe unten). Das darunterliegende v6-Material und die
Platzierung (`config/brand/szene1_stehend_animation/`, `host_placement_v6_neuer_hintergrund.json`) werden
weiterhin verwendet, jetzt aber von Begrüssung/Themen/Verabschiedung geteilt statt von einer eigenen Cold-Open-Szene.

## Szene Begrüssung (fest eingefroren, stehend)

- Struktur vom 30.09.2026 (Marlon): Latara begrüsst das Publikum ganz allgemein, **ohne Datum und ohne die
  heutigen Themen**, damit der Clip zeitlos bleibt und in jeder Folge unverändert wiederverwendet werden kann
  (gleiches Prinzip wie Szene 3 «Auftritt»).
- Text (fest, siehe `tools/weltlage_begruessung.py`): «Willkommen bei Weltlage Kompakt, ich bin Latara. Heute
  kommen die folgenden Themen.»
- Bild: gleicher Hintergrund/Platzierung wie das v6-Material, startet bei V6-Position 0 – schliesst nahtlos an
  den letzten Frame von Szene 3 «Reinlaufen» an (dessen letzter Frame = V6 Frame 0 = erster Frame Begrüssung).
- Ton: Chatterbox-Klon Ramona (wie `tools/weltlage_tts.py`, seit 30.09.2026; v1 war Piper), danach
  Freisteller-Lipsync nach der festen Lipsync-Regel (siehe unten) und Studio-Composite.
- Neu gebaut am 30.09.2026 mit der Chatterbox-Stimme: `config/brand/begruessung/begruessung_v2.mp4` (aktiv);
  `begruessung_v1.mp4` (Piper) bleibt als Backup.
- Gebaut und eingefroren am 30.09.2026 (Task 20260930-010440-2467): `config/brand/begruessung/begruessung_v1.mp4`
  (aktiv laut `config/brand/begruessung/aktiv.json`), 5,9 s, 1920x1080, 24 fps, H.264 + AAC.
- Werkzeug: `tools/weltlage_begruessung.py` (`build` → `_work/begruessung/begruessung_v1.mp4`, `freeze` → kopiert
  nach `config/brand/begruessung/` und schreibt `aktiv.json`). **Einmalig, nie neu rendern**, ausser Marlon ändert
  Text oder Platzierung – dann Neubau wie bei Szene 3.
- Eingehängt in `tools/weltlage_rohschnitt.py` (Abschnitt «Begruessung»): läuft direkt nach Szene 3, vor der
  Themen-Szene.

## Szene Logo-Wisch (fest eingefroren, zwischen Begrüssung und Themen)

- Entscheid Marlon, 30.09.2026: zwischen Begrüssung und Themen ersetzt ein kurzer Logo-Wisch (Variante A)
  den bisherigen harten Schnitt bei Sekunde 11 des Kurztests. Eine bildgenaue Standbild-Vorlage
  (Variante B, Übergang über den identischen letzten/ersten V6-Frame) wurde verworfen – nicht nötig.
- Eigenständige, immer gleiche Vorlage wie Bumper/Intro, unabhängig vom Folgeninhalt: WK-Logo
  (`config/brand/logo.png`) mit diagonalem Lichtwisch auf dunklem Studioblau, im Stil des bestehenden
  Logo-Sweeps (`tools/render_logo_probe.py`, Variante A) und der Bumper-/Intro-Farben. Kurzer Ton-Swoosh
  aus dem Ton des aktiven Bumpers (`config/brand/bumper/aktiv.json`), da auch Bumper und Intro Ton haben.
- Gebaut und eingefroren am 30.09.2026: `config/brand/uebergang/uebergang_v1.mp4` (aktiv laut
  `config/brand/uebergang/aktiv.json`), ca. 1,0 s, 1920x1080, 24 fps, H.264 + AAC.
- Werkzeug: `tools/weltlage_uebergang.py` (`build` → `_work/uebergang/uebergang_v1.mp4`, `freeze` → kopiert
  nach `config/brand/uebergang/` und schreibt `aktiv.json`). Rein CPU (PIL/numpy + ffmpeg), kein GPU nötig.
  Einmalig, nie neu rendern, ausser Marlon ändert den Look.
- Eingehängt in `tools/weltlage_rohschnitt.py` (Abschnitt «Logo-Wisch»): läuft direkt nach der Begrüssung,
  vor der Themen-Szene – auch im `--kurztest`.
- **Ton seit v2 (Marlon 30.09.2026):** der Bumper-Hit (auf -14 LUFS, so laut wie die Sprache) war zu aggressiv.
  Jetzt `config/brand/uebergang/uebergang_v2.mp4`: synthetischer weicher Whoosh (`synth_whoosh`, gefiltertes
  Rauschen, Filter wandert mit dem Lichtwisch, Stereo links→rechts), Spitze -17 dBFS, im Schnitt ~13 dB unter der
  Sprache, kein loudnorm. Varianten `A` (luftig, Standard) / `B` (dunkler + leiser Schimmer):
  `tools/weltlage_uebergang.py build A|B`, `freeze A|B`. `uebergang_v1.mp4` bleibt als Backup liegen.

## Szene Themen (pro Folge neu, stehend)

- Struktur vom 30.09.2026 (Marlon): Latara nennt die heutigen Themen als kurze Aufzählung (Schlagzeilen der
  Meldungen), «Jetzt im Einzelnen» am Ende. Ersetzt die alte Szene 4 «Themenüberblick».
- **Keine eigene Ansage** (Marlon 30.09.2026): die Begrüssung endet schon mit «Heute kommen die folgenden
  Themen.», darum beginnt der Themen-Text direkt mit der ersten Schlagzeile (früher «Das kommt heute: …» = doppelt).
- Text wird **automatisch** aus den `"kurz"`-Feldern der Meldungen in `texte.json` gebaut:
  `tools/weltlage_text_gen.py` (`build_themen_text`) formuliert den Aufzählungssatz,
  `tools/weltlage_update_themen.py <folgenordner>` schreibt/aktualisiert den Eintrag `s_themen` in `texte.json`
  einer Folge – vor `tools/weltlage_tts.py` laufen lassen, damit die Themen-Szene die aktuellen Schlagzeilen
  vorliest.
- Bild: gleicher Hintergrund/Platzierung wie Begrüssung, Fortsetzung des v6-Materials; startet an einem
  **v6-Ruhepunkt** (`V6_RUHEPUNKTE` in `tools/weltlage_rohschnitt.py`), damit sich die Bewegung nicht mit der
  Begrüssung wiederholt.
- Ca. 12–20 s, je nach Anzahl Meldungen.
- **Abo-Hinweis** (festgelegt von Marlon, 29.09.2026, jetzt Teil dieser Szene statt der alten Szene 4): ein
  Halbsatz «Wenn du dranbleiben willst, abonnieren», dazu kurz eingeblendetes Abo-Symbol
  (`config/brand/endscreen/abo_hinweis_icon.mov`, Alpha, ProRes 4444, ~2,5 s, pulsierender Button unten rechts),
  per Alpha-Overlay eingeblendet (`abo_overlay` in `tools/weltlage_rohschnitt.py`). Kein Like/Abo-Aufruf mitten
  in den Meldungen (Szene 5) – nur hier und im Outro.
- Wird **pro Folge neu gerendert** (Lipsync auf dem Freisteller, wie alle Sprechszenen).

## Szene 1b – Welt-Bumper (zwischen Cold Open und Intro)

- Entscheid Marlon 29.09.2026: **Bumper A2** (A1 verworfen, liegt unter `output/bumper_outro/_verworfen/`).
- Aktiv laut `config/brand/bumper/aktiv.json` → `config/brand/bumper/bumper_A2.mp4` (Kopie von
  `output/bumper_outro/bumper_A2.mp4`, Ton auf -14 LUFS / -2 dBTP an das Intro angeglichen). Wechseln = Dateiname
  in der json ändern, `null` = kein Bumper.
- **Ton-Update 02.10.2026** (Marlon fand den Ton seit 30.09. immer noch schlecht): vier neue, druckvollere
  ACE-Step-Varianten erzeugt (`_work/bumper_opener_20261002/`, Prompt-Familien `brass_impact`/`hybrid_drive`/
  `minimal_power`/`digital_crisp`, je Familie das beste 4,7917-s-Fenster wie zuvor bei `bumper_sanft`). Automatisch
  nach Punch/Transient-Position bester Kandidat war Kandidat 1 (`hybrid_drive`), zunaechst als Zwischenstand
  eingebaut. **Marlon hat die vier Varianten angehoert und Kandidat 3 (`brass_impact`, Seed 701, klassische
  Blechblaeser-Fanfare mit Impact-Hit) gewaehlt** – das ist seit 02.10.2026 20:19 der Standard, auf
  Produktionsstandard (-14 LUFS / -2 dBTP) gemastert und in `bumper_A2_lizenzfrei.mp4` eingebaut
  (`_work/bumper_opener_20261002/install_standard.py`, `WAHL = "3"`). Fallback bleibt die urspruengliche ruhige
  Synth-Pad-Fassung (seit Ende September) unter
  `config/brand/bumper/bumper_A2_lizenzfrei_backup_20261002-001601.mp4`; die kurzlebige Kandidat-1-Zwischenfassung
  liegt zusaetzlich unter `..._backup_20261002-001930.mp4`. Alle vier Varianten (Bild+Ton, fertige Vorschau-Videos)
  liegen unter `_work/bumper_opener_20261002/kandidaten/kandidat_1..4.mp4`, Bewertung in `kandidaten_bericht.json`.
- Technisch eingehängt in beide Schnittwege: `tools/weltlage_rohschnitt.py` (eigenes Segment «Bumper A2» nach
  Szene 1, bildgenaue Länge) und `video/assemble.py` (`_with_bumper`: Bumper wird vor das Intro geklebt, Sting-Fenster,
  Stimmpause und Sting-Ton wachsen automatisch mit; nur Querformat).

## Szene 2 – Intro

- Bestehendes Intro-Material, aktiv laut `config/brand/intro/aktiv.json` (Stand 29.09.: `weltlage_intro_v7.mp4`, 3,6 s, 1920x1080).
- Kein Sprechtext.

## Szene 3 – Auftritt (fester Clip, in jeder Folge identisch)

- Gebaut 29.09.2026 (Task 20260929-202639-7cb6), Auftrag Marlon: einmal endgültig, **kein Text, kein Lipsync, kein Sprechton**.
- Clip: `config/brand/szene3_auftritt/szene3_auftritt_v1.mp4` (aktiv laut `config/brand/szene3_auftritt/aktiv.json`),
  5,08 s, 1920x1080, 24 fps, H.264 + AAC (nur sehr leiser Raumton, Musik gibt es nach Konzept nur in Bumper/Intro/Outro).
  Daneben: Freisteller-Lauf mit Alpha `szene3_freisteller_lauf_v1_prores4444.mov` (1344x896, 16 fps, Ausschnitt x 0–1344,
  y 100–996 des 1920er-Bilds) und das Zielbild `szene3_letzter_frame_ziel.png`.
- Inhalt: leeres Studio, Latara läuft von links (Profil, parallel zur Rückwand) auf ihre Marke, dreht sich zur Kamera und
  steht in der Pose des Cold Open. Die letzten 5 Bilder gehen weich in das exakte Zielbild über, **letztes Bild = v6-Freisteller
  Frame 0, mit `fl.studio_filter` in 1920x1080 ins Studio gesetzt** (genau der Weg des Cold Open).
- Werkzeug: `tools/szene3_auftritt.py` (prep → render → matte → compose → freeze). Wan 2.2 I2V-A14B First-Last-Frame
  (Start = leeres Studio, Ende = Zielbild), Hochrausch-Stufe ohne lightx2v mit CFG 3,5 (6 von 12 Schritten), Tiefrausch mit
  lightx2v; Seed 7311. Reine 4-Schritt-Läufe (Seeds 7301/7302, `_work/szene3_auftritt/_v1_4schritt/`) zeigten eine doppelte,
  überlagerte Latara und wurden verworfen. Freistellen BiRefNet, begrenzt auf die Differenz zum leeren Studio; Schlagschatten
  wie `fl.studio_filter`.
- Ändert sich die Platzierung des Cold Open (`host_placement_v6_neuer_hintergrund.json`), muss Szene 3 neu gebaut werden
  (`prep`, `render`, `matte`, `compose`, `freeze`), sonst stimmt der letzte Frame nicht mehr.
- Schnitt: `tools/weltlage_rohschnitt.py` nimmt den Clip bildgenau als Szene 3 (Ton aus dem Clip). Szene 4 beginnt seither
  an einem **v6-Ruhepunkt** (`V6_RUHEPUNKTE`, Segmentgrenzen, an denen v6 praktisch Frame 0 zeigt), damit der Übergang 3→4
  ebenfalls nahtlos ist. Der Satz aus `texte.json` (`s3_auftritt`) wird nicht mehr verwendet.

## Szene 5 – Meldungen (sitzend, bis zum Ende)

- Latara **sitzend** am Pult (bestehendes Sitz-Material: `config/brand/studio_bg/composite_host_v4_full.mp4`,
  eingefrorenes Muster `config/brand/host_v3_frozen.json`, sitzt bis zum Ende der Folge).
- Sie liest die Meldungen; Rhythmus pro Meldung:
  1. Latara spricht in die Kamera (ca. 3–5 s, immer beim Beginn einer Meldung),
  2. Schnitt auf **Bild/Screenshot zur Meldung** (Artikel-Screenshot, zitierter Tweet/Post, offizielles Dokument –
     `video/sources.py`: Artikel/X/YouTube/PDF), Stimme läuft weiter,
  3. nach einigen Sekunden zurück auf Latara – alle paar Sekunden wieder sichtbar sprechend.
- Schnittbilder: ruhiger Ken-Burns-Zoom, Quellen-Kennzeichnung (Medium/Domain) sichtbar, keine KI-Illustrationen.

## Szene 6 – Verabschiedung + Outro

- **Fest eingefroren seit 02.10.2026** (Task 20261002-163146-afaf): der Abschiedstext ist in jeder Folge wortgleich
  (`tools/weltlage_skript.py` `OUTRO["text"]`, als `"s6_outro fest"` unveraendert in jede `texte.json` geschrieben) –
  genau wie die Begrüssung wird die Szene darum nur noch einmal vertont und gelipsynct statt bei jeder Folge erneut
  (das kostete vorher pro Folge rund zwei LatentSync-Stücke à ~7 Minuten GPU-Zeit für ein praktisch identisches
  Ergebnis). Werkzeug `tools/weltlage_verabschiedung.py` (`build` → `_work/verabschiedung/verabschiedung_v1.mp4`,
  `freeze` → kopiert nach `config/brand/verabschiedung/` und schreibt `aktiv.json` samt `guidance`/`hd`-Feld).
  Eingehängt in `tools/weltlage_rohschnitt.py` (Abschnitt „Verabschiedung“): solange `verabschiedung/aktiv.json`
  fehlt oder die Folge einen eigenen Ort für `s6_outro` setzt, läuft automatisch der alte Pro-Folge-Weg weiter.
  **Noch nicht gebaut** (Stand 02.10.2026 nachmittags) – der erste Bau braucht GPU-Zeit (TTS + ~2 LatentSync-Stücke)
  und sollte erst laufen, wenn kein Folgen-Render die Karte braucht.
- Frühere Fassung (**fest eingebaut**, 29.09.2026, Marlon, vor der Einfrierung): Verabschiedung lief nach derselben
  Freisteller-Regel wie Cold Open/Szene 4 – **stehende** Latara, gleicher Idle-Master
  `config/brand/szene1_stehend_animation/stehend_v6_alpha_prores4444.mov`, gleiches Studiobild/Placement wie
  Szene 1/4. Umgesetzt in `tools/weltlage_rohschnitt.py` (`host_scene("stehend", s6, ...)`, Ausschnitt aus der
  Taktmitte des Idle-Masters, damit sich die Bewegung nicht mit Szene 1/4 wiederholt) – das ist weiterhin der
  Rückfall-Pfad, solange die eingefrorene Fassung fehlt.
- **Lipsync-Staerke/HD-Pruefung** (ebenfalls Task 20261002-163146-afaf): `tools/weltlage_abnahme.py` vergleicht
  bei Begrüssung UND Verabschiedung das `guidance`/`hd`-Feld der jeweiligen `aktiv.json` gegen
  `config.settings.NEWS_WELTLAGE_LIPSYNC_GUIDANCE`/`_HD` und bricht bei Abweichung ab (z.B. eine mit Stärke 1,5
  eingefrorene Fassung in einer 2,0-Folge). Fassungen von vor dem 02.10.2026 ohne dieses Feld (z.B.
  `begruessung_v3.mp4`) geben nur eine Warnung, keinen Abbruch – ihre tatsächliche Baustärke ist nicht dokumentiert.
- **Aktiv seit 29.09.2026 (Task 20260929-165649-e0b8): `output/outro_v3/outro_B_weltnetz_lizenzfrei.mp4`** –
  Bild von Outro v3 B «Weltnetz» unverändert, Musik neu mit **ACE-Step 1.5** (MIT, kommerziell erlaubt; Lizenz
  `output/outro_v3/LIZENZ_musik_B_lizenzfrei_ACE-Step.txt`), 12 Seeds erzeugt, Sieger per Messung `ace_s103`
  (auf 123,7 bpm / Raster von musik_B gelegt, -14 LUFS, TP -1,9 dBFS). Kandidaten: `output/outro_v3/lizenzfrei_kandidaten/`,
  Skript `_work/outro_lizenzfrei/musik_finish_ace.py`. Backup (MusicGen, CC-BY-NC, nicht monetarisierbar):
  `output/outro_v3/outro_B_weltnetz.mp4`. Eingetragen in `tools/weltlage_rohschnitt.py` (`OUTRO`).
  **Noch MusicGen:** `outro_final.mp4` (Backup) und vermutlich das Endscreen-Musikbett (aus Task c4a6) – vor Monetarisierung prüfen/ersetzen.
- **Outro-Grafik fertig** (29.09.2026, Task 20260929-030414-c4a6): `output/bumper_outro/outro_final.mp4`, 8 s, Look B2
  (Erde im All, End-Card ab 1,4 s), neue Musik (MusicGen, 6 Kandidaten analysiert, Sieger «bright_s11», -14 LUFS,
  Ausklang auf dem Tonika-Akkord). Render: `tools/render_bumper_outro.py outro --audio <wav>`.
  Danach folgt nahtlos der Endscreen (siehe unten).
- **Abo-Hinweis** (festgelegt von Marlon, 29.09.2026): im Outro-Text auf das nächste Video hinweisen
  («… morgen wieder hier» o.ä.) + Abo-Aufruf. Siehe Abschnitt „Call-to-Action & Endscreen" unten für den
  technischen Teil (Endscreen-Führung, Positionen).
- Welt-Bumper/Outro-Bildmaterial (Montage-Stil) entsteht in Task 20260929-021843-3ee7,
  `output/bumper_outro/` (`bumper_A1/A2.mp4`, `outro_B1/B2.mp4` + Bausteine unter `work/`) – dieser
  Abschnitt beschreibt nur den Abo-Hinweis/Endscreen-Teil, nicht das Bildmaterial selbst.

## Call-to-Action & Endscreen

Ergänzt von Marlon, 29.09.2026 – technischer Teil umgesetzt in Task 20260929-022135-5814, Details in
[endscreen.md](endscreen.md).

- **Zwei Abo-Stellen, sonst keine:**
  1. Szene 4 (Themenüberblick, stehend) – Halbsatz + kurzes Icon, siehe dort.
  2. Outro – Hinweis auf das nächste Video + Abo-Aufruf, siehe Szene 6.
  Keine Like/Abo-Aufrufe mitten in den Meldungen (Szene 5).
- **Endscreen (letzte 20 s des Videos):** der Outro-Hintergrund läuft weiter; YouTube legt die klickbaren
  Endscreen-Elemente (2 empfohlene Videos + Abo-Button, Standardpositionen der Vorlage) selbst als Overlay
  darüber – das bleibt pro Video ein manueller Klick im Studio, die YouTube Data API hat dafür keinen
  Endpunkt (geprüft, siehe endscreen.md).
- Endscreen-Design «edel» (29.09.2026, ersetzt die pulsierenden Goldrahmen, die Marlon nicht gefielen):
  ruhige Kamerafahrt auf dem Outro-Globus, Wortmarke oben links, zwei dunkle Glasflächen mit feiner Gold-Haarlinie
  und Label («NÄCHSTES VIDEO», «AUCH SEHENSWERT») genau auf den Studio-Positionen, Abo-Kreis unten links mit
  «ABONNIEREN». Startet exakt auf dem letzten Outro-Frame. Werkzeug `tools/endscreen_design.py`, Layout aus
  `config/brand/endscreen/positions.json`, eigenes Musikbett (-14 LUFS, Ausklang bis 20,0 s).
- Vorschau (echter Outro-Hintergrund): `output/bumper_outro/endscreen_vorschau.mp4`, alte Goldrahmen-Version unter
  `output/bumper_outro/_verworfen/`.
- Anleitung fürs Platzieren im Studio + alle Details/offenen Punkte: [endscreen.md](endscreen.md).

## Feste Regel Lipsync: immer auf dem Freisteller (Marlon, 29.09.2026)

Gilt für **alle** Weltlage-Videos, stehend **und** sitzend:

1. Lipsync (LatentSync 1.6) läuft **immer auf dem Freisteller-Quellvideo** der Moderatorin: ohne Studio-Hintergrund,
   volle Quellauflösung, Gesicht gross (stehend `config/brand/szene1_stehend_animation/stehend_v6_alpha_prores4444.mov`,
   832x1248; sitzend grüner Ping-Pong-Master aus v3+v4-Tail, 896x1152). **Nie** auf dem fertig komponierten Studiobild (dort ist das
   Gesicht 40–60 px gross und der Mund kaum sichtbar).
2. Matte/Alpha bleibt die des Freistellers (stehend BiRefNet-Alpha, sitzend Differenz-Key `tools/key_host.py`); ersetzt
   wird nur die untere Gesichtshälfte innerhalb der Alpha.
3. **Erst danach** skalieren und in der abgemachten Position ins Studio setzen (`host_placement_v6_neuer_hintergrund.json`
   bzw. `studio_bg/host_placement.json`), und zwar direkt in der Endauflösung 1920x1080 – kein Composite in 1280x704
   mit anschliessendem Hochskalieren.

Umsetzung: `video/freisteller_lipsync.py` (`render_scene(pose, ton, start, länge, ordner, name)`, Posen `stehend`/`sitz`),
fest eingebaut in `tools/weltlage_rohschnitt.py` (Szenen 1, 4, 5 automatisch, sobald LatentSync installiert ist):

    .venv-lipsync\Scripts\python.exe tools\weltlage_rohschnitt.py <testordner> [--out datei.mp4] [--work ordner]

Einstellungen: Gesichtsfenster 2,2x Gesicht auf 768x768, 20 Schritte, guidance 2,5, Stücke ≤ 7 s an leisen Stellen.
LatentSync-Stücke werden nach Inhalt in `data/_latentsync_cache` zwischengespeichert, gemeinsam für alle Läufe: bei einer
neuen Folge wird nur neu gesynct, was sich geändert hat. Nie zwei LatentSync gleichzeitig: Sperre `state/latentsync.lock`
(PID, vom ersten Stück bis Prozessende), vor jedem Stück Warten auf freien Grafikspeicher, Zeitlimit 15 min mit bis zu
3 Versuchen. LatentSync läuft mit VAE-Slicing (`vendor/LatentSync/scripts/inference.py`, gleiches Ergebnis, ~8,5 statt
~17 GB VRAM; abschaltbar mit `LATENTSYNC_VAE_SLICING=0`). Zwischenergebnis pro Szene: `<name>_freisteller_lipsync_prores4444.mov` (mit
Alpha) und `<name>_studio.mp4`. Die Skripte `tools/weltlage_lipsync_sitz.py` und `tools/weltlage_lipsync_stehend*.py`
sind damit veraltet.

**Sitzend nie ein sichtbarer Loop-Schnitt (29.09.2026, Task 20260929-204508-b71a):** Der grüne Sitz-Rohmaster ist nur
22 s lang (`config/brand/takes_green/weltlage_host_sitz_raw22_25fps.mp4`); hart von vorne geloopt gab das alle 22 s
einen Sprung (Testvideo bei 1:33). Die Pipeline nutzt darum den daraus gebauten **Ping-Pong-Master**
`config/brand/takes_green/weltlage_host_sitz_pingpong100_25fps.mp4` (99,7 s): vor und zurück mit wechselnden
Umkehrpunkten (`SITZ_PINGPONG` in `video/freisteller_lipsync.py`), an jedem Umkehrpunkt 0,6 s sanft abgebremst und
wieder angefahren (Zwischenbilder geblendet), Ende = Anfang. Beliebig lange Meldungen loopen diesen Master nahtlos
(Loop-Sprung gemessen 0,2 statt 17). Fehlt die Datei, baut `_ensure_source` sie automatisch neu.

## Offen (laut Marlon, 29.09./30.09.2026)

1. **Lipsync für alle Sprechszenen** (Begrüssung, Themen, 5, 6): laufen seit 30.09. automatisch nach der
   Freisteller-Regel oben; Szene 3 «Reinlaufen» hat bewusst kein Sprechvideo (kein Text, kein Lipsync).
2. **Gesamtschnitt** als automatisierter Baustein der Pipeline (heute: Rohschnitt-Skript `tools/weltlage_rohschnitt.py`,
   Struktur inkl. Begrüssung/Themen seit 30.09. eingebaut).
3. ~~Szene 3 (Auftritt)~~ gebaut 29.09. (fester Clip, siehe oben), wartet auf Marlons Ja.
4. ~~Endscreen final rendern~~ erledigt 29.09. (`tools/endscreen_design.py`). Marlon: Positionen einmal live im
   Studio gegenprüfen.
5. ~~Begrüssungs-Vorlage bauen~~ erledigt 30.09.2026 (Task 20260930-010440-2467), siehe Szene Begrüssung oben.
   Marlon: Testclip unten ansehen und Begrüssungstext/Bild freigeben.
6. **Volle Folge mit der neuen Struktur** (Bumper–Intro–Reinlaufen–Begrüssung–Logo-Wisch–Themen–Meldungen–
   Verabschiedung–Outro) noch nicht komplett gerendert, nur der Kurztest der ersten fünf Teile (siehe Testläufe).
7. ~~Logo-Wisch statt hartem Schnitt Begrüssung→Themen~~ erledigt 30.09.2026 (Variante A, siehe Szene
   Logo-Wisch oben). Vorheriger Versuch mit bildgenauer Standbild-Vorlage (Variante B, Task
   20260930-105141-3694) wurde abgebrochen und verworfen. Marlon: neuen Kurztest unten ansehen und Wisch freigeben.

## Testläufe

- 29.09.2026: erster Rohschnitt nach diesem Plan, siehe `data/weltlage_test_20260929/` (README dort):
  `weltlage_rohschnitt_20260929_lipsync.mp4`, 3:25, Szene 5 mit Lipsync (`tools/weltlage_lipsync_sitz.py`),
  Szenen 1/4 ohne Lipsync, Szene 3 und Verabschiedung als Standbild-Platzhalter.
  Lehre: LatentSync nur in Stücken ≤ 7 s (33-s-Stück lief über den VRAM, Abbruch nach 30 min) und nie parallel zu MusicGen/ComfyUI.
- 30.09.2026 (Task 20260930-010440-2467): Kurztest der neuen Struktur, `data/weltlage_test_20260929/weltlage_rohschnitt_20260929_lipsync_kurztest.mp4`,
  58,6 s, 1920x1080, mit Lipsync: Reinlaufen (5,1 s) – Begrüssung (5,9 s, feste Vorlage) – Themen (17,1 s, automatisch
  aus den Schlagzeilen der Testfassung) – Anfang der Sitz-Szene (erste Meldung Fairford, 30,5 s). Kein Bumper/Intro/
  Verabschiedung/Outro (per `--kurztest` ausgelassen). Marlon muss den Clip noch ansehen und Struktur/Begrüssungstext
  freigeben.
- 30.09.2026 (Task 20260930-111810-d281): Kurztest mit dem neuen Logo-Wisch (siehe Szene Logo-Wisch oben),
  `data/weltlage_test_20260929/weltlage_rohschnitt_20260930_wisch_kurztest.mp4`, 59,5 s, 1920x1080: Reinlaufen
  (5,1 s) – Begrüssung (5,8 s) – **Logo-Wisch (1,0 s, neu)** – Themen (17,1 s) – Anfang der Sitz-Szene (30,5 s).
  Ersetzt den harten Schnitt bei Sekunde 11 des vorherigen Kurztests; der Wisch sitzt jetzt bei 00:10,88–00:11,88.
  4-Sekunden-Ausschnitt um den Übergang zur Kontrolle: `C:\Users\Marlon\projekte\jarvis\reports\weltlage_uebergang_ausschnitt_20260930.mp4`
  (Sekunde 9,0–13,0 des Kurztests). Marlon muss den Wisch ansehen und freigeben.

## Orte pro Szene (01.10.2026)

Optional kann jede Sprechszene in `texte.json` ein Feld `"ort"` tragen (z.B. `"bruessel"`); Latara steht dann vor diesem
Hintergrund statt im Studio. Ohne Feld bleibt alles wie oben. Details, Tool und offene Punkte: `docs/weltlage_orte.md`.
