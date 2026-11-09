"""Leere Studio-Sprachliste in echtem Chromium: danach muss «Weiter» klickbar sein (Nachpruefung 09.11.2026)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from upload import youtube_playwright as yp

_SEITE = """
<script>
class Liste extends HTMLElement {
  get opened() { return this.hasAttribute('opened'); }
  open() { this.setAttribute('opened', ''); this.style.display = 'block'; }
  close() { this.removeAttribute('opened'); this.style.display = 'none'; }
}
customElements.define('tp-yt-iron-dropdown', Liste);
</script>
<div id="language-subtitles-cc">
  %s
  <ytcp-form-language-input>Auswählen</ytcp-form-language-input>
  <ytcp-dropdown-trigger><button onclick="event.stopPropagation(); liste.open()">Sprache</button></ytcp-dropdown-trigger>
</div>
<button id="next-button" onclick="document.title='weiter'" style="position:fixed;top:300px;left:100px">Weiter</button>
<tp-yt-iron-dropdown id="liste" style="display:none;position:fixed;inset:150px 0 0 0;background:#333"></tp-yt-iron-dropdown>
<script>
document.addEventListener('mousedown', e => { if (!liste.contains(e.target)) liste.close(); });
</script>
"""
_LABEL = '<div class="section-label-with-description">Sprache und Untertitel</div>'


class LeereListeImBrowserTest(unittest.TestCase):
    def _lauf(self, label):
        meldungen = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                seite = browser.new_page(viewport={"width": 800, "height": 600})
                seite.set_default_timeout(3000)
                seite.set_content(_SEITE % label)
                with mock.patch.object(yp, "SPRACH_WARTEN_MS", 400):
                    yp._set_language(seite, "de", meldungen.append)
                offen = seite.evaluate("() => document.querySelector('#liste').opened")
                seite.locator("#next-button").first.click(timeout=1500)
                self.assertEqual(seite.title(), "weiter")
            finally:
                browser.close()
        self.assertFalse(offen)
        self.assertEqual(len(meldungen), 1)

    def test_liste_schliesst_mit_bekanntem_label(self):
        self._lauf(_LABEL)

    def test_liste_schliesst_auch_ohne_label(self):
        # Der Selektor des Labels ist nie gegen das echte Studio geprueft worden
        self._lauf("")


if __name__ == "__main__":
    unittest.main()
