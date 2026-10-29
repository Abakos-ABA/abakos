# YouTube Data API für Weltlage-Shorts-Thumbnails (klickfrei)

Stand 21.10.2026 (Task 20261021-105909-286b). Seit dem Edge-Update 155.0.4283.62 (18.10.2026) bleiben Browser-
Prozesse nach dem Schliessen minutenlang als Zombies stehen; der Studio-Weg (Playwright) ist dagegen abgesichert
(`upload/youtube_playwright._launch`: Lockfile-Wartezeit, Neustart, Watchdog), bleibt aber ein Klickpfad, den YouTube
jederzeit ändern kann. Der Data-API-Weg braucht keinen Browser: `thumbnails.set` kostet 50 Quota-Einheiten (Tageslimit
10'000), funktioniert für **schon veröffentlichte** Videos und Shorts auch mit unverifizierter App (die Einschränkung
«privat bis zur Prüfung» gilt nur für `videos.insert`, also fürs Hochladen - das bleibt bei Studio).

Sobald die Einrichtung da ist, nimmt `tools/weltlage_shorts_takt._thumbnail_setzen_versucht()` automatisch zuerst die
API (`upload.youtube_api.verfuegbar()`), Studio nur noch als Rückfall. Abschalten ohne Dateien zu löschen:
`NEWS_YOUTUBE_API_THUMBNAIL=0` in `.env`.

## Einmalige Einrichtung (rexemre, ca. 10 Minuten)

1. <https://console.cloud.google.com/> mit dem Google-Konto des Kanals «Weltlage Kompakt» anmelden, Projekt anlegen
   (z. B. «Weltlage Kompakt Newsroom»).
2. **APIs & Dienste → Bibliothek → «YouTube Data API v3» → Aktivieren.**
3. **APIs & Dienste → OAuth-Zustimmungsbildschirm:** Nutzertyp «Extern», App-Name beliebig, Support-Mail = eigene
   Adresse, Bereiche (Scopes) hinzufügen: `.../auth/youtube`, `.../auth/youtube.upload`,
   `.../auth/yt-analytics.readonly`. Unter **Zielgruppe / Testnutzer** das eigene Google-Konto eintragen.
   **Wichtig:** Veröffentlichungsstatus auf **«In Produktion»** stellen (Knopf «App veröffentlichen»). Im Status
   «Testen» läuft das Token nach 7 Tagen ab; «In Produktion» ohne Verifizierung zeigt beim Anmelden nur die Warnung
   «Google hat diese App nicht überprüft» (Erweitert → trotzdem fortfahren), das Token bleibt dann dauerhaft gültig.
4. **APIs & Dienste → Anmeldedaten → Anmeldedaten erstellen → OAuth-Client-ID → Typ «Desktop-App».** JSON
   herunterladen und als `C:\Users\rexemre\abakos\newsroom\secrets\client_secret.json` speichern (Ordner ist in
   `.gitignore`, landet nie in Git).
5. Am PC im Newsroom-Ordner:

       C:\Users\rexemre\abakos\newsroom\.venv\Scripts\python -m upload.youtube_api --einrichten

   Es öffnet sich der Browser: Konto wählen, bei der Kanal-Auswahl **«Weltlage Kompakt»** nehmen (nicht das
   persönliche Konto, nicht «Jarvis KI»), Warnung «nicht überprüft» mit «Erweitert → fortfahren» bestätigen, alle
   Berechtigungen anhaken. Der Befehl schreibt `secrets/youtube_token.json` und zeigt den autorisierten Kanal als
   JSON (`kanal.titel` muss «Weltlage Kompakt» sein, `kanal.id` = `NEWS_YOUTUBE_CHANNEL_ID` aus `.env`).
6. Prüfen:

       .venv\Scripts\python -m upload.youtube_api --status
       .venv\Scripts\python -m upload.youtube_api --thumbnail <video_id> <pfad_zum_jpg>

Ab dann setzt der stündliche Nachtrag der Weltlage-Wache (`thumbnail_nachtrag`) fehlende Thumbnails ohne Browser;
der Verlauf (`state/weltlage_shorts_verlauf.json`) und das Wache-Log zeigen `weg: "api"`.

## Wenn das Token einmal ungültig wird

`--status` meldet `fehler` (z. B. `invalid_grant`): einfach `--einrichten` wiederholen. Der Takt fällt in der
Zwischenzeit automatisch auf Studio zurück und meldet nur, wenn auch das scheitert.
