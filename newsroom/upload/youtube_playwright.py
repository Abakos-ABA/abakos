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
"""
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from config.settings import (
    DATA_DIR, NEWS_PLAYWRIGHT_CHANNEL, NEWS_PLAYWRIGHT_HEADLESS, NEWS_YOUTUBE_CHANNEL_ID,
    PLAYWRIGHT_PROFILE_DIR, require,
)
from orchestrator import state_store
from upload.metadata import build as build_metadata

logger = logging.getLogger(__name__)

STEP_TIMEOUT_MS = 60_000
UPLOAD_TIMEOUT_MS = 20 * 60_000   # file transfer + processing of the dialog, generous on purpose

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


def _bestaetigung(page, visibility: str, log, timeout_s: int = 600, zu_gnade_s: int = 60) -> str:
    """Nach «Speichern/Veroeffentlichen»: wartet auf Studios Bestaetigung. Oeffentlich/nicht gelistet zeigt Studio
    den Dialog «Video veroeffentlicht» (ytcp-video-share-dialog) oder «wird noch verarbeitet, danach
    veroeffentlicht» (ytcp-uploads-still-processing-dialog); privat schliesst sich der Dialog nur.
    Vorfall 02./03.10.2026: nach dem Schliessen des Upload-Dialogs wurde nur EINMAL 3 s nachgeprueft, bevor
    "dialog zu ohne bestaetigung" gemeldet wurde - der Bestaetigungsdialog kann aber deutlich spaeter kommen.
    Jetzt: nach dem Schliessen weiter im selben Zeitbudget pollen, erst nach zu_gnade_s ohne Bestaetigung aufgeben."""
    import time
    zu_seit = None
    for _ in range(timeout_s):
        for sel, art in (("ytcp-video-share-dialog", "veroeffentlicht"),
                         ("ytcp-uploads-still-processing-dialog", "wird nach der Verarbeitung veroeffentlicht"),
                         ("ytcp-prechecks-warning-dialog", "Warnung vor Veroeffentlichung")):
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                text = loc.first.inner_text()[:300].replace("\n", " | ")
                log(f"Studio-Bestätigung ({sel}): {text}")
                if art.startswith("Warnung"):
                    raise RuntimeError(f"Studio zeigt eine Warnung vor dem Veroeffentlichen: {text}")
                return art
        zu = not page.locator("ytcp-uploads-dialog").count() or not page.locator("ytcp-uploads-dialog").first.is_visible()
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


def visibility_setzen(video_id: str, visibility: str, log=None, debug_dir=None) -> None:
    """Setzt die Sichtbarkeit eines schon hochgeladenen Videos nachtraeglich ueber Studios Bearbeiten-Seite (keine
    neue Datei, nur das Sichtbarkeits-Feld). Selektoren stammen aus den am 25./28.09.2026 gegen die echte
    Studio-Seite verifizierten Skripten _work/youtube_upload/set_public.py und set_private.py (Screenshots
    pub1-3.png/priv1-4.png), mit denen die Fairford-Folge am 06.10.2026 von Hand oeffentlich gestellt wurde."""
    from playwright.sync_api import sync_playwright

    visibility = visibility.upper()
    shots = Path(debug_dir) if debug_dir else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
        page = context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        try:
            page.goto(f"https://studio.youtube.com/video/{video_id}/edit?hl=en", wait_until="domcontentloaded")
            page.wait_for_selector("#title-textarea #textbox", state="attached")
            auswahl = page.locator("ytcp-video-metadata-visibility #select-button, #visibility-text, "
                                   "ytcp-icon-button.ytcp-video-metadata-visibility").first
            auswahl.wait_for(state="visible")
            auswahl.click()
            page.wait_for_selector(f'tp-yt-paper-radio-button[name="{visibility}"]', state="attached")
            if shots:
                page.screenshot(path=str(shots / "visibility_01_dialog.png"))
            _click_radio(page, visibility)
            teilspeichern = page.locator("#save-button").first
            teilspeichern.wait_for(state="visible")
            teilspeichern.click()
            page.wait_for_timeout(3000)
            haupt = page.locator("#save").first
            if haupt.count() and haupt.get_attribute("aria-disabled") != "true":
                haupt.click()
                page.wait_for_timeout(3000)
            if shots:
                page.screenshot(path=str(shots / "visibility_02_gespeichert.png"))
            if log:
                log(f"Sichtbarkeit auf {visibility} nachgezogen (Studio-Bearbeiten-Seite, Video {video_id})")
        finally:
            context.close()


def oeffentlich_pruefen(video_id: str, minuten: float = 30, log=None) -> bool:
    """Unabhaengige Kontrolle von aussen: oEmbed liefert nur fuer oeffentliche/nicht gelistete Videos Daten."""
    import time
    import httpx
    ende = time.time() + minuten * 60
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    while True:
        try:
            r = httpx.get(url, timeout=30)
            if r.status_code == 200:
                if log:
                    log(f"oEmbed bestätigt: {video_id} ist öffentlich abrufbar ({r.json().get('title', '')[:80]})")
                return True
            if log:
                log(f"oEmbed {r.status_code} - noch nicht öffentlich abrufbar")
        except Exception as e:
            if log:
                log(f"oEmbed-Abfrage fehlgeschlagen: {e}")
        if time.time() > ende:
            return False
        time.sleep(30)


def _wizard(page, video_path: str, meta: dict, thumb_path, visibility: str, log, shot, on_video_id,
            timeout_min: float) -> dict:
    """Gemeinsamer Upload-Assistent fuer Shorts-Jobs (run) und Weltlage-Folgen (upload_datei)."""
    _open_upload_page(page)
    if f"/channel/{NEWS_YOUTUBE_CHANNEL_ID}" not in page.url:
        raise RuntimeError(f"Studio opened a different channel than {NEWS_YOUTUBE_CHANNEL_ID} "
                           f"(url: {page.url[:100]}) - not uploading. Is the profile still signed in?")
    page.set_input_files("input[type=file]", video_path)
    on_video_id(None)                                   # ab hier kein blinder Neuversuch mehr
    log(f"Datei übergeben: {video_path}")
    page.wait_for_selector("#title-textarea #textbox")
    video_id = _video_id_from_dialog(page)
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
    language. Wartet auf 100 Prozent Transfer, Verarbeitungsstart und Studios Bestaetigung; bei oeffentlich
    zusaetzlich auf die oEmbed-Kontrolle von aussen. Protokoll Zeile fuer Zeile in log_path.
    Rueckgabe: video_id, transfer, bestaetigung, thumbnail, oeffentlich_bestaetigt."""
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

    zustand = {"video_id": None}

    def shot(name):
        if shots:
            try:
                page.screenshot(path=str(shots / f"upload_{name}.png"))
            except Exception:
                pass

    with sync_playwright() as p:
        context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
        page = context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        try:
            ergebnis = _wizard(page, str(video_path), meta, thumb_path, visibility, log, shot,
                               lambda vid: zustand.update(video_id=vid) if vid else None, timeout_min)
        except Exception as e:
            shot("fehler")
            log(f"FEHLER: {e}")
            if zustand["video_id"]:
                raise UploadHaltedForReview(f"Upload {zustand['video_id']} nach Dateiübergabe fehlgeschlagen - "
                                            f"in Studio prüfen, nicht blind wiederholen: {e}") from e
            raise
        finally:
            context.close()
    ergebnis["oeffentlich_bestaetigt"] = None
    if visibility != "PRIVATE":
        ergebnis["oeffentlich_bestaetigt"] = oeffentlich_pruefen(ergebnis["video_id"], pruef_minuten, log)
    if braucht_nachzug(ergebnis, visibility):
        log("Noch nicht öffentlich bestätigt - ziehe die Sichtbarkeit über Studios Bearbeiten-Seite nach")
        try:
            visibility_setzen(ergebnis["video_id"], visibility, log, debug_dir)
        except Exception as e:
            log(f"Nachziehen der Sichtbarkeit fehlgeschlagen: {e}")
            ergebnis["nachzug_fehler"] = str(e)[:500]
        else:
            ergebnis["nachgezogen"] = True
            ergebnis["oeffentlich_bestaetigt"] = oeffentlich_pruefen(ergebnis["video_id"], min(pruef_minuten, 10), log)
    log(f"FERTIG: {ergebnis}")
    return ergebnis


def _launch(p, headless: bool):
    """Persistent context on a real installed browser so Google's sign-in accepts it."""
    return p.chromium.launch_persistent_context(
        str(PLAYWRIGHT_PROFILE_DIR), channel=NEWS_PLAYWRIGHT_CHANNEL, headless=headless,
        locale="en-US",
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )


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
    for _ in range(30):
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
            page.goto(f"https://studio.youtube.com/video/{video_id}/edit?hl=en", wait_until="domcontentloaded")
            page.wait_for_selector("#title-textarea #textbox", state="attached")
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
            page.goto(f"https://studio.youtube.com/video/{video_id}/edit?hl=en", wait_until="domcontentloaded")
            page.wait_for_selector("#title-textarea #textbox", state="attached")
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


def set_thumbnail(video_id: str, thumb_path: str, debug_dir: str | None = None) -> None:
    """Sets the custom thumbnail of an already-published video via Studio's edit page (the
    video exists already, unlike run() which uploads a new one). Reuses the same signed-in
    profile. debug_dir, if given, gets a screenshot after each step for troubleshooting."""
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    thumb_path = Path(thumb_path)
    if not thumb_path.exists():
        raise FileNotFoundError(thumb_path)
    shots = Path(debug_dir) if debug_dir else None

    with sync_playwright() as p:
        context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
        page = context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        try:
            page.goto(f"https://studio.youtube.com/video/{video_id}/edit?hl=en", wait_until="domcontentloaded")
            page.wait_for_selector("#file-loader", state="attached")
            if shots:
                page.screenshot(path=str(shots / "01_edit_page.png"))
            page.set_input_files("#file-loader", str(thumb_path))
            page.wait_for_timeout(3000)
            if shots:
                page.screenshot(path=str(shots / "02_after_file_set.png"), full_page=True)
            save = page.locator("ytcp-button#save").first
            save.wait_for(state="visible")
            save.click()
            page.wait_for_timeout(3000)
            if shots:
                page.screenshot(path=str(shots / "03_after_save.png"), full_page=True)
        finally:
            context.close()


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
    else:
        run(sys.argv[1])
