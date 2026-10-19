"""Interim uploader: drives YouTube Studio's upload wizard in a dedicated, already-signed-in
browser profile (secrets/playwright_profile, Edge by default). This is the load-bearing upload
path until the Google OAuth verification AND the YouTube API compliance audit have both
cleared (see newsroom/README.md) - until then, uploads via the real API are forced private, so
this is how videos actually go public in the meantime.

One-time setup: `python -m upload.youtube_playwright --login`, sign in with the Google account
that owns the channel, switch to the channel if it is a brand channel, close the window.

Selectors were verified against a live Studio session (2026-09-21, German UI) and are
language-independent on purpose: element ids, `name=` on the radio buttons, `test-id=` on the
language list. Do NOT switch them to visible labels - Studio follows the Google account's UI
language, not the browser's. The Studio wizard can change; if a step breaks, the job fails
loudly (see below) and `python -m upload.youtube_playwright <job_id>` with
NEWS_PLAYWRIGHT_HEADLESS=false + NEWS_UPLOAD_VISIBILITY=private shows exactly where.

Targets ONE channel (NEWS_YOUTUBE_CHANNEL_ID): a Google account can own several channels, and the
active one can be switched by hand, so the channel id is put in the URL and re-checked.

Safety rule, not a suggestion: any failure AFTER the file is selected and the upload has started
halts the job for human confirmation. No automatic retry past that point - a duplicate publish
from a blind retry is a pure downside with no upside. The draft's video id is written to the job
before anything else can go wrong, so a half-finished upload can be found in Studio.

Vorfall 05./06.10.2026 (Fairford-Folge): Studio hat die Veroeffentlichung im Upload-Dialog nie
bestaetigt ("dialog zu ohne bestaetigung"), das Video blieb ein privater Entwurf und musste von
Hand oeffentlich gestellt werden. upload_datei() prueft darum den echten Status per oEmbed
(oeffentlich_pruefen) und zieht die Sichtbarkeit bei Bedarf selbst ueber Studios Bearbeiten-Seite
nach (visibility_setzen) statt nur zu melden; schlaegt auch das fehl, bleibt es bei der Meldung.

Vorfall 06.10.2026 (Bolsonaro-Folge, gleiche Ursache wie Fairford): Studio zeigt nach «Veroeffentlichen» den neuen
Zwischendialog «Die Vorabpruefung deiner Inhalte laeuft noch» (Trotzdem veroeffentlichen / Zurueck). Ohne Klick bleibt
das Video ein ENTWURF; der alte Nachzug suchte auf der Bearbeiten-Seite das Sichtbarkeits-Feld, das es bei Entwuerfen
nicht gibt («Entwurf bearbeiten»), und lief in den Timeout. Seither: vor dem Klick auf die Vorabpruefung warten
(_warte_auf_pruefung), den Zwischendialog erkennen und bestaetigen (_trotzdem_knopf), und nach jedem Upload
veroeffentlichen() - frischer Seitenaufruf, Studio-Status lesen (ENTWURF/PUBLIC/UNLISTED/PRIVATE), Entwurf ueber den
Assistenten bzw. Sichtbarkeit ueber die Bearbeiten-Seite abschliessen, erneut frisch pruefen, bis zu 3 Versuche.
Das Studio-Profil ist mit einer Sperrdatei gegen gleichzeitige Zugriffe (Upload + Weltlage-Wache) geschuetzt.
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from config.settings import (
    DATA_DIR, NEWS_PLAYWRIGHT_CHANNEL, NEWS_PLAYWRIGHT_HEADLESS, NEWS_YOUTUBE_CHANNEL_ID,
    PLAYWRIGHT_PROFILE_DIR, require,
)
from orchestrator import state_store
from upload.metadata import build as build_metadata

logger = logging.getLogger(__name__)

STEP_TIMEOUT_MS = 120_000        # 06.10.2026: 60 s reichten fuer Studios Bearbeiten-Seite nicht immer
UPLOAD_TIMEOUT_MS = 20 * 60_000   # file transfer + processing of the dialog, generous on purpose
PRUEF_WARTEN_MIN = float(os.environ.get("NEWS_UPLOAD_PRUEF_WARTEN_MIN", "20"))   # Vorabpruefung abwarten
VEROEFFENTLICHEN_VERSUCHE = int(os.environ.get("NEWS_UPLOAD_VEROEFFENTLICHEN_VERSUCHE", "3"))
SPERRE = Path(__file__).resolve().parents[1] / "state" / "playwright_profile.lock"
SPERRE_WARTEN_S = 30 * 60

# Studio folgt der Sprache des Google-Kontos (deutsch), darum immer beide Sprachen.
_VORAB_LAEUFT = re.compile(r"vorabprüfung[^.]{0,60}läuft noch|checks?[^.]{0,30}still running|still checking", re.I)
_TROTZDEM = re.compile(r"^\s*(trotzdem veröffentlichen|publish anyway)\s*$", re.I)
_PRUEFUNG_LAEUFT = re.compile(r"wird geprüft|prüfung läuft|überprüfung läuft|checking", re.I)
_ENTWURF = re.compile(r"status\s*[„\"»«]?\s*entwurf|is a draft|\bentwurf bearbeiten\b|\bedit draft\b", re.I)
_ENTWURF_KNOPF = re.compile(r"^\s*(entwurf bearbeiten|edit draft)\s*$", re.I)
_SICHT_MUSTER = (("UNLISTED", re.compile(r"nicht gelistet|\bunlisted\b", re.I)),
                 ("PRIVATE", re.compile(r"\bprivat(e)?\b", re.I)),
                 ("PUBLIC", re.compile(r"öffentlich|\bpublic\b", re.I)))
_DIALOGE = "tp-yt-paper-dialog:visible, ytcp-dialog:visible, [role=dialog]:visible, [role=alertdialog]:visible"


def zwischendialog_art(text: str) -> str | None:
    """'vorab_laeuft', wenn der Text Studios Zwischendialog «Vorabpruefung laeuft noch» ist (Vorfall 06.10.2026)."""
    return "vorab_laeuft" if _VORAB_LAEUFT.search(" ".join((text or "").split())) else None


def pruefung_laeuft(text: str) -> bool:
    """True, solange der Fortschrittstext des Upload-Dialogs die Vorabpruefung als laufend zeigt
    («Wird geprüft: 7 % ... Noch 10 Minuten»)."""
    return bool(_PRUEFUNG_LAEUFT.search(text or ""))


def sichtbarkeit_aus_text(text: str) -> str | None:
    """PUBLIC/UNLISTED/PRIVATE aus dem Sichtbarkeits-Feld der Bearbeiten-Seite; None wenn keins oder mehrdeutig."""
    t = " ".join((text or "").split())
    treffer = {name for name, rx in _SICHT_MUSTER if rx.search(t)}
    return treffer.pop() if len(treffer) == 1 else None


def studio_status_aus(seitentext: str, sicht_text: str) -> str:
    """ENTWURF | PUBLIC | UNLISTED | PRIVATE | UNBEKANNT aus Seitentext und Sichtbarkeits-Feld der Bearbeiten-Seite."""
    if _ENTWURF.search(seitentext or ""):
        return "ENTWURF"
    return sichtbarkeit_aus_text(sicht_text) or "UNBEKANNT"


def _pid_lebt(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))     # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


_sperre_tiefe = 0


def sperre_holen(datei: Path = None, warten_s: float = SPERRE_WARTEN_S) -> None:
    """Exklusiver Zugriff auf das Studio-Profil (Chromium erlaubt nur einen Browser pro Profil): Upload, Nachzug und
    Weltlage-Wache warten aufeinander statt sich gegenseitig den Start zu verderben. Verwaiste Sperre (Prozess tot)
    wird uebernommen. Im selben Prozess verschachtelt aufrufbar."""
    global _sperre_tiefe
    datei = datei or SPERRE
    if _sperre_tiefe:
        _sperre_tiefe += 1
        return
    datei.parent.mkdir(parents=True, exist_ok=True)
    ende = time.time() + warten_s
    while True:
        try:
            fd = os.open(str(datei), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            _sperre_tiefe = 1
            return
        except FileExistsError:
            try:
                pid = int(datei.read_text().strip() or 0)
            except (OSError, ValueError):
                pid = 0
            alt = time.time() - datei.stat().st_mtime if datei.exists() else 0
            if (pid and not _pid_lebt(pid)) or (not pid and alt > 60):
                try:
                    datei.unlink()
                except OSError:
                    pass
                continue
            if time.time() > ende:
                raise RuntimeError(f"Studio-Profil seit {warten_s / 60:.0f} min von PID {pid} belegt")
            time.sleep(5)


def sperre_freigeben(datei: Path = None) -> None:
    global _sperre_tiefe
    if _sperre_tiefe == 0:
        return
    if _sperre_tiefe > 1:
        _sperre_tiefe -= 1
        return
    _sperre_tiefe = 0
    try:
        (datei or SPERRE).unlink()
    except OSError:
        pass

# Upload-Fortschritt im Dialog (01.10.2026, Faden f-youtube-upload-warten-auf-veroeffentlich): Studio folgt der
# Sprache des Google-Kontos (deutsch), nicht dem Browser - darum beide Sprachen. Vorfall 01.10.: «Fertig» wurde
# geklickt und der Browser geschlossen, bevor der Dateitransfer bei 100 Prozent war -> das Video blieb ein privater
# Entwurf. Jetzt: erst Transfer 100 Prozent + Verarbeitung gestartet, dann Speichern, dann Bestaetigung abwarten.
_FORTSCHRITT_JS = """() => {
  const sel = ['ytcp-uploads-dialog .progress-label', 'ytcp-video-upload-progress .progress-label',
               'ytcp-uploads-dialog ytcp-video-upload-progress', 'ytcp-video-upload-progress'];
  for (const s of sel) { const e = document.querySelector(s); if (e && e.innerText && e.innerText.trim())
      return e.innerText.trim().replace(/\s+/g, ' '); }
  return ''; }"""
_FERTIG_WORTE = re.compile(r"upload complete|upload abgeschlossen|hochladen abgeschlossen|wird verarbeitet|"
                           r"verarbeitung|processing|processed|verarbeitet|checks? complete|überprüfung|"
                           r"\b(sd|hd|4k)\b", re.I)
_LAEUFT_WORTE = re.compile(r"uploading|wird hochgeladen|hochladen|upload\b", re.I)
_FEHLER_WORTE = re.compile(r"error|fehler|failed|fehlgeschlagen|abgelehnt|rejected|limit|abgebrochen|cancel", re.I)


def upload_stand(text: str) -> tuple[str, int | None]:
    """('laeuft'|'fertig'|'fehler'|'unbekannt', prozent) aus dem Fortschrittstext des Upload-Dialogs."""
    m = re.search(r"(\d{1,3})\s*%", text or "")
    pct = int(m.group(1)) if m else None
    if not text:
        return "unbekannt", None
    if _FEHLER_WORTE.search(text) and not re.search(r"keine probleme|no issues", text, re.I):
        return "fehler", pct
    hochladen = bool(_LAEUFT_WORTE.search(text)) and not re.search(r"abgeschlossen|complete", text, re.I)
    verarbeitung = bool(_FERTIG_WORTE.search(text))
    if pct is not None and pct < 100:      # Prozent unter 100: nur fertig, wenn es klar die Verarbeitung ist
        return ("fertig" if verarbeitung and not hochladen else "laeuft"), pct
    if verarbeitung or pct == 100:
        return "fertig", pct
    return ("laeuft" if _LAEUFT_WORTE.search(text) else "unbekannt"), pct


def _warte_auf_transfer(page, log, timeout_min: float):
    """Blockiert, bis der Dateitransfer 100 Prozent hat und die Verarbeitung gestartet ist."""
    import time
    ende, letzt, letzt_log = time.time() + timeout_min * 60, None, 0.0
    while time.time() < ende:
        text = page.evaluate(_FORTSCHRITT_JS)
        stand, pct = upload_stand(text)
        if text != letzt or time.time() - letzt_log > 60:
            log(f"Upload-Fortschritt: {stand} {'' if pct is None else f'{pct} %'} «{text[:120]}»")
            letzt, letzt_log = text, time.time()
        if stand == "fertig":
            return text
        if stand == "fehler":
            raise RuntimeError(f"Studio meldet einen Upload-Fehler: {text[:200]}")
        page.wait_for_timeout(5000)
    raise RuntimeError(f"Dateitransfer nach {timeout_min:.0f} min nicht abgeschlossen (letzter Stand «{letzt}»)")


def _thumbnail_setzen(page, thumb_path, log, shot) -> str:
    """Versucht das eigene Thumbnail im Upload-Dialog: Klick auf «Datei hochladen» (ytcp-thumbnail-uploader
    #select-button) mit Dateiauswahl. 'gesetzt' | 'gesperrt: ...' | 'unklar: ...'. Stand 01.10.2026: ohne
    Telefonbestaetigung des Kanals oeffnet Studio statt der Dateiauswahl den Dialog «Du musst deine Telefonnummer
    bestaetigen, um benutzerdefinierte Thumbnails hinzuzufuegen» - der wird abgebrochen und als gesperrt gemeldet."""
    sperre = re.compile(r"telefon|phone|verif|bestätig", re.I)

    def dialoge():
        return [" ".join(d.inner_text()[:300].split()) for d in
                page.locator("tp-yt-paper-dialog:visible, ytcp-dialog:visible, [role=dialog]:visible").all()
                if d.inner_text().strip()]

    knopf = page.locator("ytcp-thumbnail-uploader #select-button").first
    if not knopf.count():
        return "gesperrt: kein Feld «Datei hochladen» für Thumbnails"
    vorher = set(dialoge())
    try:
        knopf.scroll_into_view_if_needed()
        with page.expect_file_chooser(timeout=8000) as fc:
            knopf.click()
        fc.value.set_files(str(thumb_path))
    except Exception:
        neu = [d for d in dialoge() if d not in vorher]
        shot("thumbnail_sperre")
        log(f"Thumbnail: keine Dateiauswahl, Dialog: {neu}")
        abbrechen = page.locator("[role=dialog]:visible #cancel-button, tp-yt-paper-dialog:visible #cancel-button, "
                                 "ytcp-dialog:visible #cancel-button").first
        if abbrechen.count():
            abbrechen.click()
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        if any(sperre.search(d) for d in neu):
            return "gesperrt: Studio verlangt die Telefonbestätigung des Kanals für eigene Thumbnails"
        return "unklar: Studio hat keine Dateiauswahl geöffnet"
    page.wait_for_timeout(5000)
    shot("thumbnail")
    eigen = page.evaluate("""() => Array.from(document.querySelectorAll('ytcp-video-thumbnail-editor img'))
                              .some(i => /^blob:|^data:image/.test(i.src || ''))""")
    return "gesetzt" if eigen else "unklar: keine Vorschau des eigenen Bildes sichtbar"


def _sichtbar_text(page, sel: str) -> str | None:
    """Text eines Studio-Elements, wenn es selbst oder ein Dialog darin sichtbar ist (die ytcp-*-Huellen haben oft
    keine eigene Groesse, dann meldet is_visible() False, obwohl der Dialog offen ist)."""
    loc = page.locator(sel)
    try:
        if not loc.count():
            return None
        el = loc.first
        if el.is_visible() or el.locator("tp-yt-paper-dialog:visible, [role=dialog]:visible").count():
            return " ".join(el.inner_text()[:600].split())
    except Exception:   # noqa: BLE001 - Element verschwindet waehrend des Lesens
        return None
    return None


def _trotzdem_knopf(page):
    """(Knopf, Dialogtext) fuer «Trotzdem veroeffentlichen», aber nur im Zwischendialog «Vorabpruefung laeuft noch»
    (Vorfall 06.10.2026). Andere Warnungen (gefundene Probleme) werden nie automatisch weggeklickt."""
    try:
        for d in page.locator(_DIALOGE).all():
            try:
                text = " ".join(d.inner_text()[:800].split())
            except Exception:   # noqa: BLE001
                continue
            if zwischendialog_art(text) != "vorab_laeuft":
                continue
            for b in (d.get_by_role("button", name=_TROTZDEM), d.get_by_text(_TROTZDEM)):
                if b.count() and b.first.is_visible():
                    return b.first, text
        b = page.get_by_role("button", name=_TROTZDEM)
        if b.count() and b.first.is_visible() and zwischendialog_art(page.inner_text("body")) == "vorab_laeuft":
            return b.first, "Vorabprüfung läuft noch (Seitentext)"
    except Exception:   # noqa: BLE001
        pass
    return None, ""


def _warte_auf_pruefung(page, log, max_min: float = PRUEF_WARTEN_MIN) -> str:
    """Vor dem Klick auf Veroeffentlichen: Studios Vorabpruefung abwarten (sonst kommt der Zwischendialog, Vorfall
    06.10.2026). Nach max_min wird trotzdem veroeffentlicht (Marlons Dauerfreigabe), der Dialog wird dann bestaetigt."""
    ende, letzt_log, text = time.time() + max_min * 60, 0.0, ""
    while time.time() < ende:
        try:
            text = page.evaluate(_FORTSCHRITT_JS)
        except Exception:   # noqa: BLE001
            text = ""
        if not pruefung_laeuft(text):
            return text
        if time.time() - letzt_log > 60:
            log(f"Vorabprüfung läuft: «{text[:120]}»")
            letzt_log = time.time()
        page.wait_for_timeout(5000)
    log(f"Vorabprüfung nach {max_min:.0f} min noch nicht fertig («{text[:120]}») - veröffentliche trotzdem")
    return text


def _bestaetigung(page, visibility: str, log, timeout_s: int = 600, zu_gnade_s: int = 90) -> str:
    """Nach «Speichern/Veroeffentlichen»: wartet auf Studios Bestaetigung. Oeffentlich/nicht gelistet zeigt Studio
    den Dialog «Video veroeffentlicht» (ytcp-video-share-dialog) oder «wird noch verarbeitet, danach
    veroeffentlicht» (ytcp-uploads-still-processing-dialog); privat schliesst sich der Dialog nur.
    Vorfall 02./03.10.2026: nach dem Schliessen des Upload-Dialogs wurde nur EINMAL 3 s nachgeprueft, bevor
    "dialog zu ohne bestaetigung" gemeldet wurde - der Bestaetigungsdialog kann aber deutlich spaeter kommen.
    Jetzt: nach dem Schliessen weiter im selben Zeitbudget pollen, erst nach zu_gnade_s ohne Bestaetigung aufgeben.
    Vorfall 06.10.2026: der Zwischendialog «Vorabpruefung laeuft noch» wird mit «Trotzdem veroeffentlichen»
    bestaetigt (hoechstens 3 Mal); ob das Video danach wirklich oeffentlich ist, prueft veroeffentlichen() frisch."""
    zu_seit, trotzdem = None, 0
    ende = time.time() + timeout_s
    while time.time() < ende:
        for sel, art in (("ytcp-video-share-dialog", "veroeffentlicht"),
                         ("ytcp-uploads-still-processing-dialog", "wird nach der Verarbeitung veroeffentlicht")):
            text = _sichtbar_text(page, sel)
            if text:
                log(f"Studio-Bestätigung ({sel}): {text[:300]}")
                return art
        knopf, text = _trotzdem_knopf(page)
        if knopf is not None and trotzdem < 3:
            trotzdem += 1
            log(f"Studio-Zwischendialog «{text[:160]}» - klicke «Trotzdem veröffentlichen» ({trotzdem}/3)")
            try:
                knopf.click()
            except Exception as e:   # noqa: BLE001
                log(f"Klick auf «Trotzdem veröffentlichen» fehlgeschlagen: {e}")
            zu_seit = None
            page.wait_for_timeout(3000)
            continue
        text = _sichtbar_text(page, "ytcp-prechecks-warning-dialog")
        if text and zwischendialog_art(text) != "vorab_laeuft":
            log(f"Studio-Warnung (ytcp-prechecks-warning-dialog): {text[:300]}")
            raise RuntimeError(f"Studio zeigt eine Warnung vor dem Veroeffentlichen: {text[:300]}")
        try:
            zu = not page.locator("#done-button:visible").count() and not _sichtbar_text(page, "ytcp-uploads-dialog")
        except Exception:   # noqa: BLE001
            zu = False
        if zu and visibility == "PRIVATE":
            return "privat gespeichert"
        if zu:
            if zu_seit is None:
                zu_seit = time.time()
                log("Upload-Dialog geschlossen, warte weiter auf die Veröffentlichungs-Bestätigung")
            elif time.time() - zu_seit > zu_gnade_s:
                log(f"Upload-Dialog seit {zu_gnade_s} s geschlossen, immer noch keine Bestätigung sichtbar")
                return "dialog zu ohne bestaetigung"
        page.wait_for_timeout(1000)
    raise RuntimeError("keine Bestätigung von Studio nach dem Speichern")


def braucht_nachzug(ergebnis: dict, visibility: str) -> bool:
    """True, wenn ein Upload nicht privat gedacht war, die unabhaengige oEmbed-Kontrolle das Video aber nicht als
    oeffentlich/nicht gelistet bestaetigt hat - dann lohnt sich ein Versuch, die Sichtbarkeit ueber Studios
    Bearbeiten-Seite nachzuziehen, statt wie bisher nur zu melden und auf eine Handkorrektur zu warten (Vorfall
    Fairford-Folge 05./06.10.2026: Studio hat die Veroeffentlichung im Upload-Dialog nie bestaetigt, das Video
    blieb bis zur Handkorrektur ein privater Entwurf). Pure Funktion, offline testbar."""
    return visibility.upper() != "PRIVATE" and ergebnis.get("oeffentlich_bestaetigt") is False


def _sichtbarkeit_lesen(page) -> str:
    """Text des Sichtbarkeits-Felds der Bearbeiten-Seite; Rueckfall: welche der exakten Beschriftungen sichtbar sind
    (so hat der Helfer-Worker am 06.10.2026 «Öffentlich» bestaetigt)."""
    for sel in ("ytcp-video-metadata-visibility", "#visibility-text", "ytcp-video-visibility-select"):
        loc = page.locator(sel)
        try:
            for i in range(min(loc.count(), 3)):
                el = loc.nth(i)
                if el.is_visible():
                    t = el.inner_text()
                    if sichtbarkeit_aus_text(t):
                        return t
        except Exception:   # noqa: BLE001
            continue
    sichtbar = []
    for label in ("Öffentlich", "Nicht gelistet", "Privat", "Public", "Unlisted", "Private"):
        try:
            loc = page.get_by_text(label, exact=True)
            if loc.count() and loc.first.is_visible():
                sichtbar.append(label)
        except Exception:   # noqa: BLE001
            continue
    return " ".join(sichtbar)


def _status_seite(page, video_id: str, warten_s: float = 60) -> str:
    """Frischer Aufruf der Bearbeiten-Seite: ENTWURF | PUBLIC | UNLISTED | PRIVATE | UNBEKANNT."""
    page.goto(f"https://studio.youtube.com/video/{video_id}/edit", wait_until="domcontentloaded")
    ende, titel_seit = time.time() + warten_s, None
    while time.time() < ende:
        try:
            text = page.inner_text("body")
        except Exception:   # noqa: BLE001
            text = ""
        if _ENTWURF.search(text):
            return "ENTWURF"
        try:
            titel = page.locator("#title-textarea #textbox").count() > 0
        except Exception:   # noqa: BLE001
            titel = False
        if titel:
            titel_seit = titel_seit or time.time()
            st = studio_status_aus(text, _sichtbarkeit_lesen(page))
            if st != "UNBEKANNT" and time.time() - titel_seit > 2:   # Entwurfs-Hinweis kommt evtl. kurz danach
                return st
        page.wait_for_timeout(1000)
    return "UNBEKANNT"


def _entwurf_abschliessen(page, visibility: str, log, shot) -> None:
    """Entwurf (Vorfall 06.10.2026): «Entwurf bearbeiten» oeffnet den Upload-Assistenten wieder; bis zur Sichtbarkeit
    weiterklicken, Sichtbarkeit waehlen, Vorabpruefung abwarten, Veroeffentlichen, Zwischendialog bestaetigen."""
    knopf = page.get_by_role("button", name=_ENTWURF_KNOPF)
    if not knopf.count():
        knopf = page.get_by_text(_ENTWURF_KNOPF)
    knopf.first.click()
    page.wait_for_selector("#next-button", state="visible")
    radio = page.locator(f'tp-yt-paper-radio-button[name="{visibility}"]')
    for _ in range(6):        # Details -> Video-Elemente -> Vorabpruefung -> Sichtbarkeit
        if radio.count() and radio.first.is_visible():
            break
        page.locator("#next-button").first.click()
        page.wait_for_timeout(2500)
    _click_radio(page, visibility)
    shot("entwurf_sichtbarkeit")
    _warte_auf_pruefung(page, log)
    page.wait_for_function(
        "() => { const b = document.querySelector('#done-button'); "
        "return b && b.getAttribute('aria-disabled') !== 'true' && !b.hasAttribute('disabled'); }",
        timeout=STEP_TIMEOUT_MS)
    page.locator("#done-button").first.click()
    log(f"Entwurf: Sichtbarkeit {visibility} gewählt und Veröffentlichen geklickt")
    _bestaetigung(page, visibility, log, timeout_s=300)
    shot("entwurf_bestaetigung")
    page.wait_for_timeout(5000)


def _sichtbarkeit_bearbeiten(page, visibility: str, log, shot) -> None:
    """Schon veroeffentlichtes/privates Video: Sichtbarkeits-Feld der Bearbeiten-Seite. Selektoren aus den am
    25./28.09.2026 gegen die echte Studio-Seite verifizierten Skripten _work/youtube_upload/set_public.py und
    set_private.py."""
    auswahl = page.locator("ytcp-video-metadata-visibility #select-button, #visibility-text, "
                           "ytcp-icon-button.ytcp-video-metadata-visibility").first
    auswahl.wait_for(state="visible")
    auswahl.click()
    page.wait_for_selector(f'tp-yt-paper-radio-button[name="{visibility}"]', state="attached")
    shot("visibility_01_dialog")
    _click_radio(page, visibility)
    teilspeichern = page.locator("#save-button").first
    teilspeichern.wait_for(state="visible")
    teilspeichern.click()
    page.wait_for_timeout(3000)
    for _ in range(3):
        knopf, text = _trotzdem_knopf(page)
        if knopf is None:
            break
        log(f"Studio-Zwischendialog «{text[:160]}» - klicke «Trotzdem veröffentlichen»")
        knopf.click()
        page.wait_for_timeout(3000)
    haupt = page.locator("#save").first
    if haupt.count() and haupt.get_attribute("aria-disabled") != "true":
        haupt.click()
        page.wait_for_timeout(3000)
    shot("visibility_02_gespeichert")
    log(f"Sichtbarkeit auf {visibility} gespeichert (Studio-Bearbeiten-Seite)")


def veroeffentlichen(video_id: str, visibility: str = "PUBLIC", log=None, debug_dir=None,
                     versuche: int | None = None, pause_s: float = 45) -> dict:
    """Bringt ein hochgeladenes Video sicher auf die Ziel-Sichtbarkeit und prueft das jedes Mal per frischem
    Seitenaufruf (Vorfall Bolsonaro-Folge 06.10.2026: Entwurf statt oeffentlich). Pro Durchgang: Status lesen; Ziel
    erreicht -> fertig; ENTWURF -> Assistent abschliessen; sonst Sichtbarkeits-Feld; dann frisch nachpruefen.
    Rueckgabe: ok, status (letzter Studio-Status), versuche (Eingriffe), nachgezogen, verlauf, fehler.
    Ist der Studio-Status nicht lesbar (Seite umgebaut), entscheidet bei PUBLIC/UNLISTED die oEmbed-Kontrolle."""
    from playwright.sync_api import sync_playwright

    visibility = visibility.upper()
    versuche = versuche or VEROEFFENTLICHEN_VERSUCHE
    shots = Path(debug_dir) if debug_dir else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    log = log or logger.info
    res = {"ok": False, "status": "UNBEKANNT", "versuche": 0, "nachgezogen": False, "verlauf": [], "fehler": None}

    for n in range(1, versuche + 1):
        try:
            with sync_playwright() as p:
                context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
                page = context.new_page()
                page.set_default_timeout(STEP_TIMEOUT_MS)

                def shot(name):
                    if shots:
                        try:
                            page.screenshot(path=str(shots / f"veroeffentlichen_{n}_{name}.png"))
                        except Exception:   # noqa: BLE001
                            pass
                try:
                    st = _status_seite(page, video_id)
                    res["status"] = st
                    res["verlauf"].append(st)
                    log(f"Studio-Status {video_id}: {st} (Ziel {visibility}, Durchgang {n}/{versuche})")
                    if st == visibility:
                        res["ok"] = True
                        return res
                    shot("vorher")
                    res["versuche"] += 1
                    if st == "ENTWURF" or (st == "UNBEKANNT" and page.get_by_text(_ENTWURF_KNOPF).count()):
                        _entwurf_abschliessen(page, visibility, log, shot)
                    else:
                        _sichtbarkeit_bearbeiten(page, visibility, log, shot)
                    res["nachgezogen"] = True
                    page.wait_for_timeout(5000)
                    st = _status_seite(page, video_id)          # frischer Seitenaufruf nach dem Klick
                    res["status"] = st
                    res["verlauf"].append(st)
                    shot("nachher")
                    log(f"Studio-Status nach dem Eingriff: {st}")
                    if st == visibility:
                        res["ok"] = True
                        return res
                finally:
                    context.close()
        except Exception as e:   # noqa: BLE001 - naechster Durchgang mit frischem Browser
            res["fehler"] = str(e)[:500]
            log(f"Veröffentlichen-Durchgang {n}/{versuche} fehlgeschlagen: {str(e)[:300]}")
        if n < versuche:
            time.sleep(pause_s)
    if res["status"] == "UNBEKANNT" and visibility in ("PUBLIC", "UNLISTED"):
        res["ok"] = oeffentlich_pruefen(video_id, 2, log)
        res["status"] = "OEMBED_OK" if res["ok"] else res["status"]
    return res


def visibility_setzen(video_id: str, visibility: str, log=None, debug_dir=None) -> None:
    """Alte Schnittstelle (CLI --set-visibility): jetzt veroeffentlichen() mit Entwurfs-Weg und frischer
    Nachpruefung. Wirft, wenn die Ziel-Sichtbarkeit danach nicht bestaetigt ist."""
    res = veroeffentlichen(video_id, visibility, log, debug_dir)
    if not res["ok"]:
        raise RuntimeError(f"Sichtbarkeit {visibility} nicht erreicht (Studio-Status {res['status']}, "
                           f"{res.get('fehler') or 'ohne Fehlermeldung'})")


def oeffentlich_pruefen(video_id: str, minuten: float = 30, log=None) -> bool:
    """Unabhaengige Kontrolle von aussen: oEmbed liefert nur fuer oeffentliche/nicht gelistete Videos Daten.
    urllib statt httpx (06.10.2026: «No module named 'httpx'» in einer fremden venv brach den Upload-Schritt ab)."""
    import urllib.error
    import urllib.request
    ende = time.time() + minuten * 60
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    while True:
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                titel = json.loads(r.read().decode("utf-8", "replace")).get("title", "")
            if log:
                log(f"oEmbed bestätigt: {video_id} ist öffentlich abrufbar ({titel[:80]})")
            return True
        except urllib.error.HTTPError as e:
            if log:
                log(f"oEmbed {e.code} - noch nicht öffentlich abrufbar")
        except Exception as e:   # noqa: BLE001
            if log:
                log(f"oEmbed-Abfrage fehlgeschlagen: {e}")
        if time.time() > ende:
            return False
        time.sleep(30)


def _wizard(page, video_path: str, meta: dict, thumb_path, visibility: str, log, shot, on_video_id,
            timeout_min: float, on_transfer=None) -> dict:
    """Gemeinsamer Upload-Assistent fuer Shorts-Jobs (run) und Weltlage-Folgen (upload_datei)."""
    _open_upload_page(page)
    if f"/channel/{NEWS_YOUTUBE_CHANNEL_ID}" not in page.url:
        raise RuntimeError(f"Studio opened a different channel than {NEWS_YOUTUBE_CHANNEL_ID} "
                           f"(url: {page.url[:100]}) - not uploading. Is the profile still signed in?")
    page.set_input_files("input[type=file]", video_path)
    on_video_id(None)                                   # ab hier kein blinder Neuversuch mehr
    log(f"Datei übergeben: {video_path}")
    page.wait_for_selector("#title-textarea #textbox")
    try:
        video_id = _video_id_from_dialog(page)
    except Exception as e:
        # Fehlerfund 18.10.2026 (Task 20261018-152136-0684): die Datei ist schon bei Studio (set_input_files
        # ist durch), nur das Ablesen der neuen Video-ID aus dem Dialog scheiterte (z.B. Timeout). Ohne diesen
        # Fang landete das als gewoehnlicher RuntimeError ohne erkennbare Video-ID bei upload_datei() - der
        # Aufrufer (weltlage_shorts_takt.takt) sah darin "nie bei Studio angekommen" und wiederholte denselben
        # Upload in der naechsten Stunde blind: echter Doppel-Upload derselben Datei (Vorbild desselben Fehlers
        # auf dem Schwesterkanal "Jarvis KI", 17.10.2026). UploadHaltedForReview markiert fuer jeden Aufrufer
        # eindeutig: Status unklar, NIE automatisch erneut hochladen, zuerst in Studio pruefen.
        raise UploadHaltedForReview(
            f"Datei {video_path} wurde an Studio übergeben, die neue Video-ID konnte danach aber nicht gelesen "
            f"werden ({e}) - in Studio prüfen (neuester Entwurf), nicht blind erneut hochladen.") from e
    on_video_id(video_id)
    log(f"Video-ID: {video_id}")
    _fill_textbox(page, "#title-textarea #textbox", meta["title"])
    _fill_textbox(page, "#description-textarea #textbox", meta["description"])
    thumb = "kein Thumbnail"
    if thumb_path and Path(thumb_path).exists():
        thumb = _thumbnail_setzen(page, thumb_path, log, shot)
        log(f"Thumbnail: {thumb}")
    _click_radio(page, "VIDEO_MADE_FOR_KIDS_NOT_MFK")
    page.locator("#toggle-button").first.click()          # "Show more"
    page.wait_for_selector('tp-yt-paper-radio-button[name="VIDEO_HAS_ALTERED_CONTENT_YES"]', state="attached")
    _click_radio(page, "VIDEO_HAS_ALTERED_CONTENT_YES")   # YouTube's synthetic-media disclosure
    _click_radio(page, "VIDEO_PAID_PRODUCT_PLACEMENT_NO")
    _add_tags(page, meta.get("tags") or [])
    _set_language(page, meta.get("language") or "de")
    shot("details")
    for _ in range(3):  # Details -> Video elements -> Checks -> Visibility
        page.locator("#next-button").first.click()
        page.wait_for_timeout(2500)
    _click_radio(page, visibility)
    for andere in ("PUBLIC", "UNLISTED", "PRIVATE"):
        if andere != visibility:
            r = page.locator(f'tp-yt-paper-radio-button[name="{andere}"]').first
            if r.count() and r.get_attribute("aria-checked") == "true":
                raise RuntimeError(f"Sichtbarkeit {andere} ist noch ausgewählt statt {visibility}")
    shot("sichtbarkeit")
    log(f"Sichtbarkeit {visibility} ausgewählt, warte auf 100 Prozent Dateitransfer")
    stand = _warte_auf_transfer(page, log, timeout_min)
    if on_transfer:
        on_transfer()
    if visibility != "PRIVATE":
        _warte_auf_pruefung(page, log)      # sonst Zwischendialog «Vorabpruefung laeuft noch» (Vorfall 06.10.2026)
    page.wait_for_function(
        "() => { const b = document.querySelector('#done-button'); "
        "return b && b.getAttribute('aria-disabled') !== 'true' && !b.hasAttribute('disabled'); }",
        timeout=int(timeout_min * 60_000),
    )
    page.wait_for_timeout(1500)
    page.locator("#done-button").first.click()
    log("Speichern/Veröffentlichen geklickt")
    bestaetigt = _bestaetigung(page, visibility, log)
    shot("bestaetigung")
    # Sicherheitsabstand: Studio speichert die Einstellungen asynchron - Browser nicht sofort schliessen
    page.wait_for_timeout(8000)
    close = page.locator("#close-button").first
    if close.count() and close.is_visible():
        close.click()
    return {"video_id": video_id, "transfer": stand, "bestaetigung": bestaetigt, "thumbnail": thumb}


def upload_datei(video_path, meta: dict, thumb_path=None, visibility: str = "PUBLIC", log_path=None,
                 debug_dir=None, timeout_min: float | None = None, pruef_minuten: float = 30) -> dict:
    """Laedt eine fertige Datei (Weltlage-Folge) hoch, ohne Job-Datenbank. meta: title, description, tags,
    language. Wartet auf 100 Prozent Transfer, Vorabpruefung und Studios Bestaetigung; bei oeffentlich/nicht
    gelistet danach veroeffentlichen() mit frischem Seitenaufruf (Status lesen, Entwurf/Sichtbarkeit nachziehen, bis
    zu 3 Durchgaenge). pruef_minuten bleibt nur fuer alte Aufrufer. Protokoll Zeile fuer Zeile in log_path.
    Rueckgabe: video_id, transfer, bestaetigung, thumbnail, oeffentlich_bestaetigt, studio_status."""
    from playwright.sync_api import sync_playwright
    from config.settings import NEWS_UPLOAD_TIMEOUT_MINUTEN

    require("NEWS_YOUTUBE_CHANNEL_ID")
    visibility = visibility.upper()
    timeout_min = timeout_min or NEWS_UPLOAD_TIMEOUT_MINUTEN
    shots = Path(debug_dir) if debug_dir else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    def log(msg):
        logger.info(msg)
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().astimezone():%Y-%m-%d %H:%M:%S} {msg}\n")

    zustand = {"video_id": None, "transfer_fertig": False}

    def shot(name):
        if shots:
            try:
                page.screenshot(path=str(shots / f"upload_{name}.png"))
            except Exception:
                pass

    fehler = None
    with sync_playwright() as p:
        context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
        page = context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        try:
            ergebnis = _wizard(page, str(video_path), meta, thumb_path, visibility, log, shot,
                               lambda vid: zustand.update(video_id=vid) if vid else None, timeout_min,
                               on_transfer=lambda: zustand.update(transfer_fertig=True))
        except Exception as e:
            shot("fehler")
            log(f"FEHLER: {e}")
            fehler = e
        finally:
            context.close()
    if fehler is not None:
        # Datei komplett bei YouTube, nur der Assistent hakte (Timeout, Zwischendialog): kein neuer Upload, sondern
        # den vorhandenen Entwurf ueber die Bearbeiten-Seite abschliessen - kein Duplikat-Risiko (gleiche Video-ID).
        # Seit 07.10.2026 auch bei PRIVAT (Weltlage-Vorab-Upload): ein Entwurf ist nicht oeffentlich, der Schritt
        # "veroeffentlichen" des Tageslaufs schliesst ihn zum Slot ueber veroeffentlichen() ab.
        if zustand["video_id"] and zustand["transfer_fertig"]:
            log(f"Assistent nach vollständigem Transfer abgebrochen - schliesse Entwurf {zustand['video_id']} ab")
            ergebnis = {"video_id": zustand["video_id"], "transfer": "fertig",
                        "bestaetigung": f"assistent-fehler: {str(fehler)[:200]}", "thumbnail": "unklar"}
        elif zustand["video_id"]:
            raise UploadHaltedForReview(f"Upload {zustand['video_id']} nach Dateiübergabe fehlgeschlagen - "
                                        f"in Studio prüfen, nicht blind wiederholen: {fehler}") from fehler
        else:
            raise fehler
    ergebnis["oeffentlich_bestaetigt"] = None
    if visibility != "PRIVATE":
        # Nie mehr nur auf Studios Bestaetigungsdialog vertrauen: frischer Seitenaufruf, Status lesen, bei Bedarf
        # Entwurf/Sichtbarkeit nachziehen und erneut pruefen (Vorfall Bolsonaro-Folge 06.10.2026)
        v = veroeffentlichen(ergebnis["video_id"], visibility, log, debug_dir)
        ergebnis.update(studio_status=v["status"], oeffentlich_bestaetigt=bool(v["ok"]),
                        veroeffentlichen_verlauf=v["verlauf"])
        if v["nachgezogen"]:
            ergebnis["nachgezogen"] = True
        if not v["ok"]:
            ergebnis["nachzug_fehler"] = (v.get("fehler") or f"Studio-Status {v['status']}")[:500]
    log(f"FERTIG: {ergebnis}")
    return ergebnis


def _launch(p, headless: bool):
    """Persistent context on a real installed browser so Google's sign-in accepts it. Holt vorher die Profil-Sperre
    (sperre_holen) und gibt sie mit context.close() wieder frei."""
    sperre_holen()
    try:
        context = p.chromium.launch_persistent_context(
            str(PLAYWRIGHT_PROFILE_DIR), channel=NEWS_PLAYWRIGHT_CHANNEL, headless=headless,
            locale="en-US",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
    except Exception:
        sperre_freigeben()
        raise
    schliessen = context.close

    def close(*a, **k):
        try:
            return schliessen(*a, **k)
        finally:
            sperre_freigeben()
    context.close = close
    return context


def login():
    """One-time interactive login: opens the Google sign-in in the dedicated profile and waits
    until you close the window. Do the sign-in yourself (password / 2FA are never automated)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = _launch(p, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fwww.youtube.com%2F")
        print("1) Sign in with the Google account that owns the channel.\n"
              "2) If the channel is a brand channel: avatar -> switch account -> pick the channel.\n"
              "3) CLOSE the window when youtube.com shows the right channel.")
        page.wait_for_event("close", timeout=0)
        context.close()
    print(f"Session saved in {PLAYWRIGHT_PROFILE_DIR}")


class UploadHaltedForReview(RuntimeError):
    """Raised when the upload got far enough that a blind retry would risk a duplicate
    publish. The orchestrator must NOT auto-retry a job that failed with this - it needs a
    human to check Studio and decide (video_id, if any, is recorded on the job first)."""


def _upload_url() -> str:
    return f"https://studio.youtube.com/channel/{NEWS_YOUTUBE_CHANNEL_ID}/videos/upload?d=ud&hl=en"


def _switch_channel(page):
    """Studio answers "not authorised" for a brand channel of the same Google account while
    another channel is the active one - switch via the channel switcher, matched by the handle
    (language-independent). Read from os.environ, not settings: a resident process importing this
    module lazily must not break on a settings name it doesn't know yet."""
    import os
    handle = os.environ.get("NEWS_YOUTUBE_HANDLE", "").strip()
    if not handle:
        raise RuntimeError(f"Studio refused channel {NEWS_YOUTUBE_CHANNEL_ID} and NEWS_YOUTUBE_HANDLE "
                           "is not set, so the uploader can't switch to it - not uploading.")
    page.goto("https://www.youtube.com/channel_switcher?hl=en", wait_until="domcontentloaded")
    item = page.locator("ytd-account-item-renderer").filter(has_text=handle).first
    item.wait_for(state="visible")
    item.click()
    page.wait_for_timeout(5000)
    logger.info("switched the upload profile to channel %s", handle)


def _open_upload_page(page):
    """Upload page of the pinned channel; switches the profile's active channel once if needed."""
    page.goto(_upload_url(), wait_until="domcontentloaded")
    try:
        page.wait_for_selector("input[type=file]", state="attached", timeout=20_000)
    except Exception:
        _switch_channel(page)
        page.goto(_upload_url(), wait_until="domcontentloaded")
        page.wait_for_selector("input[type=file]", state="attached")


_STUDIO_FEHLERSEITE = re.compile(r"ein fehler ist aufgetreten|an error occurred", re.I)


def _ist_fehlerseite(page) -> bool:
    """Studios eigene, generische Absturz-/Ladefehlerseite (Maskottchen + 'Ein Fehler ist aufgetreten') -
    kein Login-/Berechtigungsproblem, sondern ein client-seitiger Ladefehler, der bei Systemlast (mehrere
    gleichzeitige Playwright-Sitzungen auf demselben Profil, Vorfall 15.10.2026 beim Shorts-Thumbnail-
    Nachtrag) öfter auftritt und mit einem einfachen Neuladen meist verschwindet."""
    try:
        return bool(_STUDIO_FEHLERSEITE.search(page.inner_text("body")))
    except Exception:   # noqa: BLE001
        return False


def _goto_edit_page(page, video_id: str, warte_auf: str, shots=None):
    """Studio-Bearbeiten-Seite eines einzelnen, bereits veroeffentlichten Videos (get_metadata,
    set_metadata, set_thumbnail). Zwei unabhaengige Fehlerbilder gefunden beim Shorts-Thumbnail-Nachtrag
    (15.10.2026): (1) das Browser-Profil ist mit anderen Kanaelen/Konten desselben Google-Kontos geteilt
    (siehe _switch_channel) - ist beim Start ein falscher Kanal aktiv, laedt die Seite gar nicht erst.
    (2) Studios eigene generische Ladefehlerseite (_ist_fehlerseite) bei hoher Systemlast (mehrere
    gleichzeitige Playwright-Sitzungen desselben Profils) - verschwindet meist nach einem Neuladen, ganz
    ohne Kanalwechsel. Erst ein paar Neuladeversuche, dann erst der (teurere) Kanalwechsel. shots (optional)
    bekommt bei endgueltigem Fehlschlag noch einen Screenshot, bevor der TimeoutError weitergereicht wird."""
    url = f"https://studio.youtube.com/video/{video_id}/edit?hl=en"
    page.goto(url, wait_until="domcontentloaded")
    for versuch in range(3):
        try:
            page.wait_for_selector(warte_auf, state="attached", timeout=20_000)
            return
        except Exception:
            if not _ist_fehlerseite(page):
                break
            page.wait_for_timeout(5000)
            page.goto(url, wait_until="domcontentloaded")
    _switch_channel(page)
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(warte_auf, state="attached")
    except Exception:
        if shots:
            page.screenshot(path=str(shots / "00_goto_fehlgeschlagen.png"), full_page=True)
        raise


def _fill_textbox(page, selector: str, text: str):
    box = page.locator(selector).first
    box.click()
    box.fill(text)


def _click_radio(page, name: str):
    """Selects a Studio radio option by its stable `name=` value and verifies it took effect."""
    radio = page.locator(f'tp-yt-paper-radio-button[name="{name}"]').first
    radio.scroll_into_view_if_needed()
    radio.click()
    for _ in range(15):
        if radio.get_attribute("aria-checked") == "true":
            return
        page.wait_for_timeout(200)
    raise RuntimeError(f"could not select the Studio option {name}")


def _add_tags(page, tags: list[str]):
    field = page.locator("ytcp-uploads-dialog input#text-input").first
    field.scroll_into_view_if_needed()
    for tag in tags:
        field.click()
        field.fill(tag[:60])
        field.press("Enter")


def _set_language(page, language: str):
    """Video language drives YouTube's auto-dubbing (it translates FROM this language)."""
    box = page.locator("#language-subtitles-cc")
    box.scroll_into_view_if_needed()
    box.locator("ytcp-dropdown-trigger").first.click()
    page.locator(f'tp-yt-paper-item[test-id="{language}"]').first.click()
    page.wait_for_timeout(500)


def _video_id_from_dialog(page) -> str:
    """The dialog shows the new video's link (youtube.com/shorts/<id> or watch?v=<id>)."""
    for _ in range(90):       # 06.10.2026: nach 30 s ohne Link abgebrochen, der Entwurf blieb verwaist in Studio
        hrefs = page.evaluate("() => Array.from(document.querySelectorAll('a')).map(a => a.href)")
        for href in hrefs:
            m = re.search(r"youtube\.com/(?:shorts/|watch\?v=)([\w-]{11})|youtu\.be/([\w-]{11})", href)
            if m:
                return m.group(1) or m.group(2)
        page.wait_for_timeout(1000)
    raise RuntimeError("could not read the new video's link from the upload dialog")


def run(job_id: str) -> str:
    from playwright.sync_api import sync_playwright

    require("NEWS_YOUTUBE_CHANNEL_ID")
    meta = build_metadata(job_id)
    video_path = str(DATA_DIR / "video" / f"{job_id}.mp4")
    thumb_path = DATA_DIR / "thumbs" / f"{job_id}.jpg"
    visibility = meta["privacy_status"].upper()   # PUBLIC | UNLISTED | PRIVATE

    with sync_playwright() as p:
        context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
        page = context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        started_upload = False

        def merke(video_id):
            nonlocal started_upload
            started_upload = True  # past this point: no blind retries
            if video_id:
                state_store.update_job(job_id, video_id=video_id, upload_method="playwright")

        try:
            from config.settings import NEWS_UPLOAD_TIMEOUT_MINUTEN
            res = _wizard(page, video_path, meta, thumb_path, visibility, logger.info, lambda name: None, merke,
                          NEWS_UPLOAD_TIMEOUT_MINUTEN)
            video_id = res["video_id"]
            status = "published" if visibility != "PRIVATE" else "uploaded_private"
            state_store.update_job(job_id, status=status, video_id=video_id, upload_method="playwright",
                                   published_at=datetime.now(timezone.utc).isoformat())
            logger.info("%s %s via Studio -> https://youtube.com/watch?v=%s (%s, %s)", status, job_id, video_id,
                        visibility, res["bestaetigung"])
            return video_id

        except Exception as e:
            if started_upload:
                state_store.update_job(job_id, status="upload_failed", error=str(e)[:2000], upload_method="playwright")
                raise UploadHaltedForReview(
                    f"upload for {job_id} failed after the file was already selected - check "
                    f"YouTube Studio by hand before retrying. Original error: {e}"
                ) from e
            state_store.mark_failed(job_id, f"playwright upload failed before file select: {e}")
            raise
        finally:
            context.close()


def _nur_status(video_id: str) -> dict:
    """Nur lesen (CLI --status): aktueller Studio-Status per frischem Seitenaufruf, ohne etwas zu aendern."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
        page = context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        try:
            return {"status": _status_seite(page, video_id)}
        finally:
            context.close()


def get_metadata(video_id: str, debug_dir: str | None = None) -> dict:
    """Reads the current title/description of an already-published video from Studio's edit
    page, so a caller can build a new description that keeps everything but one sentence."""
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    shots = Path(debug_dir) if debug_dir else None
    with sync_playwright() as p:
        context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
        page = context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        try:
            _goto_edit_page(page, video_id, "#title-textarea #textbox", shots)
            if shots:
                page.screenshot(path=str(shots / "meta_01_edit_page.png"))
            title = page.locator("#title-textarea #textbox").first.inner_text()
            description = page.locator("#description-textarea #textbox").first.inner_text()
            return {"title": title, "description": description}
        finally:
            context.close()


def set_metadata(video_id: str, title: str | None = None, description: str | None = None,
                  debug_dir: str | None = None) -> None:
    """Sets title and/or description of an already-published video via Studio's edit page.
    Only the fields given are touched; the other stays whatever Studio currently shows."""
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    shots = Path(debug_dir) if debug_dir else None
    with sync_playwright() as p:
        context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
        page = context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        try:
            _goto_edit_page(page, video_id, "#title-textarea #textbox", shots)
            if shots:
                page.screenshot(path=str(shots / "meta_01_edit_page.png"))
            if title is not None:
                _fill_textbox(page, "#title-textarea #textbox", title)
            if description is not None:
                _fill_textbox(page, "#description-textarea #textbox", description)
            if shots:
                page.screenshot(path=str(shots / "meta_02_filled.png"), full_page=True)
            save = page.locator("ytcp-button#save").first
            save.wait_for(state="visible")
            save.click()
            page.wait_for_timeout(3000)
            if shots:
                page.screenshot(path=str(shots / "meta_03_after_save.png"), full_page=True)
        finally:
            context.close()


THUMB_UPLOAD_WARTEN_S = 90      # Studio laedt die Thumbnail-Datei sofort nach der Auswahl hoch ("Wird hochgeladen…")
THUMB_SPEICHERN_WARTEN_S = 90   # bis Studios eigentlicher Speicher-Request (metadata_update) beantwortet ist
_THUMB_UPLOAD_LAEUFT = re.compile(r"wird hochgeladen|uploading", re.I)
_THUMB_SPEICHER_REQUEST = re.compile(r"/youtubei/v1/video_manager/metadata_update")
# Studio zeigt im Thumbnail-Editor nach dem Neuladen entweder die drei automatischen Videoframes
# (i9.ytimg.com/vi_webp/<id>/sd1|sd2|sd3.webp) oder, sobald ein eigenes Bild gesetzt ist, genau dieses eine Bild
# (i9.ytimg.com/vi/<id>/sddefault.jpg?v=<version>) - daran laesst sich das Ergebnis ohne Klick ablesen.
_THUMB_EIGENES_BILD = re.compile(r"ytimg\.com/vi/([A-Za-z0-9_-]{11})/[a-z]*default\.jpg\?v=", re.I)

_JS_THUMB_ZUSTAND = """() => {
  const save = document.querySelector('ytcp-button#save');
  const editor = document.querySelector('ytcp-video-thumbnail-editor');
  const imgs = Array.from(document.querySelectorAll('ytcp-video-thumbnail-editor img, ytcp-thumbnail-uploader img'))
      .map(i => (i.src || '').slice(0, 200));
  return {save_disabled: save ? save.hasAttribute('disabled') : null,
          editor_text: editor ? editor.innerText.replace(/\\s+/g, ' ').slice(0, 300) : '',
          imgs: imgs};
}"""


def _thumb_zustand(page) -> dict:
    try:
        return page.evaluate(_JS_THUMB_ZUSTAND) or {}
    except Exception:   # noqa: BLE001 - Zustand ist Diagnose, nie Abbruchgrund
        return {}


def _thumb_eigenes_bild_sichtbar(zustand: dict, video_id: str) -> bool:
    """True, wenn Studios Thumbnail-Editor das EIGENE Bild (sddefault.jpg?v=…) dieses Videos zeigt statt der
    automatischen Frame-Vorschlaege (vi_webp/…/sdN.webp)."""
    for src in zustand.get("imgs") or []:
        m = _THUMB_EIGENES_BILD.search(src)
        if m and m.group(1) == video_id:
            return True
    return False


def set_thumbnail(video_id: str, thumb_path: str, debug_dir: str | None = None) -> dict:
    """Setzt das eigene Thumbnail eines bereits veroeffentlichten Videos ueber Studios Bearbeiten-Seite (auch fuer
    Shorts: das hier gesetzte Bild ist genau die Datei, die YouTube im Shorts-Regal der Kanalseite als
    `sardefault.jpg` zeigt, Befund 19.10.2026 per ytInitialData der echten Kanal-Shorts-Seite).

    Befund 19.10.2026 (Task 20261019-193153-93d4, vierter Anlauf "Shorts ohne Thumbnail"): die alte Fassung
    wartete nach dem Speichern-Klick fest 3 s und schloss dann den Browser. Studio schickt den eigentlichen
    Speicher-Request (youtubei/v1/video_manager/metadata_update) aber erst NACH einer Kette von Attestierungs-
    Aufrufen (att/get, att/esr, security/get_web_reauth_url, ars/grst) - gemessen 6,4 s nach dem Klick. Je nach
    Tagesform von Studio/Netz lag die Kette unter oder ueber 3 s, darum "funktionierte" das Setzen scheinbar
    zufaellig (am 19.10. viermal hintereinander nicht, mit identischem "Erfolg" im Log). Dazu wurde der
    Speichern-Knopf teils geklickt, waehrend die Datei noch hochlud ("Wird hochgeladen…").

    Jetzt deterministisch: (1) warten, bis der Datei-Upload im Editor beendet ist und der Speichern-Knopf aktiv
    wird; (2) Speichern klicken und auf die Antwort des metadata_update-Requests warten (zusaetzlich bis der
    Knopf wieder inaktiv ist); (3) Seite neu laden und ablesen, ob Studio jetzt das eigene Bild zeigt. Rueckgabe
    {"gespeichert": bool (Speicher-Request beantwortet), "studio_bestaetigt": bool|None (nach Neuladen sichtbar),
    "dauer_s", "hinweis"} - Aufrufer entscheiden damit selbst, statt einem fehlerfreien Klick zu vertrauen.
    debug_dir bekommt pro Schritt einen Screenshot."""
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    thumb_path = Path(thumb_path)
    if not thumb_path.exists():
        raise FileNotFoundError(thumb_path)
    shots = Path(debug_dir) if debug_dir else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    start = time.time()
    ergebnis = {"gespeichert": False, "studio_bestaetigt": None, "hinweis": "", "dauer_s": 0.0}

    with sync_playwright() as p:
        context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
        page = context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        try:
            _goto_edit_page(page, video_id, "#file-loader", shots)
            if shots:
                page.screenshot(path=str(shots / "01_edit_page.png"))
            page.set_input_files("#file-loader", str(thumb_path))
            # (1) Datei-Upload im Editor abwarten
            ende = time.time() + THUMB_UPLOAD_WARTEN_S
            zustand = {}
            while time.time() < ende:
                page.wait_for_timeout(1000)
                zustand = _thumb_zustand(page)
                laeuft = bool(_THUMB_UPLOAD_LAEUFT.search(zustand.get("editor_text") or ""))
                if not laeuft and zustand.get("save_disabled") is False:
                    break
            else:
                ergebnis["hinweis"] = "Thumbnail-Upload im Editor nicht fertig geworden"
                if shots:
                    page.screenshot(path=str(shots / "02_upload_haengt.png"), full_page=True)
                return ergebnis
            if shots:
                page.screenshot(path=str(shots / "02_after_file_set.png"), full_page=True)
            # (2) Speichern und den eigentlichen Speicher-Request abwarten
            save = page.locator("ytcp-button#save").first
            save.wait_for(state="visible")
            try:
                with page.expect_response(lambda r: bool(_THUMB_SPEICHER_REQUEST.search(r.url)),
                                          timeout=THUMB_SPEICHERN_WARTEN_S * 1000) as antwort:
                    save.click()
                status = antwort.value.status
                ergebnis["gespeichert"] = status == 200
                if status != 200:
                    ergebnis["hinweis"] = f"metadata_update antwortete HTTP {status}"
            except Exception as e:   # noqa: BLE001 - Timeout o.ae.: kein Speicher-Request gesehen
                ergebnis["hinweis"] = f"kein Speicher-Request innerhalb {THUMB_SPEICHERN_WARTEN_S}s ({type(e).__name__})"
            ende = time.time() + 30
            while time.time() < ende:
                if _thumb_zustand(page).get("save_disabled"):
                    break
                page.wait_for_timeout(1000)
            if shots:
                page.screenshot(path=str(shots / "03_after_save.png"), full_page=True)
            # (3) Neu laden und ablesen, was Studio jetzt wirklich zeigt
            try:
                page.wait_for_timeout(2000)
                page.reload(wait_until="domcontentloaded")
                page.wait_for_selector("#file-loader", state="attached", timeout=60_000)
                page.wait_for_timeout(4000)
                zustand = _thumb_zustand(page)
                ergebnis["studio_bestaetigt"] = _thumb_eigenes_bild_sichtbar(zustand, video_id)
                if shots:
                    page.screenshot(path=str(shots / "04_after_reload.png"), full_page=True)
            except Exception as e:   # noqa: BLE001 - Rueckkontrolle fehlgeschlagen = unbekannt, nicht "nein"
                ergebnis["studio_bestaetigt"] = None
                ergebnis["hinweis"] = (ergebnis["hinweis"] + f"; Rueckkontrolle fehlgeschlagen ({type(e).__name__})").strip("; ")
        finally:
            context.close()
    ergebnis["dauer_s"] = round(time.time() - start, 1)
    logger.info("set_thumbnail %s: %s", video_id, ergebnis)
    return ergebnis


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if "--login" in sys.argv:
        login()
    elif "--set-thumbnail" in sys.argv:
        idx = sys.argv.index("--set-thumbnail")
        debug = None
        if "--debug-dir" in sys.argv:
            d_idx = sys.argv.index("--debug-dir")
            debug = sys.argv[d_idx + 1]
        set_thumbnail(sys.argv[idx + 1], sys.argv[idx + 2], debug_dir=debug)
    elif "--set-title" in sys.argv:
        idx = sys.argv.index("--set-title")
        set_metadata(sys.argv[idx + 1], title=sys.argv[idx + 2])
    elif "--set-visibility" in sys.argv:
        idx = sys.argv.index("--set-visibility")
        visibility_setzen(sys.argv[idx + 1], sys.argv[idx + 2], log=logger.info)
    elif "--publish" in sys.argv or "--status" in sys.argv:
        # Weltlage-Wache: letzte Zeile = JSON, Exit 0 nur bei bestaetigter Ziel-Sichtbarkeit
        nur_status = "--status" in sys.argv
        idx = sys.argv.index("--status" if nur_status else "--publish")
        vid = sys.argv[idx + 1]
        ziel = sys.argv[idx + 2] if len(sys.argv) > idx + 2 and not sys.argv[idx + 2].startswith("--") else "PUBLIC"
        debug = sys.argv[sys.argv.index("--debug-dir") + 1] if "--debug-dir" in sys.argv else None
        res = _nur_status(vid) if nur_status else veroeffentlichen(vid, ziel, logger.info, debug)
        print(json.dumps(res, ensure_ascii=False))
        sys.exit(0 if res.get("ok") or (nur_status and res.get("status") != "UNBEKANNT") else 1)
    else:
        run(sys.argv[1])
