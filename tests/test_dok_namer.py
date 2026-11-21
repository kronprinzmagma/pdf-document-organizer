"""
Offline-Unit-Tests fuer reine Funktionen in dok_namer.py.
Keine API-Calls, kein ANTHROPIC_API_KEY erforderlich.
"""
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import dok_namer


# --- _ascii_filename_part ---

def test_ascii_filename_part_unicode():
    assert dok_namer._ascii_filename_part("Müller") == "Muller"


def test_ascii_filename_part_empty():
    assert dok_namer._ascii_filename_part("") == "unknown"


def test_ascii_filename_part_symbols():
    result = dok_namer._ascii_filename_part("foo! @bar")
    assert "-" in result
    assert "!" not in result
    assert "@" not in result


def test_ascii_filename_part_no_double_hyphens():
    result = dok_namer._ascii_filename_part("foo--bar")
    assert "--" not in result


# --- sanitize_filename ---

def test_sanitize_filename_truncates():
    long_name = "A" * 200 + ".pdf"
    result = dok_namer.sanitize_filename(long_name)
    assert len(result) <= dok_namer.MAX_FILENAME_LENGTH
    assert result.endswith(".pdf")


def test_sanitize_filename_adds_pdf():
    result = dok_namer.sanitize_filename("MyDoc")
    assert result.endswith(".pdf")


# --- unique_original_destination ---

def test_unique_original_destination_no_collision(tmp_path):
    result = dok_namer.unique_original_destination(tmp_path, "test.pdf")
    assert result == tmp_path / "test.pdf"
    assert not result.exists()


def test_unique_original_destination_collision(tmp_path):
    (tmp_path / "test.pdf").touch()
    result = dok_namer.unique_original_destination(tmp_path, "test.pdf")
    assert result.name == "test-2.pdf"


# --- done_category_for_filename ---

def test_done_category_bank():
    cats = dok_namer.load_categories()
    result = dok_namer.done_category_for_filename("ZKB-Kontoauszug-20250101.pdf", cats)
    assert result.startswith("02_"), f"Erwartet 02_-Praefix, erhalten: {result}"


def test_done_category_taxes():
    cats = dok_namer.load_categories()
    result = dok_namer.done_category_for_filename("Steueramt-Steuerrechnung-20260101.pdf", cats)
    assert result.startswith("01_"), f"Erwartet 01_-Praefix, erhalten: {result}"


def test_done_category_fallback():
    cats = dok_namer.load_categories()
    # Dateiname ohne Schluesselwoerter einer Kategorie → Fallback 99_Other
    result = dok_namer.done_category_for_filename("Zzz-Xyzzy-20250101.pdf", cats)
    assert "99" in result, f"Erwartet Fallback 99_, erhalten: {result}"


def test_done_category_custom_yaml(tmp_path):
    yaml_file = tmp_path / "cats.yaml"
    yaml_file.write_text(
        "- key: '01_Custom'\n  keywords:\n    - mycorp\n    - mycompany\n"
        "- key: '99_Rest'\n  keywords: []\n"
    )
    cats = dok_namer.load_categories(yaml_file)
    assert cats[0][0] == "01_Custom"
    result = dok_namer.done_category_for_filename("MyCorp-Invoice-20250101.pdf", cats)
    assert result == "01_Custom"


# --- calc_cost_chf ---

def test_calc_cost_chf_input_only():
    # 1M Input-Tokens × 1.00 USD/M × 0.90 = 0.90 CHF
    result = dok_namer.calc_cost_chf(1_000_000, 0)
    assert abs(result - 0.90) < 0.001, f"Erwartet ~0.90, erhalten: {result}"


def test_calc_cost_chf_output_only():
    # 1M Output-Tokens × 5.00 USD/M × 0.90 = 4.50 CHF
    result = dok_namer.calc_cost_chf(0, 1_000_000)
    assert abs(result - 4.50) < 0.001, f"Erwartet ~4.50, erhalten: {result}"


# --- verify_with_regex ---

def test_verify_with_regex_ahv():
    hits = dok_namer.verify_with_regex("AHV: 756.1234.5678.90")
    assert len(hits) == 1
    assert hits[0][0] == "AHV"


def test_verify_with_regex_clean():
    hits = dok_namer.verify_with_regex("Rechnung von Swisscom, CHF 89.00")
    assert hits == []


# --- redact ---

def test_redact_iban():
    text = "IBAN: CH56 0483 5012 3456 7800 9"  # gitleaks:allow
    redacted, counts = dok_namer.redact(text)
    assert "[IBAN]" in redacted
    assert "CH56" not in redacted


def test_redact_blocklist():
    redacted, counts = dok_namer.redact("Hallo John Smith", blocklist=("John Smith",))
    assert "[NAME]" in redacted
    assert "John Smith" not in redacted


# --- pre_extract_date ---

def test_pre_extract_date_standard_letter():
    # Typischer Schweizer Brief: «Ort, DD. Monat YYYY»
    text = "Swisscom AG\nBern, 1. Oktober 2025\nRechnung Oktober 2025"
    assert dok_namer.pre_extract_date(text) == "20251001"

def test_pre_extract_date_city_with_space():
    text = "Kantonales Steueramt\nSt. Gallen, 15. November 2025\nSteuerrechnung"
    assert dok_namer.pre_extract_date(text) == "20251115"

def test_pre_extract_date_bilingual_city():
    text = "PostFinance\nBiel/Bienne, 31. Dezember 2025\nKontoauszug"
    assert dok_namer.pre_extract_date(text) == "20251231"

def test_pre_extract_date_not_in_header():
    # Datum weit unten im Text → None (Briefkopf-Fenster überschritten)
    text = "EKZ Musterstadt\n" + "x" * 900 + "\nMusterstadt, 15. November 2025"
    assert dok_namer.pre_extract_date(text) is None

def test_pre_extract_date_no_match():
    text = "PostFinance Kontoauszug\nPeriode: 01.12.2025 – 31.12.2025\nSaldo: CHF 4727.40"
    # Kein «Ort, Datum»-Muster → None, LLM soll period-end ermitteln
    assert dok_namer.pre_extract_date(text) is None


# --- eval corpus loading/scoring ---

def test_load_eval_cases_from_expectations_json(tmp_path):
    (tmp_path / "sample_001.txt").write_text("PostFinance Zinsausweis", encoding="utf-8")
    (tmp_path / "expectations.json").write_text(json.dumps({
        "cases": [{
            "id": "case-1",
            "file": "sample_001.txt",
            "input_type": "text",
            "sender_any": ["PostFinance"],
            "content_any": ["Zinsausweis"],
            "date": "20230104",
        }]
    }), encoding="utf-8")

    cases = dok_namer.load_eval_cases(tmp_path)

    assert len(cases) == 1
    assert cases[0]["id"] == "case-1"
    assert cases[0]["input_type"] == "text"
    assert cases[0]["expected"]["sender_any"] == ["PostFinance"]
    assert cases[0]["expected"]["date"] == "20230104"
    assert cases[0]["cloud_safe"] is False


def test_score_eval_result_handles_optional_date():
    info = dok_namer.DocumentInfo(
        sender="PostFinance",
        content="Zinsausweis",
        date="unknown",
        confidence="high",
    )
    score = dok_namer._score_eval_result(info, {
        "sender_any": ["PostFinance"],
        "content_any": ["Zinsausweis"],
    })

    assert score["sender_ok"] is True
    assert score["content_ok"] is True
    assert score["date_ok"] is None
    assert score["all_ok"] is True


def test_score_eval_result_requires_date_when_expected():
    info = dok_namer.DocumentInfo(
        sender="PostFinance",
        content="Zinsausweis",
        date="unknown",
        confidence="high",
    )
    score = dok_namer._score_eval_result(info, {
        "sender_any": ["PostFinance"],
        "content_any": ["Zinsausweis"],
        "date": "20230104",
    })

    assert score["date_ok"] is False
    assert score["all_ok"] is False

# --- redact: Pattern-Abdeckung (sichert die Datenschutz-rote-Linie ab) ---

@pytest.mark.parametrize("text,label,leak", [
    ("AHV-Nummer: 756.4821.9034.17", "[AHV]", "756.4821"),  # synthetischer Testwert, gitleaks:allow
    ("AHV-Nummer: 7564821903417", "[AHV]", "7564821903417"),  # synthetischer Testwert, gitleaks:allow
    ("Kontakt: max.muster@example.ch", "[EMAIL]", "max.muster"),
    ("Telefon: 079 456 78 90", "[TELEFON]", "079 456"),
    ("Telefon: +41 79 456 78 90", "[TELEFON]", "79 456"),
    ("Total: CHF 1'234.50", "[BETRAG]", "1'234.50"),
    ("Bahnhofstrasse 12, 8001 Zuerich", "[ADRESSE]", "Bahnhofstrasse"),
    ("Ihr Arzt: Dr. med. Anna Weber", "[BEHANDLER]", "Weber"),
    ("Sehr geehrter Herr Muster", "[NAME]", "Muster"),
    ("Frau Anna Beispiel-Meier wird gebeten", "[NAME]", "Beispiel-Meier"),
])
def test_redact_patterns(text, label, leak):
    redacted, counts = dok_namer.redact(text)
    assert label in redacted, f"{label} fehlt in: {redacted!r}"
    assert leak not in redacted, f"Leak {leak!r} in: {redacted!r}"
    assert counts.get(label, 0) >= 1


def test_redact_email_before_phone():
    # E-Mail muss vor Telefon greifen, sonst zerlegt das Telefon-Pattern die Adresse
    redacted, _ = dok_namer.redact("info@ekz.ch")
    assert redacted == "[EMAIL]"


def test_redact_name_line_above_address():
    # Empfängername ohne Anrede direkt über der Adresse → [NAME]
    text = "Max Mustermann\nBahnhofstrasse 12, 8001 Zuerich"
    redacted, counts = dok_namer.redact(text)
    assert "Mustermann" not in redacted
    assert counts.get("[NAME]", 0) == 1


def test_redact_org_line_above_address_preserved():
    # Organisationszeilen über Adressen bleiben stehen (Absender-Extraktion)
    text = "Steueramt Zuerich\nBahnhofstrasse 12, 8001 Zuerich"
    redacted, _ = dok_namer.redact(text)
    assert "Steueramt" in redacted


def test_verify_with_regex_ahv_without_dots():
    hits = dok_namer.verify_with_regex("Versichertennummer 7561234567890")
    assert len(hits) == 1
    assert hits[0][0] == "AHV"


def test_verify_with_regex_ch_mobile():
    hits = dok_namer.verify_with_regex("Rueckruf unter 079 123 45 67")
    assert any(label.startswith("Telefon") for label, _ in hits)


# --- classify_error ---

def test_classify_error_pdf_path_in_message_not_pdf_error():
    # Dateipfade in Messages enden auf .pdf — darf NICHT als pdf-read-error gelten
    exc = FileNotFoundError("/inbox/scan-001.pdf nicht gefunden")
    assert dok_namer.classify_error(exc) == "FileNotFoundError"


def test_classify_error_timeout():
    exc = RuntimeError("request timed out after 30s")
    assert dok_namer.classify_error(exc) == "timeout"


# --- unique_destination ---

def test_unique_destination_collision_suffix(tmp_path):
    (tmp_path / "A-B-20250101.pdf").touch()
    dest = dok_namer.unique_destination(tmp_path, "A-B-20250101.pdf")
    assert dest.name == "A-B-20250101-2.pdf"


def test_move_renamed_collision_keeps_both_files(tmp_path):
    # Zwei Quelldateien mit identischem Vorschlag → keine darf verloren gehen
    src1 = tmp_path / "src1.pdf"; src1.write_text("eins")
    src2 = tmp_path / "src2.pdf"; src2.write_text("zwei")
    target = tmp_path / "ziel"; target.mkdir()
    dok_namer.move_renamed(target, "Sender-Inhalt-20250101.pdf", src1)
    dok_namer.move_renamed(target, "Sender-Inhalt-20250101.pdf", src2)
    files = sorted(p.name for p in target.iterdir())
    assert files == ["Sender-Inhalt-20250101-2.pdf", "Sender-Inhalt-20250101.pdf"]


# --- process_file Routing (gemockter Client, keine API-Calls) ---

# Synthetischer Brieftext, in dem Absender und Datum der Test-DocumentInfo vorkommen.
TESTTEXT = "Zürcher Kantonalbank ZKB\nKONTOAUSZUG\nPeriode: 01.09.2025 – 30.09.2025"

def _run_process_file(tmp_path, monkeypatch, info, text=None):
    src = tmp_path / "quelle"; src.mkdir()
    pdf = src / "scan-test.pdf"; pdf.write_text("dummy")
    dirs = {name: tmp_path / name for name in ("done", "unrecognized", "review", "error")}
    for d in dirs.values():
        d.mkdir()

    monkeypatch.setattr(dok_namer, "prepare_document",
                        lambda path, blocklist=(): ({"type": "text", "text": text or TESTTEXT}, {}, False))
    usage = type("Usage", (), {"input_tokens": 100, "output_tokens": 10})()
    monkeypatch.setattr(dok_namer, "analyze_claude", lambda client, block: (info, usage))

    status = dok_namer.process_file(
        None, pdf, dirs["done"], dirs["unrecognized"], dirs["review"], dirs["error"],
        engine="claude", auto=True, lines=[],
    )[0]
    return status, dirs


def test_process_file_high_confidence_renamed(tmp_path, monkeypatch):
    info = dok_namer.DocumentInfo(sender="ZKB", content="Kontoauszug", date="20250930", confidence="high")
    status, dirs = _run_process_file(tmp_path, monkeypatch, info)
    assert status == "renamed"
    moved = list(dirs["done"].rglob("*.pdf"))
    assert len(moved) == 1
    assert moved[0].name == "ZKB-Kontoauszug-20250930.pdf"
    assert moved[0].parent.name.startswith("02_")


def test_process_file_low_confidence_unrecognized(tmp_path, monkeypatch):
    info = dok_namer.DocumentInfo(sender="unknown", content="unknown", date="unknown", confidence="low")
    status, dirs = _run_process_file(tmp_path, monkeypatch, info)
    assert status == "unrecognized"
    assert (dirs["unrecognized"] / "scan-test.pdf").exists()


def test_redact_address_uncommon_suffix():
    # Strassennamen ohne Standard-Suffix (Vorstadt, Quai, …) muessen auch greifen
    redacted, _ = dok_namer.redact("Steinenvorstadt 15, 4051 Basel")
    assert "[ADRESSE]" in redacted
    assert "Steinenvorstadt" not in redacted


def test_interaktiv_vorschlag_steht_vor_der_rueckfrage(tmp_path, monkeypatch, capsys):
    # Regression: Im interaktiven Modus wurde die Ausgabe gepuffert, die Rueckfrage
    # «Akzeptieren?» erschien vor Analyse und vorgeschlagenem Dateinamen.
    src = tmp_path / "quelle"; src.mkdir()
    (src / "scan-test.pdf").write_text("dummy")
    info = dok_namer.DocumentInfo(sender="ZKB", content="Kontoauszug", date="20250930", confidence="high")
    usage = type("Usage", (), {"input_tokens": 100, "output_tokens": 10})()
    monkeypatch.setattr(dok_namer, "create_anthropic_client", lambda: None)
    monkeypatch.setattr(dok_namer, "load_blocklist", lambda: ())
    monkeypatch.setattr(dok_namer, "prepare_document",
                        lambda path, blocklist=(): ({"type": "text", "text": TESTTEXT}, {}, False))
    monkeypatch.setattr(dok_namer, "analyze_claude", lambda client, block: (info, usage))
    shown_before_prompt: list[str] = []

    def fake_input(prompt):
        shown_before_prompt.append(capsys.readouterr().out)
        return "y"

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(sys, "argv", ["dok_namer.py", str(src), "--engine", "claude"])

    dok_namer.main()

    assert shown_before_prompt, "Rueckfrage wurde nicht gestellt"
    assert "ZKB-Kontoauszug-20250930.pdf" in shown_before_prompt[0]


# --- Plausibilitaetspruefung vor dem Umbenennen ---

@pytest.mark.parametrize("date, text", [
    ("20251115", "Musterstadt, 15. November 2025"),
    ("20251001", "Bern, 1. Oktober 2025"),
    ("20250930", "Periode: 01.09.2025 – 30.09.2025"),
    ("20251231", "VORSORGEGUTHABEN per 31.12.2025"),
    ("20251005", "Datum: 5.10.25"),
    ("20260301", "Lausanne, 1. März 2026"),
    ("20251203", "Uster, 3. Dez. 2025"),
])
def test_check_date_im_text_belegt(date, text):
    assert dok_namer.check_date(date, text) is None


@pytest.mark.parametrize("date, text, reason", [
    ("unknown", "Musterstadt, 15. November 2025", "datum-fehlt-oder-unbekannt"),
    ("2025111", "Musterstadt, 15. November 2025", "datum-fehlt-oder-unbekannt"),
    ("20250231", "31.02.2025", "datum-kein-kalenderdatum"),
    ("20991231", "31.12.2099", "datum-ausserhalb-zeitraum"),
    ("20251116", "Periode 01.11.2025 – 15.11.2025", "datum-nicht-im-text"),
    # Briefdatum im Kopf hat Vorrang: Faelligkeit oder Periodenende zaehlen nicht
    ("20251116", "Musterstadt, 15. November 2025", "datum-nicht-briefdatum"),
    ("20251231", "St. Gallen, 1. Oktober 2025\nPeriode: 01.10.2025 – 31.12.2025", "datum-nicht-briefdatum"),
    # 1.10.2025 darf nicht in 11.10.2025 gefunden werden
    ("20251001", "Zahlbar bis 11.10.2025", "datum-nicht-im-text"),
])
def test_check_date_faellt_durch(date, text, reason):
    assert dok_namer.check_date(date, text, today=datetime(2026, 11, 19)) == reason


@pytest.mark.parametrize("sender, text", [
    ("Swisscom", "Swisscom (Schweiz) AG"),
    ("Swisscom-AG", "Swisscom (Schweiz) AG"),
    ("Steueramt-Zuerich", "Kantonales Steueramt Musterstadt"),
    ("Zurich", "Kantonales Steueramt Musterstadt"),
    ("EKZ", "Elektrizitätswerke des Kantons Musterstadt (EKZ)"),
    ("Migros-Bank", "Migros Bank AG"),
    ("Pensionskasse-SBB", "Pensionskasse SBB"),
])
def test_check_sender_im_text_belegt(sender, text):
    assert dok_namer.check_sender(sender, text) is None


@pytest.mark.parametrize("sender, text, reason", [
    ("unknown", "Swisscom (Schweiz) AG", "absender-fehlt-oder-unbekannt"),
    ("[NAME]", "Swisscom (Schweiz) AG", "absender-fehlt-oder-unbekannt"),
    ("Sunrise", "Swisscom (Schweiz) AG", "absender-nicht-im-text"),
    # «CSS» darf nicht als Teil eines anderen Wortes zaehlen
    ("CSS", "Prozess-Stand", "absender-nicht-im-text"),
    ("Helsana-Versicherungen-Bern", "Versicherungen", "absender-nicht-im-text"),
])
def test_check_sender_faellt_durch(sender, text, reason):
    assert dok_namer.check_sender(sender, text) == reason


def test_check_plausibility_ohne_text_geht_zur_pruefung():
    info = dok_namer.DocumentInfo(sender="ZKB", content="Kontoauszug", date="20250930", confidence="high")
    assert dok_namer.check_plausibility(info, "") == ["kein-text-fuer-pruefung"]


def test_process_file_unplausibles_datum_geht_nach_review(tmp_path, monkeypatch):
    # Modell sagt «high», aber das Datum steht nirgends im Text → nicht umbenennen.
    info = dok_namer.DocumentInfo(sender="ZKB", content="Kontoauszug", date="20251231", confidence="high")
    status, dirs = _run_process_file(tmp_path, monkeypatch, info)
    assert status == "review"
    assert (dirs["review"] / "scan-test.pdf").exists()
    assert not list(dirs["done"].rglob("*.pdf"))


def test_process_file_erfundener_absender_geht_nach_review(tmp_path, monkeypatch):
    info = dok_namer.DocumentInfo(sender="UBS", content="Kontoauszug", date="20250930", confidence="high")
    status, dirs = _run_process_file(tmp_path, monkeypatch, info)
    assert status == "review"
    assert (dirs["review"] / "scan-test.pdf").exists()


def test_pruefgrund_und_vorschlag_stehen_im_log(tmp_path, monkeypatch):
    src = tmp_path / "quelle"; src.mkdir()
    (src / "scan-test.pdf").write_text("dummy")
    info = dok_namer.DocumentInfo(sender="UBS", content="Kontoauszug", date="20250930", confidence="high")
    usage = type("Usage", (), {"input_tokens": 100, "output_tokens": 10})()
    monkeypatch.setattr(dok_namer, "create_anthropic_client", lambda: None)
    monkeypatch.setattr(dok_namer, "load_blocklist", lambda: ())
    monkeypatch.setattr(dok_namer, "prepare_document",
                        lambda path, blocklist=(): ({"type": "text", "text": TESTTEXT}, {}, False))
    monkeypatch.setattr(dok_namer, "analyze_claude", lambda client, block: (info, usage))
    monkeypatch.setattr(sys, "argv", ["dok_namer.py", str(src), "--engine", "claude", "--auto"])

    dok_namer.main()

    entry = json.loads((src / "dok-namer-log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert entry["status"] == "review"
    assert entry["review_reason"] == "pruefung:absender-nicht-im-text"
    assert entry["suggested"] == "UBS-Kontoauszug-20250930.pdf"
    assert entry["error_reason"] == ""
    report = (src / "dok-namer-report.md").read_text(encoding="utf-8")
    assert "| absender-nicht-im-text | 1 |" in report
    assert "UBS" not in report



@pytest.mark.parametrize("content, sender, text", [
    ("Stromrechnung", "EKZ", "EKZ STROMRECHNUNG"),
    ("Rechnung", "Swisscom", "Swisscom STROMRECHNUNG"),
    ("Praemienrechnung", "Helsana", "Helsana PRÄMIENRECHNUNG – Quartal IV"),
    ("Generalabonnement-Erneuerung", "SBB", "SBB GENERALABONNEMENT – ERNEUERUNGSRECHNUNG"),
])
def test_check_content_im_text_belegt(content, sender, text):
    assert dok_namer.check_content(content, sender, text) is None


@pytest.mark.parametrize("content, sender, text, reason", [
    ("unknown", "EKZ", "EKZ STROMRECHNUNG", "inhalt-fehlt-oder-unbekannt"),
    # Tippfehler des Modells: steht so nicht im Text
    ("Abfallgebuernrechnung", "Kusnacht", "Küsnacht ABFALLGEBÜHRENRECHNUNG 2025", "inhalt-nicht-im-text"),
    ("Hypothekar-Zinsabrechnung", "HYPOTHEKAR-ZINSABRECHNUNG", "Raiffeisen HYPOTHEKAR-ZINSABRECHNUNG",
     "absender-ist-dokumenttyp"),
])
def test_check_content_faellt_durch(content, sender, text, reason):
    assert dok_namer.check_content(content, sender, text) == reason
# --- Absender aus der bestehenden Ablage ---

def _ablage(tmp_path, names):
    done = tmp_path / "done"
    for rel in names:
        f = done / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
    return done


@pytest.mark.parametrize("variant", ["Swisscom", "Swisscom-AG", "swisscom", "SWISSCOM-Schweiz-AG", "Swisscom (Schweiz) AG"])
def test_sender_key_vereinheitlicht_varianten(variant):
    assert dok_namer.sender_key(variant) == "swisscom"


def test_sender_key_faltet_umlaute():
    assert dok_namer.sender_key("Steueramt-Musterstadt") == dok_namer.sender_key("Steueramt-Zuerich")


def test_collect_known_senders_nimmt_haeufigste_schreibweise(tmp_path):
    done = _ablage(tmp_path, [
        "05_Wohnen/Swisscom-Rechnung-20250101.pdf",
        "05_Wohnen/Swisscom-Rechnung-20250201.pdf",
        "05_Wohnen/swisscom-Rechnung-20250301.pdf",
        "02_Banken/Migros-Bank-Kontoauszug-20250131.pdf",
        "02_Banken/Migros-Bank-Kontoauszug-20250131-2.pdf",
        "99_Sonstiges/notizen.pdf",  # nicht von dok-namer benannt
    ])
    known = dok_namer.collect_known_senders(done)
    assert known["swisscom"] == "Swisscom"
    assert known["migrosbank"] == "Migros-Bank"
    assert "notizen" not in known


def test_collect_known_senders_ohne_ablage_ist_leer(tmp_path):
    assert dok_namer.collect_known_senders(tmp_path / "gibts-nicht") == {}


def test_match_sender_bildet_variante_auf_ablage_ab(tmp_path):
    done = _ablage(tmp_path, ["05_Wohnen/Swisscom-Rechnung-20250101.pdf"])
    known = dok_namer.collect_known_senders(done)
    assert dok_namer.match_sender("Swisscom-AG", known) == ("Swisscom", "ablage")
    assert dok_namer.match_sender("swisscom", known) == ("Swisscom", "ablage")


def test_match_sender_neuer_absender_bleibt(tmp_path):
    done = _ablage(tmp_path, ["05_Wohnen/Swisscom-Rechnung-20250101.pdf"])
    known = dok_namer.collect_known_senders(done)
    assert dok_namer.match_sender("Sunrise", known) == ("Sunrise", "neu")


def test_match_sender_alias_hat_vorrang(tmp_path):
    cfg = tmp_path / "absender.yaml"
    cfg.write_text("- name: ZKB\n  aliases: [Zuercher Kantonalbank, Zürcher Kantonalbank AG]\n- EKZ\n",
                   encoding="utf-8")
    aliases = dok_namer.load_sender_aliases(source_folder=tmp_path)
    known = {"zurcherkantonalbank": "Zuercher-Kantonalbank"}
    assert dok_namer.match_sender("Zürcher-Kantonalbank", known, aliases) == ("ZKB", "alias")
    assert dok_namer.match_sender("zkb", {}, aliases) == ("ZKB", "alias")
    assert dok_namer.match_sender("EKZ-AG", {}, aliases) == ("EKZ", "alias")


def test_load_sender_aliases_ohne_datei_ist_leer(tmp_path):
    assert dok_namer.load_sender_aliases(source_folder=tmp_path) == {}


def test_load_sender_aliases_ungueltiges_format(tmp_path):
    cfg = tmp_path / "absender.yaml"
    cfg.write_text("name: ZKB\n", encoding="utf-8")
    with pytest.raises(ValueError):
        dok_namer.load_sender_aliases(cfg)


def _run_main_mit_ablage(tmp_path, monkeypatch, sender, extra_args=()):
    src = tmp_path / "quelle"; src.mkdir()
    (src / "scan-test.pdf").write_text("dummy")
    _ablage(src, ["02_Banking-Pension/Zuercher-Kantonalbank-Kontoauszug-20250831.pdf"])
    info = dok_namer.DocumentInfo(sender=sender, content="Kontoauszug", date="20250930", confidence="high")
    usage = type("Usage", (), {"input_tokens": 100, "output_tokens": 10})()
    monkeypatch.setattr(dok_namer, "create_anthropic_client", lambda: None)
    monkeypatch.setattr(dok_namer, "load_blocklist", lambda: ())
    monkeypatch.setattr(dok_namer, "prepare_document",
                        lambda path, blocklist=(): ({"type": "text", "text": TESTTEXT}, {}, False))
    monkeypatch.setattr(dok_namer, "analyze_claude", lambda client, block: (info, usage))
    monkeypatch.setattr(sys, "argv", ["dok_namer.py", str(src), "--engine", "claude", "--auto", *extra_args])
    dok_namer.main()
    return sorted(p.name for p in (src / "done").rglob("*.pdf")), src


def test_ablauf_uebernimmt_schreibweise_der_ablage(tmp_path, monkeypatch):
    names, src = _run_main_mit_ablage(tmp_path, monkeypatch, "Zürcher-Kantonalbank-AG")
    assert "Zuercher-Kantonalbank-Kontoauszug-20250930.pdf" in names
    report = (src / "dok-namer-report.md").read_text(encoding="utf-8")
    assert "| existing sender in done/ | 1 |" in report


def test_ablauf_ohne_abgleich_behaelt_modellvorschlag(tmp_path, monkeypatch):
    names, _ = _run_main_mit_ablage(tmp_path, monkeypatch, "Zürcher-Kantonalbank-AG",
                                    extra_args=("--no-sender-matching",))
    # sanitize_filename macht aus «ü» ein «u»: ohne Abgleich entsteht eine neue Variante
    assert "Zurcher-Kantonalbank-AG-Kontoauszug-20250930.pdf" in names


def test_absender_beispieldatei_ist_gueltig():
    example = Path(__file__).parent.parent / "absender.yaml.example"
    aliases = dok_namer.load_sender_aliases(example)
    assert aliases[dok_namer.sender_key("Zürcher Kantonalbank")] == "ZKB"
