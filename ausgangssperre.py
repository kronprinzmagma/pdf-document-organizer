"""Ausgangssperre: letzte harte Pruefung jedes Cloud-Aufrufs vor dem Senden.

dok-namer verarbeitet Behoerdenpost, Rechnungen und Kontoauszuege. Vor jedem
Claude-Aufruf laeuft die Schwaerzung (``redact`` bzw. llama3.2 plus Regex).
Danach duerfen geschuetzte Daten nicht mehr im Text stehen. Die Sperre prueft
das unabhaengig ein letztes Mal, direkt vor ``client.messages.parse``:

- AHV-Nummern (756.xxxx.xxxx.xx, auch mit Leerzeichen/Bindestrichen oder ohne Trenner)
- IBAN (mit gueltiger Pruefziffer)
- Kreditkartennummern (Luhn-gueltig)
- Geburtsdaten (Datum mit Bezeichnung wie «Geburtsdatum», «geboren am», «Date of Birth»)
- Secrets und API-Keys (bekannte Formate sowie der Wert von ANTHROPIC_API_KEY)
- eine lokal gepflegte Verbotsliste (``ausgangssperre.local.yaml`` neben
  ``dok_namer.py``, gitignored; Vorlage ``ausgangssperre.example.yaml``)
- Nicht-Text-Inhalte (Bild, PDF): an die Cloud geht nur geschwaerzter Text.
  Bilder kann die Sperre nicht lesen, darum werden sie gar nicht durchgelassen.

Ein Fund heisst: die Schwaerzung hat versagt. Standard ist Abbrechen, nicht
still Umschreiben. Die Fehlermeldung nennt nur die Art des Funds und die
Nachricht, nie den Wert, damit er weder im Terminal noch im Log landet.

Geprueft wird eine Normalform des Texts (NFKC, ohne unsichtbare Formatzeichen,
jedes Unicode-Leerzeichen als Leerzeichen), damit geschuetzte Leerzeichen,
Vollbreiten-Ziffern oder Kleinschreibung nichts verstecken.

Format der Verbotsliste wie in cv-tailor (``verboten`` / ``erlaubt``), damit
dieselbe Liste in beide Repos kopiert werden kann.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

VERBOTSLISTE_PFAD = Path(__file__).parent / "ausgangssperre.local.yaml"
VERBOTSLISTE_ENV = "DOK_NAMER_AUSGANGSSPERRE_LISTE"
# Werte dieser Variablen gehen nie an ein Modell, egal in welchem Format.
SECRET_ENV_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
_MIN_LAENGE_EINTRAG = 4

ART_NICHT_TEXT = "Nicht-Text-Inhalt (Bild/PDF)"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fund:
    """Ein Fund ohne Wert: nur Art und Fundort."""

    art: str
    nachricht: int  # Index in der messages-Liste
    rolle: str


class AusgangGesperrt(RuntimeError):
    """Ein Cloud-Aufruf wurde vor dem Senden gestoppt (geschuetzte Daten im Prompt)."""

    def __init__(self, funde: list[Fund]) -> None:
        self.funde = funde
        self.arten = sorted({f.art for f in funde})
        orte = ", ".join(sorted({f"Nachricht {f.nachricht} ({f.rolle})" for f in funde}))
        super().__init__(
            f"Ausgangssperre: Claude-Aufruf abgebrochen, geschuetzte Daten trotz Schwaerzung "
            f"({', '.join(self.arten)}; in {orte}). Nichts wurde gesendet, die Datei bleibt "
            f"unbenannt. Bekannter Fehlalarm: exakten Fundtext in {VERBOTSLISTE_PFAD.name} "
            f"unter 'erlaubt' eintragen."
        )


# ---------------------------------------------------------------------------
# Muster (gleich wie cv-tailor)
# ---------------------------------------------------------------------------

_TRENNER = r"(?:[ \t]*[.\-][ \t]*|[ \t]+)"
_AHV_RE = re.compile(
    rf"(?<!\d)756{_TRENNER}\d{{4}}{_TRENNER}\d{{4}}{_TRENNER}\d{{2}}(?!\d)|(?<!\d)756\d{{10}}(?!\d)"
)

# IBAN-Laengen je Land (SWIFT IBAN Registry, ISO 13616). Fuer Laender ausserhalb
# der Tabelle werden alle Laengen 15-34 versucht (im Zweifel lieber ein Fund).
# fmt: off
_IBAN_LAENGE: dict[str, int] = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22,
    "BH": 22, "BI": 27, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24,
    "DE": 22, "DJ": 27, "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18,
    "FK": 18, "FO": 18, "FR": 27, "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27,
    "GT": 28, "HN": 28, "HR": 21, "HU": 28, "IE": 22, "IL": 23, "IQ": 23, "IS": 26,
    "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28, "LC": 32, "LI": 21, "LT": 20,
    "LU": 20, "LV": 21, "LY": 25, "MC": 27, "MD": 24, "ME": 22, "MK": 19, "MN": 20,
    "MR": 27, "MT": 31, "MU": 30, "NI": 28, "NL": 18, "NO": 15, "OM": 23, "PK": 24,
    "PL": 28, "PS": 29, "QA": 29, "RO": 24, "RS": 22, "RU": 33, "SA": 24, "SC": 31,
    "SD": 18, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "SO": 23, "ST": 25, "SV": 28,
    "TL": 23, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20, "YE": 30,
}
# fmt: on
# Moegliche IBAN-Anfaenge: zwei Buchstaben, zwei Ziffern, davor kein Buchstabe/keine Ziffer.
_IBAN_START_RE = re.compile(r"(?<![0-9A-Za-z])[A-Za-z]{2}[0-9]{2}")
# Moegliche Kartenanfaenge: eine Ziffer, davor keine Ziffer (auch nicht «1.» oder «1,»).
_KARTE_START_RE = re.compile(r"(?<![0-9])(?<![0-9][.,])[0-9]")
_ZIFFERN = frozenset("0123456789")
_ALNUM = frozenset("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_MAX_TRENNER = 3  # Leerzeichen/Bindestriche hintereinander innerhalb einer Nummer

_MONATE = (
    r"(?:jan(?:uar|uary)?|feb(?:ruar|ruary)?|m(?:ä|ae)rz|march|mar|apr(?:il)?|mai|may|"
    r"jun(?:i|e)?|jul(?:i|y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|okt(?:ober)?|oct(?:ober)?|"
    r"nov(?:ember)?|dez(?:ember)?|dec(?:ember)?)\.?"
)
_DATUM = (
    r"(?:\d{1,2}\.\s*\d{1,2}\.\s*\d{2,4}"
    rf"|\d{{1,2}}\.?\s+{_MONATE}\s+\d{{4}}"
    rf"|{_MONATE}\s+\d{{1,2}},?\s+\d{{4}}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}/\d{1,2}/\d{4})"
)
_GEBURT_RE = re.compile(
    r"(?:geburtsdatum|geb\.\s*datum|geboren(?:\s+am)?|geb\.(?:\s+am)?|date\s+of\s+birth|"
    r"birth\s*date|born(?:\s+on)?|\bdob\b)"
    rf"[\s:*_,]*{_DATUM}",
    re.IGNORECASE,
)

_SECRET_MUSTER: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def normalisiere(text: str) -> str:
    """Text fuer die Pruefung vereinheitlichen, damit Schreibvarianten nichts verstecken.

    NFKC macht aus Vollbreiten- und Sonderformen normale Zeichen, unsichtbare
    Formatzeichen (z. B. Null-Breite-Leerzeichen, weiches Trennzeichen) fallen
    weg und jedes Unicode-Leerzeichen (geschuetztes Leerzeichen, Tab,
    Zeilenumbruch usw.) wird zu einem normalen Leerzeichen.
    """
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return re.sub(r"\s", " ", text)


def _ist_trenner(c: str) -> bool:
    return c.isspace() or c == "-"


def _sammle(text: str, start: int, erlaubt: frozenset[str], max_zeichen: int) -> list[int]:
    """Endpositionen nach jedem Zeichen aus ``erlaubt`` ab ``start``.

    Zwischen den Zeichen duerfen bis zu ``_MAX_TRENNER`` Leerzeichen oder
    Bindestriche stehen. Der i-te Eintrag ist das Ende des Abschnitts mit
    i+1 Nutzzeichen; so lassen sich alle Laengen einzeln pruefen.
    """
    enden: list[int] = []
    i, n = start, len(text)
    while i < n and len(enden) < max_zeichen:
        if text[i] in erlaubt:
            i += 1
            enden.append(i)
            continue
        j = i
        while j < n and j - i < _MAX_TRENNER and _ist_trenner(text[j]):
            j += 1
        if j == i or j >= n or text[j] not in erlaubt:
            break
        i = j
    return enden


def _iban_gueltig(kandidat: str) -> bool:
    s = re.sub(r"[\s\-]", "", kandidat).upper()
    if not 15 <= len(s) <= 34 or not s.isascii() or not s.isalnum():
        return False
    umgestellt = s[4:] + s[:4]
    zahl = int("".join(str(int(c, 36)) for c in umgestellt))
    return zahl % 97 == 1


def _iban_plausibel(kompakt: str) -> bool:
    """Laenge passt zum Land; fuer unbekannte Laender mindestens halb Ziffern im BBAN."""
    land = kompakt[:2].upper()
    if land in _IBAN_LAENGE:
        return len(kompakt) == _IBAN_LAENGE[land]
    bban = kompakt[4:]
    return sum(c in _ZIFFERN for c in bban) * 2 >= len(bban)


def iban_stellen(text: str) -> list[tuple[int, int]]:
    """Bereiche (start, ende) gueltiger IBANs, gross oder klein, mit oder ohne Trenner.

    Fuer jeden moeglichen Anfang wird jede Laenge, die an einer Wortgrenze
    endet, gegen die Pruefziffer (mod 97) getestet. Darum verschluckt nachfolgender
    Text (z. B. « BIC …») die IBAN nicht mehr.
    """
    stellen: list[tuple[int, int]] = []
    for m in _IBAN_START_RE.finditer(text):
        enden = _sammle(text, m.start(), _ALNUM, 34)
        for laenge in range(len(enden), 14, -1):
            ende = enden[laenge - 1]
            if ende < len(text) and text[ende] in _ALNUM:
                continue  # endet mitten in einem Wort
            kandidat = text[m.start() : ende]
            kompakt = re.sub(r"[\s\-]", "", kandidat)
            if _iban_plausibel(kompakt) and _iban_gueltig(kompakt):
                stellen.append((m.start(), ende))
                break
    return stellen


def _luhn_gueltig(ziffern: str) -> bool:
    summe = 0
    for i, c in enumerate(reversed(ziffern)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        summe += d
    return summe % 10 == 0


def _ist_karte(kandidat: str) -> bool:
    ziffern = re.sub(r"\D", "", kandidat)
    if not 13 <= len(ziffern) <= 19 or ziffern[0] not in "3456":
        return False
    if len(set(ziffern)) == 1:
        return False
    return _luhn_gueltig(ziffern)


def karten_stellen(text: str) -> list[tuple[int, int]]:
    """Bereiche (start, ende) Luhn-gueltiger Kartennummern (13-19 Ziffern).

    Fuer jeden moeglichen Anfang wird jede Laenge, die nicht mitten in einer
    Zahl endet, einzeln geprueft (laengste zuerst). Nachfolgende Ziffern (Ablaufdatum,
    CVC) verstecken die Nummer so nicht mehr. Bereiche ueberlappen nicht.
    """
    stellen: list[tuple[int, int]] = []
    belegt_bis = 0
    for m in _KARTE_START_RE.finditer(text):
        if m.start() < belegt_bis:
            continue
        enden = _sammle(text, m.start(), _ZIFFERN, 19)
        for laenge in range(len(enden), 12, -1):
            ende = enden[laenge - 1]
            rest = text[ende : ende + 2]
            if (rest[:1] and rest[0] in _ZIFFERN) or (
                len(rest) == 2 and rest[0] in ".," and rest[1] in _ZIFFERN
            ):
                continue  # endet mitten in einer Zahl oder vor Dezimalstellen
            if _ist_karte(text[m.start() : ende]):
                stellen.append((m.start(), ende))
                belegt_bis = ende
                break
    return stellen


# ---------------------------------------------------------------------------
# Schwaerzungs-Helfer fuer dok_namer.redact (gleiche Erkennung wie die Sperre)
# ---------------------------------------------------------------------------

def schwaerze_geburtsdaten(text: str, ersatz: str) -> tuple[str, int]:
    """Geburtsdaten samt Bezeichnung ersetzen. Gibt (text, anzahl) zurueck."""
    return _GEBURT_RE.subn(ersatz, text)


def schwaerze_karten(text: str, ersatz: str) -> tuple[str, int]:
    """Luhn-gueltige Kartennummern ersetzen. Gibt (text, anzahl) zurueck.

    Gleiche Erkennung wie die Sperre (jede Laenge einzeln, Unicode-Leerzeichen
    als Trenner); Vollbreiten-Ziffern faengt erst die Sperre nach NFKC.
    """
    stellen = karten_stellen(text)
    for start, ende in reversed(stellen):
        text = text[:start] + ersatz + text[ende:]
    return text, len(stellen)


# ---------------------------------------------------------------------------
# Verbotsliste
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Eintrag:
    art: str
    muster: re.Pattern[str]


def _eintrag_muster(wert: str) -> re.Pattern[str]:
    """Tolerant gegen Leerzeichen, Gross-/Kleinschreibung und Ziffern-Trenner."""
    wert = normalisiere(wert).strip()
    ziffern = re.sub(r"\D", "", wert)
    if len(ziffern) >= 7 and len(ziffern) >= len(re.sub(r"[\s+().\-/]", "", wert)):
        # Ueberwiegend Ziffern (Telefon, Kontonummer): Trenner zwischen den Ziffern egal.
        return re.compile(r"(?<!\d)" + r"[\s.\-/()]*".join(ziffern) + r"(?!\d)")
    woerter = wert.split()
    kern = r"\s+".join(re.escape(w) for w in woerter)
    return re.compile(rf"(?<!\w){kern}(?!\w)", re.IGNORECASE)


@dataclass(frozen=True)
class Verbotsliste:
    eintraege: tuple[_Eintrag, ...] = ()
    erlaubt: tuple[str, ...] = ()  # normalisierte Werte bekannter Fehlalarme


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", normalisiere(text)).strip().casefold()


_HINWEIS_GEGEBEN = False


def _hinweis_ohne_liste() -> None:
    global _HINWEIS_GEGEBEN
    if not _HINWEIS_GEGEBEN:
        _HINWEIS_GEGEBEN = True
        log.info("Ausgangssperre: %s fehlt, es gelten nur die festen Muster", VERBOTSLISTE_PFAD.name)


def lade_verbotsliste(pfad: Path | None = None) -> Verbotsliste:
    """Liest die lokale Verbotsliste.

    Fail closed, wo ein Fehler die Sperre still abschalten wuerde:
    - eine unlesbare Datei bricht ab;
    - ist ``DOK_NAMER_AUSGANGSSPERRE_LISTE`` gesetzt und die Datei fehlt, bricht
      der Lauf ab (Tippfehler im Pfad oder nicht eingehaengtes Laufwerk).
    Fehlt nur die optionale Standard-Liste neben ``dok_namer.py``, gelten die
    festen Muster; das steht einmal pro Prozess im Log.
    """
    if pfad is None:
        env = os.environ.get(VERBOTSLISTE_ENV, "").strip()
        if env:
            pfad = Path(env).expanduser()
            if not pfad.is_file():
                raise ValueError(
                    f"Ausgangssperre: {VERBOTSLISTE_ENV} zeigt auf eine Verbotsliste, die es "
                    f"nicht gibt ({pfad}). Nichts wurde gesendet. Pfad korrigieren oder die "
                    f"Variable entfernen"
                )
        else:
            pfad = VERBOTSLISTE_PFAD
            if not pfad.exists():
                _hinweis_ohne_liste()
                return Verbotsliste()
    if not pfad.exists():
        return Verbotsliste()
    try:
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Ausgangssperre: Verbotsliste {pfad} ist kein gueltiges YAML") from exc
    if not isinstance(daten, dict):
        raise ValueError(f"Ausgangssperre: Verbotsliste {pfad} muss ein YAML-Objekt sein")

    eintraege: list[_Eintrag] = []
    for roh in daten.get("verboten") or []:
        if isinstance(roh, str):
            wert, art = roh, "Verbotsliste"
        elif isinstance(roh, dict) and isinstance(roh.get("wert"), str):
            wert = roh["wert"]
            art = f"Verbotsliste: {roh['art']}" if roh.get("art") else "Verbotsliste"
        else:
            raise ValueError(f"Ausgangssperre: ungueltiger Eintrag unter 'verboten' in {pfad}")
        if len(wert.strip()) < _MIN_LAENGE_EINTRAG:
            raise ValueError(
                f"Ausgangssperre: Eintrag in {pfad} ist kuerzer als {_MIN_LAENGE_EINTRAG} Zeichen"
            )
        eintraege.append(_Eintrag(art=art, muster=_eintrag_muster(wert.strip())))
    erlaubt = tuple(_norm(str(w)) for w in (daten.get("erlaubt") or []))
    return Verbotsliste(eintraege=tuple(eintraege), erlaubt=erlaubt)


# ---------------------------------------------------------------------------
# Pruefung
# ---------------------------------------------------------------------------

def finde_im_text(text: str, liste: Verbotsliste | None = None) -> list[str]:
    """Arten der Funde in ``text`` (ohne Werte), in fester Reihenfolge."""
    liste = liste or Verbotsliste()
    roh = text
    text = normalisiere(text)

    def erlaubt(treffer: str) -> bool:
        return _norm(treffer) in liste.erlaubt

    arten: list[str] = []
    if any(not erlaubt(m.group(0)) for m in _AHV_RE.finditer(text)):
        arten.append("AHV-Nummer")
    if any(not erlaubt(text[a:b]) for a, b in iban_stellen(text)):
        arten.append("IBAN")
    if any(not erlaubt(text[a:b]) for a, b in karten_stellen(text)):
        arten.append("Kreditkartennummer")
    if any(not erlaubt(m.group(0)) for m in _GEBURT_RE.finditer(text)):
        arten.append("Geburtsdatum")
    secret = any(p.search(text) for p in _SECRET_MUSTER)
    if not secret:
        for var in SECRET_ENV_VARS:
            wert = os.environ.get(var, "").strip()
            if len(wert) >= 16 and (wert in roh or wert in text):
                secret = True
                break
    if secret:
        arten.append("Secret/API-Key")
    for eintrag in liste.eintraege:
        if eintrag.art not in arten and any(
            not erlaubt(m.group(0)) for m in eintrag.muster.finditer(text)
        ):
            arten.append(eintrag.art)
    return arten


def _bloecke(content: object) -> list[tuple[str | None, bool]]:
    """Inhalt einer Nachricht als Liste (text, ist_text). Nicht-Text gilt als Fund."""
    if isinstance(content, str):
        return [(content, True)]
    if isinstance(content, list):
        out: list[tuple[str | None, bool]] = []
        for block in content:
            if isinstance(block, str):
                out.append((block, True))
            elif isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                out.append((block["text"], True))
            else:
                # Bild, PDF, Scan-Pfad oder Unbekanntes: kann nicht geprueft werden.
                out.append((None, False))
        return out
    if content is None:
        return []
    return [(None, False)]


def pruefe_nachrichten(messages: list[dict], liste: Verbotsliste | None = None) -> list[Fund]:
    """Alle Funde in einer messages-Liste."""
    if liste is None:
        liste = lade_verbotsliste()
    funde: list[Fund] = []
    for i, msg in enumerate(messages):
        rolle = str(msg.get("role", "?"))
        gesehen: set[str] = set()

        # melde wird nur in derselben Schleifenrunde aufgerufen, die Bindung an
        # gesehen/i/rolle ist also gewollt (ruff B023 ist hier ein Fehlalarm).
        def melde(art: str) -> None:
            if art not in gesehen:  # noqa: B023
                gesehen.add(art)  # noqa: B023
                funde.append(Fund(art=art, nachricht=i, rolle=rolle))  # noqa: B023

        for text, ist_text in _bloecke(msg.get("content")):
            if not ist_text:
                melde(ART_NICHT_TEXT)
                continue
            for art in finde_im_text(text or "", liste):
                melde(art)
    return funde


def sperre_pruefen(messages: list[dict], liste: Verbotsliste | None = None) -> None:
    """Wirft ``AusgangGesperrt``, wenn der Prompt geschuetzte Daten enthaelt."""
    funde = pruefe_nachrichten(messages, liste)
    if funde:
        raise AusgangGesperrt(funde)
