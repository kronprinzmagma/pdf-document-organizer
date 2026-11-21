"""
Privacy-Gate: Tests fuer das Kernversprechen von dok-namer.

Rohe Personendaten verlassen die Maschine nie. Die Tests pruefen das am
Ausgang: Ein aufzeichnender Fake-Client ersetzt die Anthropic-API, und jede
Assertion schaut auf das, was tatsaechlich an die Cloud gegangen waere.
Keine API-Calls, kein ANTHROPIC_API_KEY, kein Ollama erforderlich.

Alle Personendaten hier sind synthetisch (gleiche Werte wie in
generate_test_pdfs.py bzw. test_dok_namer.py).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import dok_namer

canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")

# Synthetische Personendaten, die im Cloud-Payload nie auftauchen duerfen.
RAW_PII = {
    "Mustermann": "Empfaengername ueber der Adresse",
    "Bahnhofstrasse": "Strassenadresse",
    "756.4821.9034.17": "AHV-Nummer",  # synthetischer Testwert, gitleaks:allow
    "CH93 0076 2011 6238 5295 7": "IBAN",  # synthetischer Testwert, gitleaks:allow
    "079 456 78 90": "CH-Mobilnummer",  # synthetischer Testwert, gitleaks:allow
    "max.muster@example.ch": "E-Mail",
    "1'234.50": "Betrag",
    "Weber": "Behandlername nach Titel",
}

LETTER_LINES = [
    "EKZ Elektrizitaetswerke des Kantons Zuerich",
    "Max Mustermann",
    "Bahnhofstrasse 12, 8001 Zuerich",
    "Zuerich, 15. November 2025",
    "Stromrechnung November 2025",
    "Sehr geehrter Herr Mustermann",
    "AHV-Nummer: 756.4821.9034.17",  # synthetischer Testwert, gitleaks:allow
    "Konto: CH93 0076 2011 6238 5295 7",  # synthetischer Testwert, gitleaks:allow
    "Rueckfragen: 079 456 78 90 oder max.muster@example.ch",  # synthetischer Testwert, gitleaks:allow
    "Total: CHF 1'234.50",
    "Vertrauensarzt: Dr. med. Anna Weber",
]


class RecordingClient:
    """Fake-Anthropic-Client: zeichnet jeden Request auf, statt ihn zu senden."""

    def __init__(self):
        self.calls: list[dict] = []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        info = dok_namer.DocumentInfo(sender="EKZ", content="Stromrechnung", date="20251115", confidence="high")
        usage = type("Usage", (), {"input_tokens": 300, "output_tokens": 40})()
        return type("Response", (), {"parsed_output": info, "usage": usage})()

    def payload(self) -> str:
        """Alles, was an die Cloud gegangen waere, als ein durchsuchbarer String."""
        return json.dumps([c["messages"] for c in self.calls], ensure_ascii=False)


def _write_pdf(path: Path, lines: list[str]) -> Path:
    c = canvas_mod.Canvas(str(path))
    y = 800
    for line in lines:
        c.drawString(60, y, line)
        y -= 18
    if not lines:
        c.rect(60, 600, 200, 100)  # Seite ohne Textebene (wie ein Scan ohne OCR)
    c.save()
    return path


def _dirs(tmp_path: Path) -> dict[str, Path]:
    dirs = {name: tmp_path / name for name in ("done", "unrecognized", "review", "error")}
    for d in dirs.values():
        d.mkdir()
    return dirs


def _process(tmp_path, pdf, engine, client, blocklist=()):
    dirs = _dirs(tmp_path)
    status = dok_namer.process_file(
        client, pdf, dirs["done"], dirs["unrecognized"], dirs["review"], dirs["error"],
        engine=engine, auto=True, lines=[], blocklist=blocklist,
    )[0]
    return status, dirs


def _assert_no_raw_pii(payload: str) -> None:
    leaks = [label for value, label in RAW_PII.items() if value in payload]
    assert not leaks, f"Rohdaten im Cloud-Payload: {leaks}"


# --- Engine claude: Regex-Redaktion vor jedem Cloud-Call ---

def test_claude_engine_sendet_nur_redaktierten_text(tmp_path):
    src = tmp_path / "quelle"; src.mkdir()
    pdf = _write_pdf(src / "scan.pdf", LETTER_LINES)
    client = RecordingClient()

    status, _ = _process(tmp_path, pdf, "claude", client)

    assert status == "renamed"
    assert len(client.calls) == 1
    payload = client.payload()
    _assert_no_raw_pii(payload)
    for placeholder in ("[NAME]", "[ADRESSE]", "[AHV]", "[IBAN]", "[TELEFON]", "[EMAIL]", "[BETRAG]", "[BEHANDLER]"):
        assert placeholder in payload, f"{placeholder} fehlt im Payload"
    # Absender und Datum bleiben erhalten, sonst taugt die Extraktion nichts
    assert "EKZ" in payload
    assert "15. November 2025" in payload


def test_blocklist_name_erreicht_die_cloud_nie(tmp_path):
    # Ein Name ohne Anrede und ohne Adresse darunter faellt durch die Regex;
    # dafuer gibt es redact-names.txt.
    src = tmp_path / "quelle"; src.mkdir()
    pdf = _write_pdf(src / "scan.pdf", ["Swisscom Rechnung", "Vertragspartnerin: Kasimira Testfrau", "1. Oktober 2025"])
    client = RecordingClient()

    _process(tmp_path, pdf, "claude", client, blocklist=("kasimira testfrau",))

    payload = client.payload()
    assert "Testfrau" not in payload
    assert "Kasimira" not in payload
    assert "[NAME]" in payload


def test_scan_pdf_ohne_text_geht_nie_in_die_cloud(tmp_path):
    # Ohne Textebene kann nichts redaktiert werden → kein Upload, sondern review/
    src = tmp_path / "quelle"; src.mkdir()
    pdf = _write_pdf(src / "scan.pdf", [])
    client = RecordingClient()

    status, dirs = _process(tmp_path, pdf, "claude", client)

    assert status == "review"
    assert client.calls == []
    assert (dirs["review"] / "scan.pdf").exists()


# --- Engine hybrid: llama3.2 anonymisiert, Regex sichert ab ---

def _fake_llama(result_text: str | None, counts: dict[str, int], truncated: bool = False):
    def fake(text):
        return (text if result_text is None else result_text), dict(counts), truncated
    return fake


def test_hybrid_wirkungslose_llama_anonymisierung_blockiert_cloud(tmp_path, monkeypatch):
    # llama gibt den Rohtext unveraendert zurueck → No-op-Check → review/.
    # Ohne AHV und Mobilnummer, damit nicht erst verify_with_regex greift.
    src = tmp_path / "quelle"; src.mkdir()
    lines = [ln for ln in LETTER_LINES if "AHV" not in ln and "079" not in ln]
    pdf = _write_pdf(src / "scan.pdf", lines)
    monkeypatch.setattr(dok_namer, "anonymize_with_llama", _fake_llama(None, {}))
    client = RecordingClient()

    status, dirs = _process(tmp_path, pdf, "hybrid", client)

    assert status == "review"
    assert client.calls == []
    assert (dirs["review"] / "scan.pdf").exists()


def test_hybrid_abgeschnittener_llama_output_blockiert_cloud(tmp_path, monkeypatch):
    src = tmp_path / "quelle"; src.mkdir()
    pdf = _write_pdf(src / "scan.pdf", LETTER_LINES)
    monkeypatch.setattr(dok_namer, "anonymize_with_llama", _fake_llama("[NAME] [ADRESSE] ...", {"[NAME]": 1}, truncated=True))
    client = RecordingClient()

    status, _ = _process(tmp_path, pdf, "hybrid", client)

    assert status == "review"
    assert client.calls == []


def test_hybrid_regex_faengt_was_llama_uebersieht(tmp_path, monkeypatch):
    # llama setzt Platzhalter fuer Namen, laesst aber AHV, IBAN, Telefon stehen.
    # Die Regex-Redaktion nach llama (Defense-in-Depth) muss das abfangen.
    src = tmp_path / "quelle"; src.mkdir()
    pdf = _write_pdf(src / "scan.pdf", LETTER_LINES)
    half_anonymized = "\n".join(LETTER_LINES).replace("Max Mustermann", "[NAME]").replace("Herr Mustermann", "[NAME]")
    monkeypatch.setattr(dok_namer, "anonymize_with_llama", _fake_llama(half_anonymized, {"[NAME]": 2}))
    client = RecordingClient()

    status, _ = _process(tmp_path, pdf, "hybrid", client)

    assert status == "renamed"
    assert len(client.calls) == 1
    _assert_no_raw_pii(client.payload())


def test_hybrid_restliche_ahv_nach_redaktion_stoppt_vor_der_cloud(tmp_path, monkeypatch):
    # Letzte Sperre: Faellt auch die Regex-Redaktion aus, findet verify_with_regex
    # die AHV-Nummer und die Datei geht nach review/, ohne Cloud-Call.
    src = tmp_path / "quelle"; src.mkdir()
    pdf = _write_pdf(src / "scan.pdf", LETTER_LINES)
    monkeypatch.setattr(dok_namer, "anonymize_with_llama",
                        _fake_llama("[NAME]\nAHV-Nummer: 756.4821.9034.17", {"[NAME]": 1}))  # synthetisch, gitleaks:allow
    monkeypatch.setattr(dok_namer, "redact", lambda text, blocklist=(): (text, {}))
    client = RecordingClient()

    status, dirs = _process(tmp_path, pdf, "hybrid", client)

    assert status == "review"
    assert client.calls == []
    assert (dirs["review"] / "scan.pdf").exists()


# --- Eval-Modus: Claude nur auf als cloud_safe markierten Korpora ---

def test_eval_ruft_claude_bei_nicht_cloud_safe_korpus_nie_auf(tmp_path, monkeypatch, capsys):
    (tmp_path / "fall.txt").write_text("Steueramt Zuerich\nSteuerrechnung\n1. Maerz 2025", encoding="utf-8")
    (tmp_path / "expectations.json").write_text(json.dumps({
        "cloud_safe": False,
        "cases": [{"file": "fall.txt", "sender_any": ["Steueramt"], "content_any": ["Steuerrechnung"]}],
    }), encoding="utf-8")

    def no_client():
        raise AssertionError("Claude-Client darf fuer diesen Korpus nicht erzeugt werden")

    monkeypatch.setattr(dok_namer, "create_anthropic_client", no_client)

    dok_namer.run_eval(tmp_path, models=[], include_claude=True)

    assert "not marked cloud_safe" in capsys.readouterr().out
