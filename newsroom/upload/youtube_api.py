"""YouTube Data API v3. Seit 21.10.2026 (Task 20261021-105909-286b) im Alltag genutzt fuer thumbnails.set
(Weltlage-Shorts-Thumbnails klickfrei, siehe thumbnail_setzen/verfuegbar, Einrichtung docs/youtube-data-api.md).

Primary uploader: YouTube Data API v3, resumable upload. Only usable once the OAuth
consent screen is verified AND the API compliance audit has passed (see newsroom/README.md
and the plan) — until then, videos uploaded through this path are forced private by
Google regardless of what's requested here, so `NEWS_UPLOAD_METHOD=playwright` should stay
the default. This module is fully wired and ready for the moment both reviews clear.
"""
import http.client
import json
import logging
import random
import time
from datetime import datetime, timezone

from config.settings import DATA_DIR, YOUTUBE_CLIENT_SECRET_PATH, YOUTUBE_TOKEN_PATH
from orchestrator import state_store
from upload.metadata import build as build_metadata

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
# Errors worth retrying a resumable-upload chunk on, per Google's own sample code.
_RETRIABLE_EXCEPTIONS = (http.client.NotConnected, http.client.IncompleteRead, http.client.ImproperConnectionState,
                          http.client.CannotSendRequest, http.client.CannotSendHeader, http.client.ResponseNotReady,
                          http.client.BadStatusLine, ConnectionError, TimeoutError)
_RETRIABLE_STATUS_CODES = (500, 502, 503, 504)
_MAX_RETRIES = 8


def verfuegbar() -> bool:
    """True, wenn die einmalige Einrichtung da ist (client_secret.json + youtube_token.json in secrets/) und der Weg
    nicht per NEWS_YOUTUBE_API_THUMBNAIL=0 abgeschaltet wurde. Entscheidet im Weltlage-Shorts-Takt, ob ein Thumbnail
    klickfrei ueber thumbnails.set gesetzt wird (seit 21.10.2026) statt ueber YouTube Studio/Playwright."""
    import os
    if os.environ.get("NEWS_YOUTUBE_API_THUMBNAIL", "1").strip() == "0":
        return False
    return YOUTUBE_CLIENT_SECRET_PATH.exists() and YOUTUBE_TOKEN_PATH.exists()


EINRICHTEN_HINWEIS = ("YouTube Data API nicht eingerichtet - einmalig von rexemre: "
                      "`.venv\\Scripts\\python -m upload.youtube_api --einrichten` (siehe docs/youtube-data-api.md)")


def get_authenticated_service(interaktiv: bool = True):
    """Authentifizierter YouTube-Data-API-Client. interaktiv=False (Takt/Wache, ohne Mensch): oeffnet nie einen
    Browser, sondern wirft RuntimeError mit Einrichtungs-Hinweis, wenn kein gueltiges/erneuerbares Token da ist."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not YOUTUBE_CLIENT_SECRET_PATH.exists():
        raise RuntimeError(
            f"{YOUTUBE_CLIENT_SECRET_PATH} not found - download it from your Google Cloud "
            f"OAuth Client (Desktop app type) and put it there. {EINRICHTEN_HINWEIS}"
        )
    creds = None
    if YOUTUBE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:   # noqa: BLE001 - z.B. Token widerrufen / Testmodus-Token nach 7 Tagen abgelaufen
                if not interaktiv:
                    raise RuntimeError(f"YouTube-Token nicht erneuerbar ({type(e).__name__}: {str(e)[:120]}). "
                                       f"{EINRICHTEN_HINWEIS}") from e
                creds = None
        if not creds or not creds.valid:
            if not interaktiv:
                raise RuntimeError(EINRICHTEN_HINWEIS)
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(str(YOUTUBE_CLIENT_SECRET_PATH), SCOPES)
            creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        YOUTUBE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def thumbnail_setzen(video_id: str, bild_pfad, youtube=None) -> dict:
    """Setzt das eigene Thumbnail eines Videos/Shorts ueber thumbnails.set (50 Quota-Einheiten, Tageslimit 10'000;
    funktioniert fuer schon veroeffentlichte Videos auch mit unverifizierter App - die "privat bis zur Pruefung"-
    Einschraenkung gilt nur fuer videos.insert). Rueckgabe {"gespeichert": True, "studio_bestaetigt": True,
    "dauer_s", "hinweis", "antwort"}; Fehler werden geworfen (HttpError, RuntimeError bei fehlender Einrichtung)."""
    from googleapiclient.http import MediaFileUpload

    bild_pfad = Path(bild_pfad)
    if not bild_pfad.exists():
        raise FileNotFoundError(bild_pfad)
    youtube = youtube or get_authenticated_service(interaktiv=False)
    t0 = time.time()
    antwort = youtube.thumbnails().set(
        videoId=video_id, media_body=MediaFileUpload(str(bild_pfad), mimetype="image/jpeg", resumable=False)
    ).execute()
    logger.info("thumbnails.set %s: %s", video_id, antwort)
    return {"gespeichert": True, "studio_bestaetigt": True, "dauer_s": round(time.time() - t0, 1),
            "hinweis": "Data API thumbnails.set", "antwort": antwort}


def status(youtube=None) -> dict:
    """Einrichtungsstand ohne Nebenwirkung: Dateien da? Token erneuerbar? Welcher Kanal (channels.list mine=True,
    1 Quota-Einheit)."""
    st = {"client_secret": YOUTUBE_CLIENT_SECRET_PATH.exists(), "token": YOUTUBE_TOKEN_PATH.exists(),
          "verfuegbar": verfuegbar(), "kanal": None, "fehler": None}
    if not st["verfuegbar"]:
        return st
    try:
        youtube = youtube or get_authenticated_service(interaktiv=False)
        r = youtube.channels().list(part="snippet", mine=True).execute()
        items = r.get("items") or []
        if items:
            st["kanal"] = {"id": items[0]["id"], "titel": items[0]["snippet"]["title"]}
    except Exception as e:   # noqa: BLE001
        st["fehler"] = f"{type(e).__name__}: {str(e)[:200]}"
    return st


def einrichten() -> dict:
    """Einmalige Einrichtung durch rexemre (interaktiv): oeffnet den Browser fuer die Google-Zustimmung, speichert das
    Token (secrets/youtube_token.json) und zeigt, welcher Kanal autorisiert wurde. Beim Zustimmungsdialog den Kanal
    «Weltlage Kompakt» waehlen, falls Google nach dem Konto/Kanal fragt."""
    if YOUTUBE_TOKEN_PATH.exists():
        YOUTUBE_TOKEN_PATH.unlink()
    youtube = get_authenticated_service(interaktiv=True)
    st = status(youtube)
    print(json.dumps(st, ensure_ascii=False))
    return st


def upload(video_path: str, meta: dict) -> str:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    youtube = get_authenticated_service()
    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": meta["category_id"],
            "defaultLanguage": meta["language"],
            "defaultAudioLanguage": meta["language"],
        },
        "status": {
            "privacyStatus": meta["privacy_status"],
            "selfDeclaredMadeForKids": meta["made_for_kids"],
            "containsSyntheticMedia": meta["contains_synthetic_media"],
        },
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response, retry = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
        except HttpError as e:
            if e.resp.status in _RETRIABLE_STATUS_CODES and retry < _MAX_RETRIES:
                retry += 1
                time.sleep(min(2 ** retry + random.random(), 60))
                continue
            raise
        except _RETRIABLE_EXCEPTIONS:
            if retry < _MAX_RETRIES:
                retry += 1
                time.sleep(min(2 ** retry + random.random(), 60))
                continue
            raise

    return response["id"]


def run(job_id: str) -> str:
    meta = build_metadata(job_id)
    video_path = str(DATA_DIR / "video" / f"{job_id}.mp4")
    thumb_path = DATA_DIR / "thumbs" / f"{job_id}.jpg"

    video_id = upload(video_path, meta)

    if thumb_path.exists():
        youtube = get_authenticated_service()
        youtube.thumbnails().set(videoId=video_id, media_body=str(thumb_path)).execute()

    state_store.update_job(job_id, status="published", video_id=video_id, upload_method="api",
                            published_at=datetime.now(timezone.utc).isoformat())
    logger.info("published %s via API -> https://youtube.com/watch?v=%s", job_id, video_id)
    return video_id


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if "--einrichten" in sys.argv:
        einrichten()
    elif "--status" in sys.argv:
        print(json.dumps(status(), ensure_ascii=False))
    elif "--thumbnail" in sys.argv:
        idx = sys.argv.index("--thumbnail")
        res = thumbnail_setzen(sys.argv[idx + 1], sys.argv[idx + 2])
        print(json.dumps({k: v for k, v in res.items() if k != "antwort"}, ensure_ascii=False))
    else:
        run(sys.argv[1])
