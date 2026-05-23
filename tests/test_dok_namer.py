"""
Offline-Unit-Tests fuer reine Funktionen in dok_namer.py.
Keine API-Calls, kein ANTHROPIC_API_KEY erforderlich.
"""
import sys
import json
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
    # 1M Input-Tokens × 0.80 USD/M × 0.90 = 0.72 CHF
    result = dok_namer.calc_cost_chf(1_000_000, 0)
    assert abs(result - 0.72) < 0.001, f"Erwartet ~0.72, erhalten: {result}"


def test_calc_cost_chf_output_only():
    # 1M Output-Tokens × 4.00 USD/M × 0.90 = 3.60 CHF
    result = dok_namer.calc_cost_chf(0, 1_000_000)
    assert abs(result - 3.60) < 0.001, f"Erwartet ~3.60, erhalten: {result}"


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
    text = "IBAN: CH56 0483 5012 3456 7800 9"
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
