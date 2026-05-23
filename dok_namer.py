#!/usr/bin/env python3
"""
dok-namer: Suggest structured filenames for all PDFs in a folder using Claude or Ollama.
Usage: python dok_namer.py <folder> [--engine claude|ollama|hybrid] [--auto] [--workers N]
"""

import argparse
import concurrent.futures
import json
import re
import sys
import threading
import time
import unicodedata
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader
from pydantic import BaseModel

# Only PDFs for folder mode
PDF_SUFFIX = ".pdf"

# Verzeichnis dieses Skripts — Basis für redact-names.txt
PROJECT_DIR = Path(__file__).parent

# Pricing for claude-haiku-4-5-20251001 (USD per million tokens)
PRICE_INPUT_PER_M  = 0.80
PRICE_OUTPUT_PER_M = 4.00
USD_TO_CHF         = 0.90

# Redaction patterns: (compiled_regex, replacement_label)
REDACTION_PATTERNS = [
    # IBAN (Swiss CH… and generic two-letter country code)
    (re.compile(r'\b[A-Z]{2}\d{2}(?:\s*[A-Z0-9]{4}){2,7}\b'), "[IBAN]"),
    # Swiss AHV number: 756.XXXX.XXXX.XX
    (re.compile(r'\b756\.\d{4}\.\d{4}\.\d{2}\b'), "[AHV]"),
    # Email addresses (before phone to avoid partial matches)
    (re.compile(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b'), "[EMAIL]"),
    # Phone numbers: Swiss 0XX XXX XX XX and international +XX …
    (re.compile(
        r'(?:\+\d{1,3}[\s\-.]?\d{2,3}[\s\-.]?\d{3,4}[\s\-.]?\d{2,4}(?:[\s\-.]?\d{2,4})?'
        r'|\b0\d{2}[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}\b)'
    ), "[TELEFON]"),
    # Amounts with currency symbol before or after the number
    (re.compile(
        r'(?:CHF|EUR|USD)\s*\d{1,3}(?:[\'.\s]\d{3})*(?:[.,]\d{2})?'
        r'|\d{1,3}(?:[\'.\s]\d{3})*(?:[.,]\d{2})?\s*(?:CHF|EUR|USD)',
        re.IGNORECASE,
    ), "[BETRAG]"),
    # Swiss postal address: Strasse/Weg/etc. + number + PLZ (4 digits) + city
    (re.compile(
        r'[A-ZÄÖÜ][a-zA-Zäöüÿ]+'
        r'(?:strasse|gasse|weg|allee|platz|ring|str\.?)'
        r'[\s\-]?\d+[a-z]?[,\s]+'
        r'\d{4}\s+[A-ZÄÖÜ][a-zA-Zäöüÿ]+',
        re.IGNORECASE,
    ), "[ADRESSE]"),
    # Akademische/medizinische Titel gefolgt von 1–3 Wörtern (Behandler-/Personenname)
    # Beispiele: Dr. Müller, Dr. med. Max Mustermann, Prof. Dr. Anna Weber, PD Dr. H. Keller
    (re.compile(
        r'\b(?:Prof\.(?:\s+Dr\.)?|PD\s+Dr\.|Dr\.(?:\s+med\.(?:\s+dent\.)?)?'
        r'|med\.\s+dent\.|lic\.\s+phil\.|dipl\.\s+psych\.)'
        r'\s+[A-ZÄÖÜ][a-zA-ZäöüÄÖÜß\-]+(?:\s+[A-ZÄÖÜ][a-zA-ZäöüÄÖÜß\-]+){0,2}'
    ), "[BEHANDLER]"),
]

EXTRACTION_PROMPT = (
    "You are extracting structured metadata from a Swiss administrative document.\n\n"
    "Extract these four fields:\n\n"
    "- sender: the organisation or authority that issued the document. "
    "Use the letterhead at the top (e.g. 'EKZ', 'Swisscom', 'ZKB', 'Helsana', 'Steueramt-Zuerich'). "
    "No spaces — use hyphens. Omit legal suffixes like AG, GmbH.\n\n"
    "- content: a short label (1–3 words, hyphens) for what the document IS "
    "(e.g. 'Stromrechnung', 'Kontoauszug', 'Praemienrechnung', 'Mahnung', 'Vorsorgeausweis', "
    "'Hypothekar-Zinsabrechnung', 'Generalabonnement-Erneuerung').\n\n"
    "- date: the document's ISSUANCE date in YYYYMMDD format. Priority rules:\n"
    "  1. If the letter shows 'Ort, DD. Monat YYYY' in the top-right area — use that date.\n"
    "  2. For account statements (Kontoauszug, Kreditkartenabrechnung): use the LAST day of the "
    "statement period (e.g. period 01.11–30.11.2025 → 20251130).\n"
    "  3. For annual reports/certificates (Vorsorgeausweis, Jahresabschluss YYYY): "
    "use 31.12 of that year.\n"
    "  Do NOT use payment due dates (Zahlbar bis), invoice receipt dates, or scan dates.\n"
    "  Use 'unknown' only if truly impossible to determine.\n\n"
    "- confidence: 'high' if sender, content, and date are all clearly identified; "
    "'low' if any field is uncertain or missing.\n"
)


def load_blocklist() -> tuple[str, ...]:
    """
    redact-names.txt im Projektverzeichnis einlesen (falls vorhanden).
    Eine Zeile pro Name/Begriff; Zeilen mit # und Leerzeilen werden ignoriert.
    Gibt ein leeres Tupel zurück, wenn die Datei nicht existiert.
    """
    path = PROJECT_DIR / "redact-names.txt"
    if not path.exists():
        return ()
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return tuple(names)


# Deutsch: Monatsname → Monatsnummer (für deterministische Datumsextraktion)
_MONTH_DE: dict[str, int] = {
    "januar": 1, "jan": 1,
    "februar": 2, "feb": 2,
    "märz": 3, "maerz": 3, "marz": 3, "mar": 3, "mär": 3,
    "april": 4, "apr": 4,
    "mai": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}

# «Ort, DD. Monat YYYY» — das zuverlässigste Ausstellungsdatum in Schweizer Briefen
_CITY_DATE_RE = re.compile(
    r"[A-ZÄÖÜ][a-zäöü]+"               # Stadt
    r"(?:[/\-][A-ZÄÖÜ][a-zäöü]+)?"     # optionaler Zusatz (z.B. Biel/Bienne)
    r"(?:\s+[A-ZÄÖÜ][a-zäöü]+)?"       # optionales zweites Wort (St. Gallen)
    r",\s*"                              # Komma nach Ort
    r"(\d{1,2})\.\s*"                   # Tag
    r"(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
    r"|Jan|Feb|Mär|Mar|Apr|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\.?\s+"
    r"(\d{4})",                         # Jahr
    re.IGNORECASE,
)


def pre_extract_date(text: str) -> str | None:
    """Versucht, das Ausstellungsdatum deterministisch aus dem Briefkopf zu extrahieren.

    Sucht nach «Ort, DD. Monat YYYY» in den ersten 800 Zeichen (Briefkopf-Bereich).
    Gibt YYYYMMDD zurück oder None wenn kein eindeutiges Muster gefunden.
    Keine API, kein LLM — rein regelbasiert.
    """
    header = text[:800]
    m = _CITY_DATE_RE.search(header)
    if not m:
        return None
    try:
        day = int(m.group(1))
        month_raw = m.group(2).rstrip(".").lower()
        # Umlaute normalisieren für Dict-Lookup
        month_key = month_raw.replace("ä", "a").replace("ö", "o").replace("ü", "u")
        year = int(m.group(3))
        month = _MONTH_DE.get(month_key) or _MONTH_DE.get(month_raw)
        if month and 2000 <= year <= 2100 and 1 <= day <= 31:
            return f"{year}{month:02d}{day:02d}"
    except (ValueError, AttributeError):
        pass
    return None


def calc_cost_chf(input_tokens: int, output_tokens: int) -> float:
    """Gesamtkosten in CHF für einen einzelnen API-Call."""
    usd = (input_tokens * PRICE_INPUT_PER_M + output_tokens * PRICE_OUTPUT_PER_M) / 1_000_000
    return usd * USD_TO_CHF


def create_anthropic_client() -> Any:
    """Anthropic-Client erst laden, wenn eine Cloud-Engine verwendet wird."""
    try:
        import anthropic
    except ImportError:
        print("Fehler: 'anthropic' Python-Bibliothek nicht installiert. Ausführen: pip install anthropic")
        raise
    return anthropic.Anthropic()


def classify_error(exc: Exception) -> str:
    """Technische Fehler anonym und reporttauglich klassifizieren."""
    msg = str(exc).lower()
    if "authentication" in msg or "api_key" in msg or "auth_token" in msg:
        return "auth-missing"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "rate limit" in msg or "429" in msg:
        return "rate-limit"
    if "overloaded" in msg or "529" in msg:
        return "overloaded"
    if "json" in msg or "parse" in msg:
        return "parse-error"
    if "pdf" in msg or "eof marker" in msg:
        return "pdf-read-error"
    return type(exc).__name__


def is_retryable_error(exc: Exception) -> bool:
    """Nur temporäre Cloud-Fehler erneut versuchen."""
    return classify_error(exc) in {"rate-limit", "timeout", "overloaded"}


def retry_delay_seconds(exc: Exception, attempt_index: int) -> float:
    """Backoff-Dauer bestimmen; Retry-After-Header wird respektiert, falls vorhanden."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return max(1.0, float(retry_after))
            except ValueError:
                pass
    return CLAUDE_BACKOFF_SECONDS[min(attempt_index, len(CLAUDE_BACKOFF_SECONDS) - 1)]


def _ascii_filename_part(value: str) -> str:
    """Text in einen robusten, portablen Dateinamen-Bestandteil umwandeln."""
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "unknown"


def sanitize_filename(filename: str) -> str:
    """Dateinamen normalisieren, Sonderzeichen entfernen und Länge begrenzen."""
    stem = filename[:-len(PDF_SUFFIX)] if filename.lower().endswith(PDF_SUFFIX) else filename
    stem = _ascii_filename_part(stem)
    max_stem_len = MAX_FILENAME_LENGTH - len(PDF_SUFFIX)
    if len(stem) > max_stem_len:
        stem = stem[:max_stem_len].rstrip("-") or "unknown"
    return stem + PDF_SUFFIX


def unique_destination(directory: Path, filename: str) -> Path:
    """Kollisionsfreien Zielpfad im Zielordner bestimmen."""
    filename = sanitize_filename(filename)
    dest = directory / filename
    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    for i in range(2, 10_000):
        marker = f"-{i}"
        max_stem_len = MAX_FILENAME_LENGTH - len(suffix) - len(marker)
        candidate_stem = stem[:max_stem_len].rstrip("-") or "unknown"
        candidate = directory / f"{candidate_stem}{marker}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Kein freier Dateiname gefunden für: {filename}")


def unique_original_destination(directory: Path, filename: str) -> Path:
    """Originalnamen erhalten, aber bei Kollision einen Zähler anhängen."""
    dest = directory / filename
    if not dest.exists():
        return dest

    stem = Path(filename).stem
    suffix = Path(filename).suffix or PDF_SUFFIX
    for i in range(2, 10_000):
        candidate = directory / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Kein freier Dateiname gefunden für: {filename}")


# Built-in English category defaults. Override by placing categories.yaml in the
# working directory or by passing --config path/to/categories.yaml.
DONE_CATEGORIES_DEFAULT: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "01_Taxes-Government",
        (
            "tax", "taxes", "irs", "hmrc", "government", "steuer", "finanzdirektion",
            "steuerverwaltung", "gemeindesteuer", "kantonssteuer",
            "ahv-ausgleichskasse", "ahv", "ausgleichskasse",
            "gemeinde", "kanton", "polizei", "gericht", "bund",
        ),
    ),
    (
        "02_Banking-Pension",
        (
            "bank", "banking", "ubs", "zkb", "kantonalbank", "postfinance",
            "raiffeisen", "credit-suisse", "migros-bank", "swisscard", "topcard",
            "selma", "true-wealth", "kontoauszug", "account-statement",
            "kontoabschluss", "zins", "interest", "saldo", "balance",
            "pension", "retirement", "vorsorge", "pensionskasse", "freizuegigkeit",
            "saeule", "3a", "kreditkarte", "credit-card",
        ),
    ),
    (
        "03_Health-Insurance",
        (
            "health", "medical", "hospital", "doctor", "pharmacy",
            "helsana", "sanitas", "kpt", "css", "visana",
            "praemienverbilligung", "premium-reduction",
            "arzt", "medizin", "psych", "labor", "analytica",
            "rezept", "prescription", "konsultation", "leistungsabrechnung",
            "krankenkasse", "health-insurance", "behandlung", "spitex",
        ),
    ),
    (
        "04_Insurance",
        (
            "insurance", "versicherung", "versicherungen",
            "mobiliar", "axa", "smile", "zurich", "helvetia",
            "police", "policy", "praemienrechnung", "premium",
            "hausrat", "haftpflicht", "liability", "schutzbrief",
            "tcs-eti",
        ),
    ),
    (
        "05_Housing-Utilities",
        (
            "rent", "rental", "miet", "nebenkosten", "utility", "utilities",
            "heiz", "heating", "betriebskosten", "operating-costs",
            "wohnen", "wohneigentum", "liegenschaft", "property",
            "grundstueck", "grundstuck", "eigenmietwert",
            "electricity", "strom", "energie", "energy",
            "ekz", "ewz", "gas", "water", "wasser", "kehricht",
            "internet", "telefonrechnung", "mobile", "sunrise", "yallo", "swisscom",
            "radio", "tv", "cleaning", "reinigung", "maintenance",
        ),
    ),
    (
        "06_Work-Income",
        (
            "salary", "income", "employment", "work", "job",
            "arbeitsvertrag", "lohnausweis", "lohnabrechnung", "payslip",
            "arbeitslosen", "unemployment", "arbeitszeugnis", "reference",
            "austritt", "kuendigung", "resignation", "termination",
            "company", "firma", "vertrag", "contract", "invoice",
        ),
    ),
    (
        "07_Children-Education",
        (
            "school", "education", "childcare", "university", "college",
            "schulamt", "schulbetreuung", "betreuung", "kita",
            "schulgeld", "tuition", "coursera", "certificate",
            "zeugnis", "diploma", "bildung", "padi",
        ),
    ),
    (
        "08_Transport",
        (
            "car", "vehicle", "auto", "transport", "mobility",
            "garage", "fahrzeug", "motorfahrzeug", "verkehr",
            "radwechsel", "tyre", "tire", "winterraed",
            "strassenverkehr", "publibike", "velo", "bicycle",
            "touring-club", "tcs", "busse", "traffic", "verkehrsabgabe",
        ),
    ),
    (
        "09_Shopping-Memberships",
        (
            "shopping", "purchase", "membership", "subscription",
            "rechnung", "quittung", "receipt", "lieferschein",
            "retourenschein", "return", "galaxus", "digitec",
            "shop", "store", "dhl", "delivery", "mahnung", "reminder",
            "kostenvoranschlag", "quote", "mitglied", "alumni",
            "donation", "sponsorship", "fitness", "abo",
        ),
    ),
    (
        "10_Personal-Legal",
        (
            "legal", "personal", "identity", "document",
            "zivilstand", "standesamt", "birth", "marriage", "divorce",
            "geburts", "eheschein", "scheidung", "familien",
            "testament", "will", "vollmacht", "power-of-attorney",
            "birth-certificate", "passport", "id",
        ),
    ),
    (
        "99_Other",
        (),
    ),
)


def load_categories(path: Path | None = None) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Load categories from a YAML file, or return built-in English defaults if absent.

    The YAML file must be a list of objects with 'key' (str) and 'keywords' (list[str]).
    If path is None, looks for categories.yaml in the current working directory.
    If the file does not exist, returns DONE_CATEGORIES_DEFAULT without error.
    """
    import yaml  # imported here so pyyaml is only required when actually used
    if path is None:
        path = Path.cwd() / "categories.yaml"
    if not path.exists():
        return DONE_CATEGORIES_DEFAULT
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return tuple(
        (entry["key"], tuple(kw.lower() for kw in entry.get("keywords", [])))
        for entry in data
    )


def done_category_for_filename(
    filename: str,
    categories: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
) -> str:
    """Return the done/ subfolder name for a recognised PDF based on its filename.

    categories: tuple of (folder_name, keywords_tuple) pairs. If None, uses built-in defaults.
    """
    cats = categories if categories is not None else DONE_CATEGORIES_DEFAULT
    key = _quality_key(filename)
    for category, markers in cats:
        if any(marker in key for marker in markers):
            return category
    # Fall back to last category (99_Other or 99_Sonstiges in YAML override)
    if cats:
        return cats[-1][0]
    return "99_Other"


def _quality_key(value: str) -> str:
    """Vergleichsstring für Testauswertungen."""
    return _ascii_filename_part(value).lower()


def evaluate_test_quality(run_entries: list[dict]) -> dict[str, float | int] | None:
    """Synthetische Test-PDFs aggregiert gegen erwartete Kerndaten prüfen."""
    evaluated = 0
    matches = 0
    high_conf = 0

    for entry in run_entries:
        expected = TEST_EXPECTATIONS.get(entry.get("file", ""))
        if not expected:
            continue

        evaluated += 1
        suggested = _quality_key(entry.get("suggested", ""))
        sender_ok = any(_quality_key(v) in suggested for v in expected["sender_any"])
        content_ok = any(_quality_key(v) in suggested for v in expected["content_any"])
        date_ok = expected["date"] in suggested
        status_ok = entry.get("status") == "renamed"

        if entry.get("confidence") == "high":
            high_conf += 1
        if status_ok and sender_ok and content_ok and date_ok:
            matches += 1

    if evaluated == 0:
        return None

    return {
        "evaluated": evaluated,
        "matches": matches,
        "match_rate": matches / evaluated,
        "high_conf": high_conf,
        "high_conf_rate": high_conf / evaluated,
        "target_high_conf_rate": 0.90,
    }


def _expectation_values(expected: dict, key: str) -> list[str]:
    """Erwartungswerte robust als Liste normalisieren."""
    value = expected.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(v) for v in value if str(v)]


def _field_match(actual: str, expected_values: list[str]) -> bool | None:
    """Substring-Match fuer Eval-Felder; None bedeutet: Feld wird nicht bewertet."""
    if not expected_values:
        return None
    actual_key = _quality_key(actual)
    return any(_quality_key(v) in actual_key for v in expected_values)


def _score_eval_result(info: "DocumentInfo", expected: dict) -> dict[str, bool | None]:
    """DocumentInfo gegen optionale sender/content/date-Erwartungen bewerten."""
    sender_ok = _field_match(info.sender, _expectation_values(expected, "sender_any"))
    content_ok = _field_match(info.content, _expectation_values(expected, "content_any"))

    expected_date = str(expected.get("date", "") or "")
    date_ok: bool | None
    if expected_date:
        date_ok = info.date == expected_date
    else:
        date_ok = None

    checked = [v for v in (sender_ok, content_ok, date_ok) if v is not None]
    all_ok = all(checked) if checked else False
    return {
        "sender_ok": sender_ok,
        "content_ok": content_ok,
        "date_ok": date_ok,
        "all_ok": all_ok,
    }


def _safe_corpus_label(corpus_dir: Path) -> str:
    """Report-taugliche Corpus-Bezeichnung ohne absoluten lokalen Pfad."""
    try:
        return str(corpus_dir.resolve().relative_to(PROJECT_DIR.resolve()))
    except ValueError:
        return corpus_dir.name


def _load_external_eval_cases(corpus_dir: Path) -> list[dict] | None:
    """Text/PDF-Eval-Cases aus expectations.json laden, falls vorhanden."""
    expectations_path = corpus_dir / "expectations.json"
    if not expectations_path.exists():
        return None

    data = json.loads(expectations_path.read_text(encoding="utf-8"))
    cloud_safe = bool(data.get("cloud_safe", False)) if isinstance(data, dict) else False
    raw_cases = data.get("cases", data) if isinstance(data, dict) else data
    if not isinstance(raw_cases, list):
        raise ValueError("expectations.json muss eine Liste oder ein Objekt mit 'cases' enthalten.")

    cases: list[dict] = []
    for index, raw in enumerate(raw_cases, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Eval-Case #{index} ist kein Objekt.")
        rel_file = raw.get("file")
        if not rel_file:
            raise ValueError(f"Eval-Case #{index} hat kein 'file'.")

        path = corpus_dir / str(rel_file)
        input_type = raw.get("input_type") or ("text" if path.suffix.lower() == ".txt" else "pdf")
        if input_type not in {"text", "pdf"}:
            raise ValueError(f"Eval-Case {rel_file!r}: input_type muss 'text' oder 'pdf' sein.")

        expected = {
            "sender_any": _expectation_values(raw, "sender_any"),
            "content_any": _expectation_values(raw, "content_any"),
            "date": str(raw.get("date", "") or ""),
        }
        if not any((expected["sender_any"], expected["content_any"], expected["date"])):
            raise ValueError(f"Eval-Case {rel_file!r}: keine auswertbaren Erwartungen.")

        cases.append({
            "id": str(raw.get("id") or path.stem),
            "path": path,
            "input_type": input_type,
            "expected": expected,
            "date_source": raw.get("date_source", ""),
            "cloud_safe": bool(raw.get("cloud_safe", cloud_safe)),
        })

    return cases


def _load_synthetic_eval_cases(corpus_dir: Path) -> list[dict]:
    """Bestehenden synthetischen PDF-Corpus in das allgemeine Eval-Case-Format bringen."""
    return [
        {
            "id": fname,
            "path": corpus_dir / fname,
            "input_type": "pdf",
            "expected": {
                "sender_any": list(expected["sender_any"]),
                "content_any": list(expected["content_any"]),
                "date": expected["date"],
            },
            "date_source": "document",
            "cloud_safe": True,
        }
        for fname, expected in TEST_EXPECTATIONS.items()
        if (corpus_dir / fname).exists()
    ]


def load_eval_cases(corpus_dir: Path) -> list[dict]:
    """Eval-Cases laden: expectations.json wenn vorhanden, sonst synthetische PDFs."""
    external_cases = _load_external_eval_cases(corpus_dir)
    if external_cases is not None:
        return external_cases
    return _load_synthetic_eval_cases(corpus_dir)


def _read_eval_case_text(case: dict) -> str:
    """Text fuer einen Eval-Case lesen."""
    path = case["path"]
    if case["input_type"] == "text":
        return path.read_text(encoding="utf-8")
    return extract_text(path)


def run_eval(
    corpus_dir: Path,
    models: list[str],
    blocklist: tuple[str, ...] = (),
    include_claude: bool = False,
    client: Any = None,
) -> None:
    """Extraktionsqualität mehrerer Ollama-Modelle (und optional Claude) auf einem Eval-Corpus vergleichen."""
    cases = load_eval_cases(corpus_dir)
    if not cases:
        print(f"No eval cases found in {corpus_dir}.")
        print("Generate synthetic PDFs or provide expectations.json for text/PDF corpora.")
        return

    print(f"Eval corpus: {len(cases)} case(s) in {_safe_corpus_label(corpus_dir)}")
    print()

    configs: list[tuple[str, str]] = [(m, "ollama") for m in models]
    if include_claude:
        if all(case.get("cloud_safe") for case in cases):
            client = client or create_anthropic_client()
            configs.append(("claude-haiku-4-5-20251001", "claude"))
        else:
            print("Skipping Claude eval: corpus is not marked cloud_safe.")
    if not configs:
        print("No eval models selected.")
        return

    all_results: dict[str, list[dict]] = {}

    for model_name, engine in configs:
        label = f"{model_name} ({engine})"
        print(f"▶  {label}")
        results: list[dict] = []

        for case in cases:
            case_path = case["path"]
            expected = case["expected"]
            try:
                raw_text = _read_eval_case_text(case)
                if not raw_text.strip():
                    results.append({"file": case_path.name, "error": "no-text", "time_s": 0.0, "cost_chf": 0.0})
                    print(f"   ⚠ {case_path.name}: no extractable text")
                    continue

                redacted_text, _ = redact(raw_text, blocklist)
                content_block = {"type": "text", "text": redacted_text}

                t0 = time.time()
                if engine == "claude" and client is not None:
                    info, usage = analyze_claude(client, content_block)
                    cost_chf = calc_cost_chf(usage.input_tokens, usage.output_tokens) if usage else 0.0
                else:
                    date_hint = pre_extract_date(redacted_text)
                    info, _ = analyze_ollama(content_block, model=model_name, date_hint=date_hint)
                    cost_chf = 0.0
                elapsed = time.time() - t0

                score = _score_eval_result(info, expected)
                sender_ok  = score["sender_ok"]
                content_ok = score["content_ok"]
                date_ok    = score["date_ok"]
                all_ok     = bool(score["all_ok"])

                s = "–" if sender_ok is None else ("✓" if sender_ok else "✗")
                co = "–" if content_ok is None else ("✓" if content_ok else "✗")
                d = "–" if date_ok is None else ("✓" if date_ok else "✗")
                a = "✓" if all_ok else "✗"
                print(f"   {a} {case_path.name:<42} sender={s}  content={co}  date={d}  conf={info.confidence}  {elapsed:.1f}s")

                results.append({
                    "file": case_path.name,
                    "sender_ok": sender_ok,
                    "content_ok": content_ok,
                    "date_ok": date_ok,
                    "all_ok": all_ok,
                    "confidence": info.confidence,
                    "time_s": elapsed,
                    "cost_chf": cost_chf,
                    "error": None,
                })

            except Exception as exc:
                results.append({"file": case_path.name, "error": str(exc)[:100], "time_s": 0.0, "cost_chf": 0.0})
                print(f"   ✗ {case_path.name}: ERROR — {exc}")

        n_ok  = sum(1 for r in results if r.get("all_ok"))
        n_err = sum(1 for r in results if r.get("error"))
        print(f"   → {n_ok}/{len(results)} all-fields correct, {n_err} error(s)\n")
        all_results[label] = results

    _write_eval_report(corpus_dir, all_results)


def _write_eval_report(corpus_dir: Path, all_results: dict[str, list[dict]]) -> None:
    """Eval-Vergleichsbericht als Markdown schreiben (keine Dateinamen, nur Metriken)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    first_results = next(iter(all_results.values()), [])
    n_evaluated = sum(1 for r in first_results if not r.get("error"))
    corpus_label = _safe_corpus_label(corpus_dir)

    def pct_for(results: list[dict], key: str) -> float | None:
        vals = [r.get(key) for r in results if r.get("error") is None and r.get(key) is not None]
        if not vals:
            return None
        return sum(1 for v in vals if v) / len(vals) * 100

    def pct_text(value: float | None, bold: bool = False) -> str:
        if value is None:
            return "—"
        text = f"{value:.0f}%"
        return f"**{text}**" if bold else text

    lines = [
        "# dok-namer Eval Report",
        "",
        f"Generated: {now}",
        f"Corpus: `{corpus_label}` ({n_evaluated}/{len(first_results)} cases evaluated successfully)",
        "",
        "## Accuracy",
        "",
        "| Model | Sender | Content | Date | Expected Fields | Errors | Avg time |",
        "|-------|--------|---------|------|-------|--------|----------|",
    ]

    for label, results in all_results.items():
        ok = [r for r in results if r.get("error") is None]
        n = len(ok)
        if n == 0:
            lines.append(f"| `{label}` | — | — | — | — | {len(results)} | — |")
            continue
        sender_pct  = pct_for(results, "sender_ok")
        content_pct = pct_for(results, "content_ok")
        date_pct    = pct_for(results, "date_ok")
        all_pct     = sum(1 for r in ok if r.get("all_ok")) / len(results) * 100
        avg_time    = sum(r["time_s"] for r in ok) / n
        n_err       = len(results) - n
        lines.append(
            f"| `{label}` | {pct_text(sender_pct)} | {pct_text(content_pct)} | {pct_text(date_pct)} "
            f"| {pct_text(all_pct, bold=True)} | {n_err} | {avg_time:.1f}s |"
        )

    lines += [
        "",
        "## Confidence Calibration",
        "",
        "_When the model says 'high' confidence — how often is it actually correct?_",
        "",
        "| Model | High-conf rate | When high → correct | When low → correct |",
        "|-------|---------------|---------------------|---------------------|",
    ]

    for label, results in all_results.items():
        ok = [r for r in results if r.get("error") is None]
        if not ok:
            lines.append(f"| `{label}` | — | — | — |")
            continue
        high = [r for r in ok if r.get("confidence") == "high"]
        low  = [r for r in ok if r.get("confidence") != "high"]
        high_rate    = len(high) / len(ok) * 100
        high_correct = (sum(1 for r in high if r.get("all_ok")) / len(high) * 100) if high else 0.0
        low_correct  = (sum(1 for r in low  if r.get("all_ok")) / len(low)  * 100) if low  else 0.0
        lines.append(
            f"| `{label}` | {high_rate:.0f}% | {high_correct:.0f}% | {low_correct:.0f}% |"
        )

    for label, results in all_results.items():
        if "claude" in label:
            ok = [r for r in results if r.get("error") is None]
            if ok:
                total_cost = sum(r.get("cost_chf", 0.0) for r in ok)
                avg_cost   = total_cost / len(ok)
                lines += [
                    "",
                    "## Cost (Claude)",
                    "",
                    "| | |",
                    "|---|---|",
                    f"| Total | CHF {total_cost:.4f} |",
                    f"| Avg per file | CHF {avg_cost:.5f} |",
                ]
            break

    lines += [
        "",
        "---",
        "_Aggregated metrics only — no filenames or document content._",
        "",
    ]

    report_path = PROJECT_DIR / "dok-namer-eval-report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Eval report written: {report_path}")


# Terminal statuses: Dateien mit diesen Statuses werden bei Resume übersprungen
TERMINAL_STATUSES = {"renamed", "unrecognized", "review"}

# Thread-Lock für den Log-Schreibzugriff
_log_lock = threading.Lock()

# Maximale Länge des Dateinamens inklusive .pdf-Endung.
MAX_FILENAME_LENGTH = 180

# Retry-Strategie für temporäre Claude-Fehler wie Rate-Limits.
CLAUDE_MAX_ATTEMPTS = 5
CLAUDE_BACKOFF_SECONDS = (5, 10, 20, 40)

# Erwartete Kerndaten der synthetischen Test-PDFs. Die Auswertung bleibt
# aggregiert; Dateinamen und Vorschläge landen nicht im teilbaren Report.
TEST_EXPECTATIONS = {
    "scan_001_ekz_rechnung.pdf": {
        "sender_any": ("ekz", "elektrizitaetswerke"),
        "content_any": ("stromrechnung",),
        "date": "20251115",
    },
    "scan_002_swisscom_rechnung.pdf": {
        "sender_any": ("swisscom",),
        "content_any": ("rechnung",),
        "date": "20251001",
    },
    "scan_003_zkb_kontoauszug.pdf": {
        "sender_any": ("zkb", "zuercher-kantonalbank"),
        "content_any": ("kontoauszug",),
        "date": "20250930",
    },
    "scan_004_helsana_praemie.pdf": {
        "sender_any": ("helsana",),
        "content_any": ("praemienrechnung", "pramienrechnung"),
        "date": "20251120",
    },
    "scan_005_steueramt_kanton.pdf": {
        "sender_any": ("steueramt",),
        "content_any": ("steuerrechnung",),
        "date": "20260328",
    },
    "scan_006_gemeinde_mahnung.pdf": {
        "sender_any": ("uster", "steuerverwaltung"),
        "content_any": ("mahnung",),
        "date": "20251203",
    },
    "scan_007_axa_versicherung.pdf": {
        "sender_any": ("axa",),
        "content_any": ("praemienrechnung", "pramienrechnung"),
        "date": "20260101",
    },
    "scan_008_migros_kreditkarte.pdf": {
        "sender_any": ("migros-bank",),
        "content_any": ("kreditkartenabrechnung",),
        "date": "20251130",
    },
    "scan_009_zurich_auto.pdf": {
        "sender_any": ("zurich",),
        "content_any": ("motorfahrzeug", "praemienrechnung", "pramienrechnung"),
        "date": "20251015",
    },
    "scan_010_postfinance_kontoauszug.pdf": {
        "sender_any": ("postfinance",),
        "content_any": ("kontoauszug",),
        "date": "20251231",
    },
    "scan_011_horgen_wasser.pdf": {
        "sender_any": ("horgen",),
        "content_any": ("wasserrechnung",),
        "date": "20251215",
    },
    "scan_012_raiffeisen_hypothek.pdf": {
        "sender_any": ("raiffeisen",),
        "content_any": ("hypothekar", "zinsabrechnung"),
        "date": "20251001",
    },
    "scan_013_ahv_beitrag.pdf": {
        "sender_any": ("ausgleichskasse",),
        "content_any": ("beitragsrechnung",),
        "date": "20260115",
    },
    "scan_014_sbb_ga.pdf": {
        "sender_any": ("sbb",),
        "content_any": ("generalabonnement", "erneuerungsrechnung"),
        "date": "20251115",
    },
    "scan_015_bildung_schulgeld.pdf": {
        "sender_any": ("bildungsdirektion",),
        "content_any": ("schulgeldrechnung",),
        "date": "20250820",
    },
    "scan_016_css_leistungsabrechnung.pdf": {
        "sender_any": ("css",),
        "content_any": ("leistungsabrechnung",),
        "date": "20251105",
    },
    "scan_017_kuesenacht_kehricht.pdf": {
        "sender_any": ("kuesnacht", "kusnacht", "gemeindeverwaltung"),
        "content_any": ("abfallgebuehrenrechnung", "abfallgebuhrenrechnung"),
        "date": "20251130",
    },
    "scan_018_pksbb_vorsorgeausweis.pdf": {
        "sender_any": ("pensionskasse", "sbb"),
        "content_any": ("vorsorgeausweis",),
        "date": "20251231",
    },
    "scan_019_wincasa_miete.pdf": {
        "sender_any": ("wincasa",),
        "content_any": ("mietzinsrechnung",),
        "date": "20251125",
    },
    "scan_020_sva_basel_fahrzeugsteuer.pdf": {
        "sender_any": ("strassenverkehrsamt", "basel"),
        "content_any": ("motorfahrzeugsteuer", "fahrzeugsteuer"),
        "date": "20251205",
    },
}


def load_log(log_path: Path) -> set[str]:
    """Log einlesen; gibt Menge der Dateinamen mit terminalem Status zurück."""
    done: set[str] = set()
    if not log_path.exists():
        return done
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("status") in TERMINAL_STATUSES:
                    done.add(entry["file"])
            except json.JSONDecodeError:
                pass
    return done


def append_log(log_path: Path, entry: dict) -> None:
    """Einen JSON-Lines-Eintrag thread-sicher ans Log anhängen."""
    with _log_lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class DocumentInfo(BaseModel):
    """Strukturierte Felder aus dem Dokument."""
    sender:     str  # Absender-Organisation, keine Leerzeichen (Bindestriche)
    content:    str  # Kurzes Dokumenttyp-Label, keine Leerzeichen (Bindestriche)
    date:       str  # Ausstellungsdatum YYYYMMDD oder "unknown"
    confidence: str  # "high" wenn alle Felder klar, sonst "low"


def extract_text(path: Path) -> str:
    """Gesamten Text aus einem PDF extrahieren. Leerstring bei reinen Scan-PDFs."""
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def redact(text: str, blocklist: tuple[str, ...] = ()) -> tuple[str, dict[str, int]]:
    """
    Alle Redaktionsmuster auf den Text anwenden (in Memory), danach Blocklist.
    Gibt (redacted_text, {label: count}) zurück.
    """
    counts: dict[str, int] = {}
    for pattern, label in REDACTION_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            counts[label] = len(matches)
            text = pattern.sub(label, text)
    # Optionale Blocklist: exakte Ersetzung (case-insensitive) durch [NAME]
    for name in blocklist:
        pat = re.compile(re.escape(name), re.IGNORECASE)
        matches = pat.findall(text)
        if matches:
            counts["[NAME]"] = counts.get("[NAME]", 0) + len(matches)
            text = pat.sub("[NAME]", text)
    return text, counts


def prepare_document(path: Path, blocklist: tuple[str, ...] = ()) -> tuple[dict, dict[str, int], bool]:
    """
    Content-Block für die API vorbereiten, mit In-Memory-Redaktion und Blocklist.
    Gibt (content_block, redaction_counts, is_scanned) zurück.
    """
    raw_text = extract_text(path)

    if raw_text.strip():
        redacted_text, counts = redact(raw_text, blocklist)
        block = {"type": "text", "text": redacted_text}
        return block, counts, False
    else:
        block = {"type": "scan", "path": str(path)}
        return block, {}, True


def analyze_claude(
    client: Any,
    content_block: dict,
) -> tuple[DocumentInfo, Any]:
    """Content-Block an Claude senden und DocumentInfo + Usage zurückgeben."""
    last_error: Exception | None = None
    for attempt in range(CLAUDE_MAX_ATTEMPTS):
        try:
            response = client.messages.parse(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": [
                        content_block,
                        {"type": "text", "text": EXTRACTION_PROMPT},
                    ],
                }],
                output_format=DocumentInfo,
            )
            return response.parsed_output, response.usage
        except Exception as e:
            last_error = e
            if attempt == CLAUDE_MAX_ATTEMPTS - 1 or not is_retryable_error(e):
                raise
            time.sleep(retry_delay_seconds(e, attempt))

    raise last_error


def analyze_ollama(
    content_block: dict,
    model: str = "llava",
    date_hint: str | None = None,
) -> tuple[DocumentInfo, None]:
    """Content-Block an ein lokales Ollama-Modell senden.

    model: beliebiges Ollama-Modell (Standard: llava für vision+text).
    date_hint: deterministisch vorextrahiertes Datum (YYYYMMDD) aus pre_extract_date();
               wird dem Modell als Hinweis übergeben, damit es das richtige Datum wählt.
    """
    try:
        import base64
        import ollama as ollama_lib
    except ImportError:
        print("  Fehler: 'ollama' Python-Bibliothek nicht installiert. Ausführen: pip install ollama")
        raise

    hint_line = (
        f"\nNote: Regex pre-extraction found '{date_hint}' as a likely issuance date "
        f"(from the 'Ort, DD. Monat YYYY' pattern). Use this unless the document type "
        f"clearly requires a different date (e.g. statement period end).\n"
        if date_hint else ""
    )

    json_prompt = (
        EXTRACTION_PROMPT
        + hint_line
        + '\nRespond with a JSON object using exactly these keys: '
        '{"sender": "...", "content": "...", "date": "YYYYMMDD or unknown", "confidence": "high or low"}'
    )

    if content_block["type"] == "text":
        messages = [{
            "role": "user",
            "content": json_prompt + "\n\nDocument text:\n" + content_block["text"],
        }]
    elif content_block["type"] == "scan":
        with open(content_block["path"], "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
        messages = [{
            "role": "user",
            "content": json_prompt,
            "images": [image_data],
        }]
    else:
        raise ValueError(f"Unbekannter Content-Block-Typ: {content_block['type']}")

    try:
        # format="json" zwingt das Modell zu gültigem JSON-Output (kein Regex-Parsing nötig)
        response = ollama_lib.chat(model=model, messages=messages, format="json")
    except Exception as e:
        error_msg = str(e)
        if "connection" in error_msg.lower() or "refused" in error_msg.lower():
            print("  Fehler: Ollama läuft nicht. Starten mit: ollama serve")
        elif "model" in error_msg.lower() and "not found" in error_msg.lower():
            print(f"  Fehler: Modell '{model}' nicht gefunden. Laden mit: ollama pull {model}")
        else:
            print(f"  Fehler bei Kommunikation mit Ollama: {e}")
        raise

    raw = response["message"]["content"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: Regex-Extraktion falls format="json" nicht unterstützt wird
        json_match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if not json_match:
            raise ValueError(f"Kein JSON-Objekt in Ollama-Antwort: {raw!r}")
        data = json.loads(json_match.group())

    # Deterministischer Datum-Override: pre_extract_date hat Vorrang wenn LLM «unknown» zurückgibt
    extracted_date = str(data.get("date", "unknown"))
    if date_hint and (extracted_date == "unknown" or not re.match(r'^\d{8}$', extracted_date)):
        extracted_date = date_hint

    info = DocumentInfo(
        sender=str(data.get("sender", "unknown")),
        content=str(data.get("content", "unknown")),
        date=extracted_date,
        confidence=str(data.get("confidence", "low")),
    )
    return info, None


# Muster zur Verifikation nach LLM-Anonymisierung
REGEX_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern]] = [
    # AHV: strukturiertes Format ist spezifisch genug
    ("AHV",
     re.compile(r'756\.\d{4}\.\d{4}\.\d{2}')),
    # Nur Schweizer Mobilnummern — inland: 07[5-9] + 3+2+2 Stellen
    # international: +41/0041 + 7[5-9] + 3+2+2 Stellen
    ("Telefon (CH)",
     re.compile(
         r'(\+41|0041)[\s\-.]?7[5-9][\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}'
         r'|(?<!\d)07(5|6|7|8|9)[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}'
     )),
]


def verify_with_regex(text: str) -> list[tuple[str, str]]:
    """
    Anonymisierten Text auf bekannte sensitive Muster prüfen.
    Gibt Liste von (label, first_match_snippet) zurück; leer = sauber.
    """
    hits = []
    for label, pattern in REGEX_SENSITIVE_PATTERNS:
        m = pattern.search(text)
        if m:
            hits.append((label, m.group(0)))
    return hits


def anonymize_with_llama(text: str) -> tuple[str, dict[str, int]]:
    """
    Rohen PDF-Text an llama3.2 via Ollama zur LLM-Anonymisierung senden.
    Gibt (anonymized_text, {placeholder: count}) zurück.
    """
    try:
        import ollama as ollama_lib
    except ImportError:
        print("  Fehler: 'ollama' Python-Bibliothek nicht installiert. Ausführen: pip install ollama")
        raise

    prompt = (
        "Anonymize the following document text by replacing sensitive personal information "
        "with generic placeholders. Use exactly these placeholders:\n"
        "  [NAME]      for names of natural persons (first names, last names, full names)\n"
        "  [KONTO]     for bank account numbers and IBANs\n"
        "  [AHV]       for Swiss AHV/social security numbers\n"
        "  [BETRAG]    for monetary amounts and prices\n"
        "  [EMAIL]     for email addresses\n"
        "  [TELEFON]   for phone numbers\n"
        "  [ADRESSE]   for postal street addresses (street name + number + postcode + city)\n"
        "\n"
        "Do NOT replace or modify the following — leave them exactly as they appear:\n"
        "  - Dates in any format (e.g. 30.09.2025, 2025-09-30, 30.09.25, September 2025)\n"
        "  - Company names and organization names (e.g. Swisscom AG, Stadtwerke München)\n"
        "  - Document titles and document types (e.g. Rechnung, Kontoauszug, Mahnung)\n"
        "  - Geographic place names: cities, cantons, regions, countries\n"
        "\n"
        "Return ONLY the anonymized text with no explanation, preamble, or commentary.\n\n"
        "Document text:\n"
        + text
    )

    try:
        response = ollama_lib.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        error_msg = str(e)
        if "connection" in error_msg.lower() or "refused" in error_msg.lower():
            print("  Fehler: Ollama läuft nicht. Starten mit: ollama serve")
        elif "model" in error_msg.lower() and "not found" in error_msg.lower():
            print("  Fehler: Modell 'llama3.2' nicht gefunden. Laden mit: ollama pull llama3.2")
        else:
            print(f"  Fehler bei Kommunikation mit Ollama: {e}")
        raise

    anonymized = response["message"]["content"]

    counts: dict[str, int] = {}
    for m in re.finditer(r'\[[A-ZÄÖÜ]+\]', anonymized):
        label = m.group(0)
        counts[label] = counts.get(label, 0) + 1

    return anonymized, counts


def analyze_hybrid(
    client: Any,
    path: Path,
    blocklist: tuple[str, ...] = (),
) -> tuple[DocumentInfo | None, Any | None, dict[str, int], str, str, dict[str, float]]:
    """
    Hybrid-Engine: llama3.2 anonymisiert (Pass 1), Regex verifiziert (Pass 2), Claude extrahiert.
    Blocklist wird VOR llama3.2 auf den Rohtext angewendet.
    Gibt (info, usage, placeholder_counts, verify_verdict, verify_reason, timings) zurück.
    timings-Keys: "anonymize", "regex", "claude" (claude fehlt bei REVIEW).
    info und usage sind None bei verify_verdict == "REVIEW".
    """
    raw_text = extract_text(path)
    if not raw_text.strip():
        raise ValueError("Hybrid-Engine benötigt extrahierbaren Text; Scan-PDFs werden nicht unterstützt.")

    # Blocklist-Einträge vor LLM-Anonymisierung ersetzen
    for name in blocklist:
        raw_text = re.sub(re.escape(name), "[NAME]", raw_text, flags=re.IGNORECASE)

    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    anonymized, placeholder_counts = anonymize_with_llama(raw_text)
    timings["anonymize"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    regex_hits = verify_with_regex(anonymized)
    timings["regex"] = time.perf_counter() - t0

    if regex_hits:
        labels = ", ".join(label for label, _ in regex_hits)
        return None, None, placeholder_counts, "REVIEW", labels, timings

    t0 = time.perf_counter()
    content_block = {"type": "text", "text": anonymized}
    info, usage = analyze_claude(client, content_block)
    timings["claude"] = time.perf_counter() - t0

    return info, usage, placeholder_counts, "CLEAN", "", timings


def process_file(
    client: Any | None,
    path: Path,
    done_dir: Path,
    unrecognized_dir: Path,
    review_dir: Path | None,
    error_dir: Path,
    engine: str,
    auto: bool = False,
    lines: list[str] | None = None,
    blocklist: tuple[str, ...] = (),
    categories: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
) -> tuple[str, float, float, str, str, dict[str, float], str, str]:
    """
    Redaktion, Analyse, Routing, Umbenennung/Verschiebung einer Datei.
    Gibt (status, cost_chf, elapsed_s, suggested_name, confidence, phase_timings, error_reason, done_category) zurück.
    status: 'renamed' | 'unrecognized' | 'review' | 'skipped'
    confidence: 'high' | 'low' | 'n/a'
    phase_timings: {'anonymize': s, 'regex': s, 'claude': s} — nur bei hybrid, sonst {}
    Wenn lines übergeben wird, werden Ausgaben darin gepuffert statt direkt gedruckt.
    """
    def emit(msg: str = "") -> None:
        if lines is not None:
            lines.append(msg)
        else:
            print(msg)

    def technical_skip(reason: str, cost: float = 0.0, elapsed: float = 0.0) -> tuple[str, float, float, str, str, dict[str, float], str, str]:
        emit(f"  → Moved unchanged to 'error/'")
        dest = unique_original_destination(error_dir, path.name)
        path.rename(dest)
        return "skipped", cost, elapsed, path.name, "n/a", phase_timings, reason, ""

    emit(f"\n{'─' * 50}")
    emit(f"File: {path.name}")
    emit(f"  Analysing... (Engine: {engine})")

    phase_timings: dict[str, float] = {}

    if engine == "hybrid":
        try:
            info, usage, placeholder_counts, verify_verdict, verify_reason, timings = \
                analyze_hybrid(client, path, blocklist=blocklist)
        except Exception as e:
            emit(f"  Fehler bei Analyse: {e}")
            return technical_skip(f"analyse:{classify_error(e)}")

        phase_timings = timings
        t_anonymize = timings.get("anonymize", 0.0)
        t_regex     = timings.get("regex", 0.0)
        t_claude    = timings.get("claude", 0.0)
        elapsed     = t_anonymize + t_regex + t_claude

        if placeholder_counts:
            summary = ", ".join(f"{count}× {label}" for label, count in placeholder_counts.items())
            total = sum(placeholder_counts.values())
            emit(f"  Anonymisierungen (llama3.2): {summary} (total: {total})  [{t_anonymize:.1f}s]")
        else:
            emit(f"  Anonymisierungen (llama3.2): keine  [{t_anonymize:.1f}s]")

        emit(f"  Verifikation (regex):        {verify_verdict}"
             + (f" – {verify_reason}" if verify_reason else "")
             + f"  [{t_regex:.3f}s]")

        if verify_verdict == "REVIEW":
            emit(f"  Gesamtzeit: {elapsed:.1f}s")
            emit(f"  → Moved unchanged to 'review/'")
            dest = unique_original_destination(review_dir, path.name)
            path.rename(dest)
            return "review", 0.0, elapsed, path.name, "n/a", phase_timings, "", ""

        cost = calc_cost_chf(usage.input_tokens, usage.output_tokens)
        emit(f"  Tokens: {usage.input_tokens} in / {usage.output_tokens} out  |  "
             f"Kosten: llama3.2 (lokal) + Claude Haiku (CHF {cost:.4f})  [{t_claude:.1f}s]")
        emit(f"  Gesamtzeit: {elapsed:.1f}s")
    else:
        try:
            content_block, redaction_counts, is_scanned = prepare_document(path, blocklist=blocklist)
        except Exception as e:
            emit(f"  Fehler beim Lesen: {e}")
            return technical_skip(f"lesen:{classify_error(e)}")

        if is_scanned:
            if engine == "claude":
                emit("  Warning: Scanned document – cloud upload without redaction blocked")
                emit("  → Moved unchanged to 'review/'")
                dest = unique_original_destination(review_dir, path.name)
                path.rename(dest)
                return "review", 0.0, 0.0, path.name, "n/a", phase_timings, "", ""
            emit("  Warning: Scanned document – llava required for scans without extractable text")
        elif redaction_counts:
            summary = ", ".join(f"{count}× {label}" for label, count in redaction_counts.items())
            total = sum(redaction_counts.values())
            emit(f"  Schwärzungen: {summary} (total: {total})")
        else:
            emit("  Schwärzungen: keine")

        try:
            t0 = time.perf_counter()
            if engine == "ollama":
                date_hint = pre_extract_date(content_block.get("text", ""))
                info, usage = analyze_ollama(content_block, date_hint=date_hint)
            else:
                info, usage = analyze_claude(client, content_block)
            elapsed = time.perf_counter() - t0
        except Exception as e:
            elapsed = time.perf_counter() - t0
            emit(f"  Fehler bei Analyse: {e}")
            return technical_skip(f"analyse:{classify_error(e)}", elapsed=elapsed)

        if engine == "ollama" or usage is None:
            cost = 0.0
            emit("  Cost: CHF 0.00 (local model)")
        else:
            cost = calc_cost_chf(usage.input_tokens, usage.output_tokens)
            emit(f"  Tokens: {usage.input_tokens} in / {usage.output_tokens} out  |  Kosten: CHF {cost:.4f}")
        emit(f"  Gesamtzeit: {elapsed:.1f}s")
        phase_timings["analysis"] = elapsed

    emit(f"  Confidence: {info.confidence}")

    # Niedrige Confidence: unverändert nach unrecognized/
    if info.confidence == "low":
        uncertain = [
            field for field, val in [
                ("sender", info.sender),
                ("content", info.content),
                ("date", info.date),
            ]
            if val in ("unknown", "")
        ]
        reason = f"unklare Felder: {', '.join(uncertain)}" if uncertain else "niedrige Confidence"
        emit(f"  ⚠ Confidence niedrig ({reason})")
        emit(f"  → Moved unchanged to 'unrecognized/'")
        dest = unique_original_destination(unrecognized_dir, path.name)
        path.rename(dest)
        return "unrecognized", cost, elapsed, path.name, "low", phase_timings, "", ""

    # Hohe Confidence: Dateinamen vorschlagen
    suggested = sanitize_filename(f"{info.sender}-{info.content}-{info.date}{PDF_SUFFIX}")
    emit(f"  Vorgeschlagener Dateiname: {suggested}")

    if auto:
        final = suggested
    else:
        answer = input("  Akzeptieren? [y/n]: ").strip().lower()
        if answer == "y":
            final = suggested
        else:
            stem = input("  Neuer Name (ohne Endung): ").strip()
            if not stem:
                emit("  Kein Name eingegeben – übersprungen.")
                return "skipped", cost, elapsed, suggested, "high", phase_timings, "manual-skip", ""
            final = sanitize_filename(stem + PDF_SUFFIX)

    done_category = done_category_for_filename(final, categories)
    category_dir = done_dir / done_category
    category_dir.mkdir(exist_ok=True)
    dest = unique_destination(category_dir, final)
    path.rename(dest)
    emit(f"  → Verschoben nach: {dest}")
    return "renamed", cost, elapsed, dest.name, "high", phase_timings, "", done_category


def _fmt_eta(seconds: float) -> str:
    """Dauer in Sekunden als lesbare ETA-Zeichenkette formatieren."""
    s = int(seconds)
    if s < 60:
        return f"~{s}s"
    m, s = divmod(s, 60)
    return f"~{m}m {s:02d}s"


def write_report(
    folder: Path,
    run_entries: list[dict],
    engine: str,
    workers: int,
) -> None:
    """
    Anonymisierte Zusammenfassung als Markdown in dok-namer-report.md schreiben.
    Keine Dateinamen, keine Suggested Names — nur aggregierte Zahlen.
    """
    from collections import Counter

    report_path = folder / "dok-namer-report.md"

    status_counts  = Counter(e["status"]     for e in run_entries)
    conf_counts    = Counter(e.get("confidence", "n/a") for e in run_entries)
    category_counts = Counter(e.get("done_category", "") for e in run_entries if e.get("done_category"))
    total          = len(run_entries)
    costs          = [e["cost_chf"] for e in run_entries]
    total_cost     = sum(costs)
    times          = [e["elapsed_s"] for e in run_entries if e["elapsed_s"] > 0]
    avg_t          = sum(times) / len(times) if times else 0.0
    now_str        = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    quality        = evaluate_test_quality(run_entries)

    lines = [
        f"# dok-namer Report",
        f"",
        f"Created: {now_str}  |  Engine: `{engine}`  |  Workers: {workers}",
        f"",
        f"## Status Distribution",
        f"",
        f"| Status | Count | Share |",
        f"|--------|------:|------:|",
    ]
    for st in ["renamed", "unrecognized", "review", "skipped"]:
        n = status_counts.get(st, 0)
        pct = f"{n/total*100:.0f}%" if total else "—"
        lines.append(f"| {st} | {n} | {pct} |")
    lines += [
        f"| **Total** | **{total}** | **100%** |",
        f"",
        f"## Confidence-Verteilung",
        f"",
        f"| Confidence | Anzahl |",
        f"|------------|-------:|",
    ]
    for cv in ["high", "low", "n/a"]:
        lines.append(f"| {cv} | {conf_counts.get(cv, 0)} |")

    if category_counts:
        lines += [
            f"",
            f"## Filing Categories",
            f"",
            f"| Category | Count |",
            f"|----------|------:|",
        ]
        for category, count in sorted(category_counts.items()):
            lines.append(f"| {category} | {count} |")

    error_counts = Counter(e.get("error_reason", "") for e in run_entries if e.get("error_reason"))
    if error_counts:
        lines += [
            f"",
            f"## Error Reasons",
            f"",
            f"| Error Reason | Count |",
            f"|--------------|------:|",
        ]
        for reason, count in sorted(error_counts.items()):
            lines.append(f"| {reason} | {count} |")

    if quality:
        target = quality["target_high_conf_rate"]
        lines += [
            f"",
            f"## Test Quality",
            f"",
            f"| Metric | Value |",
            f"|--------|------:|",
            f"| Evaluated Test PDFs | {quality['evaluated']} |",
            f"| Core data matched | {quality['matches']} ({quality['match_rate']*100:.0f}%) |",
            f"| High Confidence | {quality['high_conf']} ({quality['high_conf_rate']*100:.0f}%) |",
            f"| Target High Confidence | {target*100:.0f}% |",
        ]

    lines += [
        f"",
        f"## Timing",
        f"",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| Min      | {min(times):.1f}s |" if times else "| Min | — |",
        f"| Max      | {max(times):.1f}s |" if times else "| Max | — |",
        f"| Ø        | {avg_t:.1f}s |",
        f"| Total    | {sum(times):.1f}s ({sum(times)/60:.1f} min) |",
    ]

    phase_keys = sorted({
        key
        for entry in run_entries
        for key in entry.get("phases", {}).keys()
    })
    if phase_keys:
        phase_times: dict[str, list[float]] = {k: [] for k in phase_keys}
        for e in run_entries:
            for k in phase_keys:
                v = e.get("phases", {}).get(k)
                if v is not None:
                    phase_times[k].append(v)
        lines += [
            f"",
            f"### Phasen-Breakdown",
            f"",
            f"| Phase | Min | Max | Ø | Total |",
            f"|-------|----:|----:|--:|------:|",
        ]
        for k in phase_keys:
            vals = phase_times[k]
            if vals:
                lines.append(
                    f"| {k} | {min(vals):.1f}s | {max(vals):.1f}s | "
                    f"{sum(vals)/len(vals):.1f}s | {sum(vals):.1f}s |"
                )

    lines += [
        f"",
        f"## Kosten",
        f"",
        f"| | |",
        f"|---|---|",
        f"| Claude Haiku (API) | CHF {total_cost:.4f} |",
        f"| Ø pro Datei | CHF {total_cost/total:.5f} |" if total else "| Ø pro Datei | — |",
    ]
    if engine in ("ollama", "hybrid"):
        lines.append(f"| llama3.2 / llava (lokal) | CHF 0.0000 |")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Report written: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Suggest structured filenames for all PDFs in a folder."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Folder containing the PDF files to process (omit when using --eval)",
    )
    parser.add_argument(
        "--engine",
        choices=["claude", "ollama", "hybrid"],
        default="claude",
        help="AI engine to use (default: claude)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        default=False,
        help="Unattended batch mode: automatically accept high-confidence suggestions",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel workers for --auto mode (default: 1 = sequential). "
             "Recommended: 4 for --engine claude, 2 for --engine hybrid.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to custom categories.yaml (default: categories.yaml in source folder)",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        default=False,
        help="Run model comparison eval against synthetic PDFs or an expectations.json corpus",
    )
    parser.add_argument(
        "--eval-models",
        type=str,
        default="llama3.2",
        metavar="MODELS",
        help="Comma-separated Ollama models to evaluate (default: llama3.2). "
             "Example: --eval-models llama3.2,qwen2.5:3b,mistral:7b",
    )
    parser.add_argument(
        "--eval-claude",
        action="store_true",
        default=False,
        help="Include claude engine as a comparison point in --eval",
    )
    parser.add_argument(
        "--eval-corpus",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to eval corpus directory (default: test-scans/ next to this script)",
    )
    args = parser.parse_args()

    if args.eval:
        corpus_dir = args.eval_corpus or (PROJECT_DIR / "test-scans")
        models = [m.strip() for m in args.eval_models.split(",") if m.strip()]
        blocklist = load_blocklist()
        run_eval(corpus_dir, models, blocklist=blocklist, include_claude=args.eval_claude)
        return

    if args.folder is None:
        parser.error("folder is required (or use --eval for model comparison mode)")

    categories = load_categories(args.config)
    folder  = Path(args.folder)
    engine  = args.engine
    auto    = args.auto
    workers = max(1, args.workers)

    if not auto and workers > 1:
        print("Note: --workers > 1 only takes effect in --auto mode.")
        workers = 1

    if not folder.is_dir():
        print(f"Fehler: kein Verzeichnis: {folder}")
        sys.exit(1)

    all_pdfs = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() == PDF_SUFFIX
    )

    if not all_pdfs:
        print(f"No PDF files found in {folder}.")
        sys.exit(0)

    log_path = folder / "dok-namer-log.jsonl"
    already_done = load_log(log_path)
    pdfs = all_pdfs
    stale_log_matches = [p for p in all_pdfs if p.name in already_done]
    if stale_log_matches:
        print(
            f"Note: {len(stale_log_matches)} file(s) are still in the source folder despite a terminal log status "
            "and will be processed again."
        )

    done_dir          = folder / "done"
    unrecognized_dir  = folder / "unrecognized"
    error_dir         = folder / "error"
    done_dir.mkdir(exist_ok=True)
    unrecognized_dir.mkdir(exist_ok=True)
    error_dir.mkdir(exist_ok=True)

    review_dir = None
    if engine in ("claude", "hybrid"):
        review_dir = folder / "review"
        review_dir.mkdir(exist_ok=True)

    total_in_batch = len(pdfs)
    print(f"Found: {len(all_pdfs)} PDF(s) in {folder}  ({total_in_batch} to process)")
    print(f"Engine: {engine}" + ("  [Auto mode]" if auto else "")
          + (f"  [Workers: {workers}]" if auto and workers > 1 else ""))

    client   = create_anthropic_client() if engine in ("claude", "hybrid") else None
    blocklist = load_blocklist()
    if blocklist:
        print(f"Blocklist: {len(blocklist)} entries loaded from redact-names.txt")

    renamed      = 0
    unrecognized = 0
    review       = 0
    skipped      = 0
    total_cost    = 0.0
    elapsed_times: list[float] = []
    run_entries:   list[dict]  = []
    print_lock = threading.Lock()

    def _process_one(i_pdf: tuple[int, Path]) -> tuple[str, float, float, str, str, dict, str, str, str]:
        """Einzelne Datei verarbeiten; gibt Resultatdaten und Dateiname zurück."""
        i, pdf = i_pdf
        lines: list[str] = []
        if auto:
            lines.append(f"\nVerarbeite {i}/{total_in_batch}: {pdf.name}")
        t_start = time.perf_counter()
        result, cost, inner_elapsed, suggested, confidence, phase_timings, error_reason, done_category = process_file(
            client, pdf, done_dir, unrecognized_dir, review_dir, error_dir, engine,
            auto=auto, lines=lines, blocklist=blocklist, categories=categories,
        )
        elapsed = time.perf_counter() - t_start
        with print_lock:
            for ln in lines:
                print(ln)
        return result, cost, elapsed, suggested, confidence, phase_timings, error_reason, done_category, pdf.name

    if workers > 1:
        # Paralleler Modus
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process_one, (i, pdf)): pdf
                for i, pdf in enumerate(pdfs, 1)
            }
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                result, cost, elapsed, suggested, confidence, phase_timings, error_reason, done_category, fname = future.result()
                completed += 1
                total_cost += cost
                elapsed_times.append(elapsed)

                entry = {
                    "file":       fname,
                    "status":     result,
                    "suggested":  suggested,
                    "confidence": confidence,
                    "engine":     engine,
                    "cost_chf":   round(cost, 6),
                    "elapsed_s":  round(elapsed, 1),
                    "phases":     {k: round(v, 2) for k, v in phase_timings.items()},
                    "error_reason": error_reason,
                    "done_category": done_category,
                    "timestamp":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                }
                append_log(log_path, entry)
                run_entries.append(entry)

                if result == "renamed":          renamed      += 1
                elif result == "unrecognized":  unrecognized += 1
                elif result == "review":        review       += 1
                else:                           skipped      += 1

                if completed < total_in_batch:
                    avg = sum(elapsed_times) / len(elapsed_times)
                    remaining = avg * (total_in_batch - completed)
                    print(f"  [{completed}/{total_in_batch}] ETA: {_fmt_eta(remaining)} remaining")
    else:
        # Sequenzieller Modus (Original-Verhalten)
        for i, pdf in enumerate(pdfs, 1):
            result, cost, elapsed, suggested, confidence, phase_timings, error_reason, done_category, fname = \
                _process_one((i, pdf))
            total_cost += cost
            elapsed_times.append(elapsed)

            entry = {
                "file":       fname,
                "status":     result,
                "suggested":  suggested,
                "confidence": confidence,
                "engine":     engine,
                "cost_chf":   round(cost, 6),
                "elapsed_s":  round(elapsed, 1),
                "phases":     {k: round(v, 2) for k, v in phase_timings.items()},
                "error_reason": error_reason,
                "done_category": done_category,
                "timestamp":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            }
            append_log(log_path, entry)
            run_entries.append(entry)

            if result == "renamed":          renamed      += 1
            elif result == "unrecognized":  unrecognized += 1
            elif result == "review":        review       += 1
            else:                           skipped      += 1

            if auto and i < total_in_batch:
                avg = sum(elapsed_times) / len(elapsed_times)
                remaining = avg * (total_in_batch - i)
                print(f"  ETA: {_fmt_eta(remaining)} remaining")

    # Summary
    processed    = len(pdfs)
    total_elapsed = sum(elapsed_times)
    print(f"\n{'═' * 50}")
    print(f"Summary: {processed} file(s) processed")
    print(f"  Renamed             : {renamed}")
    print(f"  Unrecognized        : {unrecognized}")
    if review_dir is not None:
        print(f"  Review              : {review}")
    print(f"  Skipped             : {skipped}")
    if engine == "ollama":
        print(f"  Total API cost      : CHF 0.00 (local model)")
    elif engine == "hybrid":
        print(f"  Total API cost      : llama3.2 (local) + Claude Haiku (CHF {total_cost:.4f})")
    else:
        print(f"  Total API cost      : CHF {total_cost:.4f}")
    if elapsed_times:
        avg = total_elapsed / len(elapsed_times)
        print(f"  Avg time per file   : {avg:.1f}s  (total: {total_elapsed:.1f}s)")
    quality = evaluate_test_quality(run_entries)
    if quality:
        print(f"  Test quality        : {quality['matches']}/{quality['evaluated']} core data matched")
        print(f"  High Confidence     : {quality['high_conf_rate']*100:.0f}%  (Target: 90%)")
    if auto:
        print(f"  Log                : {log_path}")
        write_report(folder, run_entries, engine, workers)


if __name__ == "__main__":
    main()
