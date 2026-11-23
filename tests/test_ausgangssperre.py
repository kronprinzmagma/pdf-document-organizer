"""Ausgangssperre: letzte harte Pruefung vor jedem Claude-Aufruf.

Alle Werte sind synthetisch (Beispiel-AHV, Beispiel-IBAN aus Bankdokumentationen,
Testkarte 4111 ..., erfundene Adressen). Werte, die gitleaks oder den
Leak-Verifier des Public-Syncs ausloesen koennten, werden zur Laufzeit
zusammengesetzt. Keine API-Calls, kein Ollama, keine echten Dokumente.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
ROOT_VERBOTSLISTE = ROOT / "ausgangssperre.local.yaml"
sys.path.insert(0, str(ROOT))

import ausgangssperre  # noqa: E402
import dok_namer  # noqa: E402
from ausgangssperre import (  # noqa: E402
    ART_NICHT_TEXT,
    AusgangGesperrt,
    finde_im_text,
    lade_verbotsliste,
    pruefe_nachrichten,
    sperre_pruefen,
)

AHV = "756." + "1234.5678.90"
IBAN = "CH93 0076 " + "2011 6238 5295 7"
IBAN_KOMPAKT = IBAN.replace(" ", "")
IBAN_FALSCHE_PRUEFZIFFER = IBAN[:-1] + "8"
KARTE = "4111 1111 1111 1111"
ANTHROPIC_KEY = "sk-" + "ant-" + "api03-" + "Q" * 40


@pytest.fixture(autouse=True)
def _keine_lokale_liste(monkeypatch, tmp_path_factory):
    """Eine echte lokale Verbotsliste darf die Tests nie beeinflussen.

    Die Variable zeigt auf eine leere Liste: eine fehlende Datei hinter der
    Variable bricht ab (fail closed).
    """
    leer = tmp_path_factory.mktemp("ausgangssperre") / "leere-liste.yaml"
    leer.write_text("verboten: []\n", encoding="utf-8")
    monkeypatch.setenv(ausgangssperre.VERBOTSLISTE_ENV, str(leer))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# Erkennung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "art"),
    [
        (f"Versicherungsnummer {AHV}", "AHV-Nummer"),
        ("AHV " + AHV.replace(".", " "), "AHV-Nummer"),
        ("AHV " + AHV.replace(".", ""), "AHV-Nummer"),
        (f"Konto {IBAN}", "IBAN"),
        (f"Konto {IBAN_KOMPAKT}", "IBAN"),
        (f"Karte {KARTE}", "Kreditkartennummer"),
        ("Geburtsdatum: 01.01.1985", "Geburtsdatum"),
        ("Versicherte Person, geb. 3.4.1980", "Geburtsdatum"),
        ("geboren am 3. April 1980", "Geburtsdatum"),
        ("Date of Birth: 01 January 1985", "Geburtsdatum"),
        (f"key={ANTHROPIC_KEY}", "Secret/API-Key"),
        ("-----BEGIN RSA PRIVATE KEY-----", "Secret/API-Key"),
    ],
)
def test_erkennt_geschuetzte_daten(text, art):
    assert art in finde_im_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "Steueramt Musterstadt, Steuerrechnung 2025, Zahlbar bis 30.11.2025",
        "Betrag [BETRAG], Konto [IBAN], AHV [AHV], [NAME], [ADRESSE]",
        f"Ungueltige IBAN {IBAN_FALSCHE_PRUEFZIFFER}",
        "Rechnungsnummer 4111 1111 1111 1112",
        "Kundennummer 12345678, Vertrag 2024-0815",
        "Musterstadt, 15. November 2025",
        "Leistungen vom 01.03.2025 bis 31.03.2025",
    ],
)
def test_keine_fehlalarme_auf_geschwaerztem_brieftext(text):
    assert finde_im_text(text) == []


def test_eigener_api_key_aus_umgebung(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "eigener-schluessel-ohne-bekanntes-format-123")
    assert finde_im_text("x eigener-schluessel-ohne-bekanntes-format-123 y") == ["Secret/API-Key"]


# ---------------------------------------------------------------------------
# Verbotsliste (gleiches Format wie cv-tailor)
# ---------------------------------------------------------------------------

def _liste(tmp_path, text: str) -> Path:
    p = tmp_path / "ausgangssperre.local.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_verbotsliste_tolerant_gegen_trenner_und_schreibweise(tmp_path):
    liste = lade_verbotsliste(_liste(tmp_path, (
        "verboten:\n"
        "  - { wert: '+41 44 555 01 23', art: Telefon privat }\n"
        "  - { wert: 'Musterweg 7', art: Privatadresse }\n"
        "  - Geheimprojekt Kolibri\n"
    )))
    assert finde_im_text("Tel. +41-44-555-01-23", liste) == ["Verbotsliste: Telefon privat"]
    assert finde_im_text("wohnhaft MUSTERWEG   7", liste) == ["Verbotsliste: Privatadresse"]
    assert finde_im_text("Betreff geheimprojekt kolibri", liste) == ["Verbotsliste"]
    assert finde_im_text("Musterweg 70", liste) == []


def test_erlaubt_unterdrueckt_bekannten_fehlalarm(tmp_path):
    liste = lade_verbotsliste(_liste(tmp_path, f"erlaubt:\n  - '{IBAN}'\n"))
    assert finde_im_text(f"Spendenkonto: {IBAN}", liste) == []


def test_kaputte_verbotsliste_bricht_ab(tmp_path):
    with pytest.raises(ValueError):
        lade_verbotsliste(_liste(tmp_path, "verboten: [unvollstaendig"))
    with pytest.raises(ValueError):
        lade_verbotsliste(_liste(tmp_path, "verboten:\n  - abc\n"))
    with pytest.raises(ValueError):
        lade_verbotsliste(_liste(tmp_path, "- nur eine Liste\n"))


def test_kaputte_verbotsliste_beendet_den_lauf_vor_dem_client(monkeypatch, tmp_path):
    p = _liste(tmp_path, "verboten: [unvollstaendig")
    monkeypatch.setenv(ausgangssperre.VERBOTSLISTE_ENV, str(p))
    with pytest.raises(SystemExit):
        dok_namer.pruefe_verbotsliste_oder_beende()


def test_fehlende_verbotsliste_heisst_nur_feste_muster(tmp_path):
    assert lade_verbotsliste(tmp_path / "gibt_es_nicht.yaml").eintraege == ()


def test_verbotsliste_ueber_umgebungsvariable(monkeypatch, tmp_path):
    p = _liste(tmp_path, "verboten:\n  - Kolibri-Intern\n")
    monkeypatch.setenv(ausgangssperre.VERBOTSLISTE_ENV, str(p))
    assert pruefe_nachrichten([{"role": "user", "content": "kolibri-intern"}])


def test_beispieldatei_ist_gueltig():
    liste = lade_verbotsliste(ROOT / "ausgangssperre.example.yaml")
    assert liste.eintraege, "Beispieldatei soll mindestens einen Eintrag zeigen"


def test_lokale_verbotsliste_ist_gitignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "ausgangssperre.local.yaml" in gitignore.splitlines()


def test_public_sync_kennt_die_neuen_dateien():
    spec = importlib.util.spec_from_file_location("sync_to_public", ROOT / "scripts" / "sync_to_public.py")
    if spec is None or not (ROOT / "scripts" / "sync_to_public.py").exists():
        pytest.skip("Sync-Skript nur im privaten Repo")
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    for datei in ("ausgangssperre.py", "ausgangssperre.example.yaml", "tests/test_ausgangssperre.py"):
        assert datei in sync.WHITELIST
    assert "ausgangssperre.local.yaml" in sync.FORBIDDEN_PATHS
    assert "ausgangssperre.local.yaml" in sync.GITIGNORE_CONTENT


# ---------------------------------------------------------------------------
# Sperre und Fehlermeldung
# ---------------------------------------------------------------------------

def test_fehlermeldung_nennt_art_nie_den_wert():
    messages = [{"role": "user", "content": [{"type": "text", "text": f"AHV {AHV}, Konto {IBAN}"}]}]
    with pytest.raises(AusgangGesperrt) as info:
        sperre_pruefen(messages)
    meldung = str(info.value)
    assert "AHV-Nummer" in meldung and "IBAN" in meldung and "Nachricht 0 (user)" in meldung
    assert AHV not in meldung and "1234" not in meldung and "0076" not in meldung


@pytest.mark.parametrize(
    "block",
    [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "AAAA"}},
        {"type": "scan", "path": "/tmp/scan.pdf"},
    ],
)
def test_nicht_text_inhalt_geht_nie_raus(block):
    """Bilder/PDFs kann die Sperre nicht lesen: sie werden gar nicht durchgelassen."""
    funde = pruefe_nachrichten([{"role": "user", "content": [block, {"type": "text", "text": "ok"}]}])
    assert [f.art for f in funde] == [ART_NICHT_TEXT]


def test_classify_error_meldet_nur_arten_und_wiederholt_nicht():
    exc = AusgangGesperrt([ausgangssperre.Fund(art="AHV-Nummer", nachricht=0, rolle="user")])
    assert dok_namer.classify_error(exc) == "ausgangssperre:AHV-Nummer"
    assert not dok_namer.is_retryable_error(exc)


# ---------------------------------------------------------------------------
# Engpass analyze_claude: bei Fund wird nichts gesendet
# ---------------------------------------------------------------------------

class _AufzeichnenderClient:
    def __init__(self):
        self.aufrufe: list[dict] = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.aufrufe.append(kwargs)
        info = dok_namer.DocumentInfo(sender="Steueramt", content="Steuerrechnung", date="20251115", confidence="high")
        return SimpleNamespace(parsed_output=info, usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def test_analyze_claude_sendet_nichts_bei_fund():
    client = _AufzeichnenderClient()
    with pytest.raises(AusgangGesperrt):
        dok_namer.analyze_claude(client, {"type": "text", "text": f"Steuerrechnung, AHV {AHV}"})
    assert client.aufrufe == []


def test_analyze_claude_sendet_kein_bild():
    client = _AufzeichnenderClient()
    with pytest.raises(AusgangGesperrt):
        dok_namer.analyze_claude(client, {"type": "scan", "path": "/tmp/scan.pdf"})
    assert client.aufrufe == []


def test_analyze_claude_laesst_geschwaerzten_text_durch():
    client = _AufzeichnenderClient()
    info, _ = dok_namer.analyze_claude(client, {"type": "text", "text": "Steueramt, Steuerrechnung, AHV [AHV]"})
    assert info.sender == "Steueramt" and len(client.aufrufe) == 1


def test_versagte_schwaerzung_datei_bleibt_unbenannt_in_error(monkeypatch, tmp_path):
    """Simuliert eine Schwaerzung, die nichts tut: die Sperre faengt es, nichts geht raus."""
    quelle = tmp_path / "eingang"
    quelle.mkdir()
    pdf = quelle / "brief.pdf"
    pdf.write_bytes(b"%PDF-1.4 synthetisch")
    dirs = {name: tmp_path / name for name in ("done", "unrecognized", "review", "error")}
    for d in dirs.values():
        d.mkdir()
    monkeypatch.setattr(dok_namer, "extract_text", lambda _p: f"Steuerrechnung\nIBAN {IBAN}\n")
    monkeypatch.setattr(dok_namer, "redact", lambda text, blocklist=(): (text, {}))
    client = _AufzeichnenderClient()
    zeilen: list[str] = []

    status, _, _, name, _, _, grund, _ = dok_namer.process_file(
        client, pdf, dirs["done"], dirs["unrecognized"], dirs["review"], dirs["error"],
        engine="claude", auto=True, lines=zeilen,
    )

    assert client.aufrufe == []
    assert status == "skipped" and grund == "analyse:ausgangssperre:IBAN"
    assert (dirs["error"] / "brief.pdf").exists() and name == "brief.pdf"
    ausgabe = "\n".join(zeilen)
    assert "Ausgangssperre" in ausgabe and "IBAN" in ausgabe
    assert IBAN not in ausgabe and IBAN_KOMPAKT not in ausgabe and "0076" not in ausgabe


# ---------------------------------------------------------------------------
# Schwaerzung und Sperre passen zusammen
# ---------------------------------------------------------------------------

def test_schwaerzung_entfernt_alles_was_die_sperre_sucht():
    roh = (
        "Krankenkasse Beispiel\n"
        f"Versichertennummer {AHV}\n"
        "Geburtsdatum: 01.01.1985\n"
        f"Karte {KARTE}\n"
        f"Zahlbar auf {IBAN}\n"
        "Musterstadt, 15. November 2025\n"
    )
    assert set(finde_im_text(roh)) >= {"AHV-Nummer", "Geburtsdatum", "Kreditkartennummer", "IBAN"}
    geschwaerzt, counts = dok_namer.redact(roh)
    assert finde_im_text(geschwaerzt) == []
    assert counts.get("[GEBURTSDATUM]") == 1 and counts.get("[KARTE]") == 1
    assert "15. November 2025" in geschwaerzt  # Briefdatum bleibt fuer die Pruefung


# ---------------------------------------------------------------------------
# Einziger Engpass: kein Cloud-Aufruf ausserhalb von analyze_claude
# ---------------------------------------------------------------------------

_ANBIETER = {"anthropic", "openai", "litellm", "google", "mistralai", "cohere"}


def _python_dateien() -> list[Path]:
    dateien = [p for p in ROOT.glob("*.py")]
    for ordner in ("scripts", "tests"):
        if (ROOT / ordner).exists():
            dateien += list((ROOT / ordner).rglob("*.py"))
    return dateien


def _importe_mit_funktion(baum: ast.AST) -> list[tuple[str, str]]:
    """(modul, umgebende Funktion) fuer jeden Import im Baum."""
    out: list[tuple[str, str]] = []

    def besuche(knoten: ast.AST, funktion: str) -> None:
        for kind in ast.iter_child_nodes(knoten):
            name = kind.name if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)) else funktion
            if isinstance(kind, ast.Import):
                out.extend((a.name.split(".")[0], funktion) for a in kind.names)
            elif isinstance(kind, ast.ImportFrom) and kind.module and kind.level == 0:
                out.append((kind.module.split(".")[0], funktion))
            elif (
                isinstance(kind, ast.Call)
                and getattr(kind.func, "attr", getattr(kind.func, "id", "")) in {"import_module", "__import__"}
                and kind.args
                and isinstance(kind.args[0], ast.Constant)
                and isinstance(kind.args[0].value, str)
            ):
                out.append((kind.args[0].value.split(".")[0], funktion))
            besuche(kind, name)

    besuche(baum, "<modul>")
    return out


def test_anthropic_nur_in_create_anthropic_client():
    verstoesse = []
    for p in _python_dateien():
        rel = p.relative_to(ROOT).as_posix()
        for modul, funktion in _importe_mit_funktion(ast.parse(p.read_text(encoding="utf-8"))):
            if modul in _ANBIETER and not (rel == "dok_namer.py" and funktion == "create_anthropic_client"):
                verstoesse.append(f"{rel}:{funktion}: {modul}")
    assert not verstoesse, "Cloud-Clients nur ueber create_anthropic_client: " + "; ".join(verstoesse)


def test_messages_aufrufe_nur_in_analyze_claude():
    """Jeder Aufruf von <client>.messages.<x>(...) muss in analyze_claude stehen."""
    baum = ast.parse((ROOT / "dok_namer.py").read_text(encoding="utf-8"))
    gefunden: list[str] = []
    for funktion in ast.walk(baum):
        if not isinstance(funktion, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for knoten in ast.walk(funktion):
            if (
                isinstance(knoten, ast.Call)
                and isinstance(knoten.func, ast.Attribute)
                and isinstance(knoten.func.value, ast.Attribute)
                and knoten.func.value.attr == "messages"
            ):
                gefunden.append(funktion.name)
    assert gefunden and set(gefunden) == {"analyze_claude"}, gefunden
    for p in _python_dateien():
        if p.name in {"dok_namer.py", "test_ausgangssperre.py"}:
            continue
        assert ".messages.parse(" not in p.read_text(encoding="utf-8")
        assert ".messages.create(" not in p.read_text(encoding="utf-8")


def test_analyze_claude_prueft_vor_dem_senden():
    quelle = (ROOT / "dok_namer.py").read_text(encoding="utf-8")
    start = quelle.index("def analyze_claude(")
    ende = quelle.index("\ndef ", start + 1)
    funktion = quelle[start:ende]
    assert 0 < funktion.index("sperre_pruefen(messages)") < funktion.index("client.messages.parse(")


# ---------------------------------------------------------------------------
# Luecken aus dem Review 2026-11-23 (jeder Fall war mit dem alten Code gruen
# durchgelassen bzw. still ohne Liste weitergelaufen)
# ---------------------------------------------------------------------------

# Offizielle Beispiel-IBAN (DE) und Amex-Testkarte, zur Laufzeit zusammengesetzt.
IBAN_DE = "DE89 3704 " + "0044 0532 0130 00"
KARTE_AMEX = "3782 822463 " + "10005"
NBSP, SCHMALES_NBSP, NULLBREITE = " ", " ", "​"
VOLLBREIT = {c: c + 0xFEE0 for c in range(0x21, 0x7F)}


@pytest.mark.parametrize(
    ("text", "art"),
    [
        (f"Konto {IBAN} BIC UBSWCHZH", "IBAN"),
        (f"Konto {IBAN} 8000 Zuerich", "IBAN"),
        (f"Konto {IBAN_KOMPAKT} BIC UBSWCHZH", "IBAN"),
        (f"IBAN {IBAN_DE} BIC COBADEFFXXX", "IBAN"),
        (f"Karte {KARTE} 12 27 CVC 123", "Kreditkartennummer"),
        (f"Karte {KARTE} 123", "Kreditkartennummer"),
        (f"Karte {KARTE_AMEX} 0427", "Kreditkartennummer"),
        (f"Kartennummer {KARTE}.", "Kreditkartennummer"),
    ],
)
def test_nachfolgender_text_versteckt_iban_und_karte_nicht(text, art):
    assert art in finde_im_text(text)


@pytest.mark.parametrize(
    ("text", "art"),
    [
        (f"Konto {IBAN.replace(' ', NBSP)}", "IBAN"),
        (f"Konto {IBAN.replace(' ', SCHMALES_NBSP)}", "IBAN"),
        (f"Konto {IBAN.replace(' ', NULLBREITE + ' ')}", "IBAN"),
        (f"Konto {IBAN.lower()}", "IBAN"),
        (f"Konto {IBAN_DE.lower()} bic cobadeffxxx", "IBAN"),
        (f"Konto {IBAN_KOMPAKT.translate(VOLLBREIT)}", "IBAN"),
        (f"Karte {KARTE.replace(' ', NBSP)}", "Kreditkartennummer"),
        (f"Karte {KARTE.replace(' ', chr(9))}", "Kreditkartennummer"),
        ("AHV " + AHV.replace(".", NBSP), "AHV-Nummer"),
    ],
)
def test_unicode_leerzeichen_und_kleinschreibung_verstecken_nichts(text, art):
    assert art in finde_im_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "Rechnung 4111 1111 1111 1112 vom 12.03.2024",
        "FY24 Budget fuer Projekt Alpha und Beta im Team von zwoelf",
        f"Konto {IBAN_FALSCHE_PRUEFZIFFER} BIC UBSWCHZH",
        "Summe 4111111111111111.50 laut Tabelle",
        f"Telefon{NBSP}+41{NBSP}44{NBSP}555{NBSP}01{NBSP}23",
    ],
)
def test_keine_neuen_fehlalarme(text):
    assert finde_im_text(text) == []


def test_erlaubt_greift_auch_bei_geschuetztem_leerzeichen(tmp_path):
    liste = lade_verbotsliste(_liste(tmp_path, f"erlaubt:\n  - '{IBAN}'\n"))
    assert finde_im_text(f"Spendenkonto: {IBAN.replace(' ', NBSP)} BIC UBSWCHZH", liste) == []


def test_meldung_nennt_auch_bei_neuen_funden_keinen_wert():
    messages = [{"role": "user", "content": f"Konto {IBAN} BIC UBSWCHZH, Karte {KARTE} 123"}]
    with pytest.raises(AusgangGesperrt) as info:
        sperre_pruefen(messages, liste=lade_verbotsliste(Path("gibt-es-nicht.yaml")))
    meldung = str(info.value)
    assert "IBAN" in meldung and "Kreditkartennummer" in meldung
    for teil in ("0076", "5295", "1111", "UBSWCHZH"):
        assert teil not in meldung


def test_gesetzte_variable_ohne_datei_bricht_ab(monkeypatch, tmp_path):
    fehlt = tmp_path / "vertippt.yaml"
    monkeypatch.setenv(ausgangssperre.VERBOTSLISTE_ENV, str(fehlt))
    with pytest.raises(ValueError, match=ausgangssperre.VERBOTSLISTE_ENV):
        lade_verbotsliste()
    with pytest.raises(ValueError):
        sperre_pruefen([{"role": "user", "content": "harmloser Text"}])


def test_standardliste_liegt_relativ_zum_repo():
    assert ausgangssperre.VERBOTSLISTE_PFAD.is_absolute()
    assert ausgangssperre.VERBOTSLISTE_PFAD == ROOT_VERBOTSLISTE


def test_gesetzte_variable_ohne_datei_beendet_den_lauf_vor_dem_client(monkeypatch, tmp_path):
    monkeypatch.setenv(ausgangssperre.VERBOTSLISTE_ENV, str(tmp_path / "vertippt.yaml"))
    with pytest.raises(SystemExit):
        dok_namer.pruefe_verbotsliste_oder_beende()


def test_fehlende_standardliste_steht_im_log(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv(ausgangssperre.VERBOTSLISTE_ENV, raising=False)
    monkeypatch.setattr(ausgangssperre, "VERBOTSLISTE_PFAD", tmp_path / "fehlt.yaml")
    monkeypatch.setattr(ausgangssperre, "_HINWEIS_GEGEBEN", False)
    with caplog.at_level("INFO", logger=ausgangssperre.__name__):
        assert lade_verbotsliste().eintraege == ()
        lade_verbotsliste()
    hinweise = [r for r in caplog.records if "fehlt" in r.getMessage()]
    assert len(hinweise) == 1


def test_schwaerzung_findet_karte_mit_folgetext_und_nbsp():
    text = f"Karte {KARTE.replace(' ', NBSP)} 12/27, Ersatz {KARTE} 123"
    geschwaerzt, anzahl = ausgangssperre.schwaerze_karten(text, "[KARTE]")
    assert anzahl == 2
    assert finde_im_text(geschwaerzt) == []
