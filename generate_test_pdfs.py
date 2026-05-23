#!/usr/bin/env python3
"""
Generate ~20 realistic Swiss test PDFs for dok-namer.
Output: test-scans/ directory.
"""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors

OUT_DIR = Path("test-scans")

def make_pdf(filename: str, draw_fn) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    p = canvas.Canvas(str(OUT_DIR / filename), pagesize=A4)
    draw_fn(p)
    p.save()
    print(f"  Created: {filename}")


def text(c, x_cm, y_cm, txt, size=10, bold=False):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.drawString(x_cm * cm, y_cm * cm, txt)


def hline(c, y_cm):
    c.setLineWidth(0.5)
    c.line(2 * cm, y_cm * cm, 19 * cm, y_cm * cm)


# ──────────────────────────────────────────────
# 1. EKZ Stromrechnung
# ──────────────────────────────────────────────
def doc_ekz_stromrechnung(c):
    text(c, 2, 27, "Elektrizitätswerke des Kantons Musterstadt (EKZ)", 13, bold=True)
    text(c, 2, 26.2, "Postfach 2312, 8022 Musterstadt   |   www.ekz.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Musterstadt, 15. November 2025")
    text(c, 2, 25.2, "Markus Müller")
    text(c, 2, 24.7, "Seestrasse 47")
    text(c, 2, 24.2, "8800 Thalwil")
    text(c, 2, 23.2, "STROMRECHNUNG", 14, bold=True)
    text(c, 2, 22.4, "Rechnungsnummer: 2025-EKZ-089341")
    text(c, 2, 21.8, "Vertragsnummer:  EKZ-7712-A")
    text(c, 2, 21.0, "Abrechnungsperiode:   01.08.2025 – 31.10.2025")
    text(c, 2, 20.2, "Verbrauch:            1'842 kWh")
    hline(c, 19.8)
    text(c, 2, 19.2, "Grundgebühr",  10);  text(c, 15, 19.2, "CHF 18.50")
    text(c, 2, 18.6, "Energielieferung  1'842 kWh à 0.2230",  10);  text(c, 15, 18.6, "CHF 410.77")
    text(c, 2, 18.0, "Netznutzung",  10);  text(c, 15, 18.0, "CHF 74.30")
    text(c, 2, 17.4, "Abgaben & Zuschläge",  10);  text(c, 15, 17.4, "CHF 22.10")
    text(c, 2, 16.8, "MwSt 7.7%",  10);  text(c, 15, 16.8, "CHF 40.55")
    hline(c, 16.4)
    text(c, 2, 15.8, "TOTAL", 11, bold=True);  text(c, 15, 15.8, "CHF 566.22", bold=True)
    text(c, 2, 14.8, "Zahlbar bis: 05.12.2025")
    text(c, 2, 14.2, "IBAN: CH56 0483 5012 3456 7800 9")
    text(c, 2, 13.6, "Kontoinhaber: Elektrizitätswerke des Kantons Musterstadt")
    text(c, 2, 12.8, "Telefon: 058 359 31 11   |   info@ekz.ch")

make_pdf("scan_001_ekz_rechnung.pdf", doc_ekz_stromrechnung)


# ──────────────────────────────────────────────
# 2. Swisscom Telefonrechnung
# ──────────────────────────────────────────────
def doc_swisscom_rechnung(c):
    text(c, 2, 27, "Swisscom (Schweiz) AG", 13, bold=True)
    text(c, 2, 26.2, "Alte Tiefenaustrasse 6, 3048 Worblaufen", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Bern, 1. Oktober 2025")
    text(c, 2, 25.2, "Sandra Baumgartner")
    text(c, 2, 24.7, "Dorfstrasse 12")
    text(c, 2, 24.2, "3600 Thun")
    text(c, 2, 23.2, "RECHNUNG – Oktober 2025", 14, bold=True)
    text(c, 2, 22.4, "Kundennummer:   SCW-44892-B")
    text(c, 2, 21.8, "Rechnungsdatum: 01.10.2025")
    hline(c, 21.4)
    text(c, 2, 20.8, "inOne home L – Monatsabo");  text(c, 15, 20.8, "CHF 89.00")
    text(c, 2, 20.2, "inOne mobile M – Monatsabo");  text(c, 15, 20.2, "CHF 49.00")
    text(c, 2, 19.6, "Roaming EU – Datenpauschale");  text(c, 15, 19.6, "CHF 5.00")
    text(c, 2, 19.0, "Gutschrift Treuebonus");  text(c, 15, 19.0, "CHF -10.00")
    hline(c, 18.6)
    text(c, 2, 18.0, "TOTAL (inkl. MwSt)", 11, bold=True);  text(c, 15, 18.0, "CHF 133.00", bold=True)
    text(c, 2, 17.2, "Zahlbar bis: 20.10.2025  |  IBAN: CH93 0076 2011 6238 5295 7")
    text(c, 2, 16.4, "Telefon Kundenservice: 0800 800 800  (kostenlos)")
    text(c, 2, 15.6, "Vertragsnummer Mobil: 079 456 78 90")

make_pdf("scan_002_swisscom_rechnung.pdf", doc_swisscom_rechnung)


# ──────────────────────────────────────────────
# 3. Kantonalbank Kontoauszug
# ──────────────────────────────────────────────
def doc_kb_kontoauszug(c):
    text(c, 2, 27, "Zürcher Kantonalbank ZKB", 13, bold=True)
    text(c, 2, 26.2, "Bahnhofstrasse 9, 8001 Musterstadt   |   www.zkb.ch", 9)
    hline(c, 25.8)
    text(c, 2, 25.2, "KONTOAUSZUG", 14, bold=True)
    text(c, 2, 24.4, "Konto:        CH38 0070 0110 0061 1600 2")
    text(c, 2, 23.8, "Kontoinhaber: Thomas Keller, Hauptstrasse 5, 5400 Baden")
    text(c, 2, 23.2, "Periode:      01.09.2025 – 30.09.2025")
    text(c, 2, 22.6, "Saldo 01.09.2025:    CHF 4'231.80 H")
    hline(c, 22.2)
    text(c, 2, 21.8, "Datum       Buchungstext                        Betrag       Saldo", bold=True)
    hline(c, 21.5)
    rows = [
        ("03.09.2025", "Lohneingang Muster AG", "CHF +5'800.00", "CHF 10'031.80"),
        ("05.09.2025", "DAUERAUFTRAG Miete", "CHF -1'950.00", "CHF 8'081.80"),
        ("10.09.2025", "TWINT Lidl Musterstadt", "CHF -84.60", "CHF 7'997.20"),
        ("12.09.2025", "Krankenkasse Helsana", "CHF -312.50", "CHF 7'684.70"),
        ("15.09.2025", "SBB Generalabonnement", "CHF -3'860.00", "CHF 3'824.70"),
        ("20.09.2025", "Migros Supermarkt", "CHF -147.35", "CHF 3'677.35"),
        ("25.09.2025", "E-Banking Überweisung", "CHF -500.00", "CHF 3'177.35"),
        ("30.09.2025", "Kontoabschluss Saldo",  "",             "CHF 3'177.35"),
    ]
    for i, (d, b, amt, sal) in enumerate(rows):
        y = (21.0 - i * 0.55) * cm
        c.setFont("Helvetica", 9)
        c.drawString(2 * cm, y, d)
        c.drawString(5 * cm, y, b)
        c.drawString(13 * cm, y, amt)
        c.drawString(16.5 * cm, y, sal)
    hline(c, 16.5)
    text(c, 2, 16.0, "Saldo 30.09.2025:    CHF 3'177.35 H", bold=True)
    text(c, 2, 14.8, "Bei Fragen: 0844 843 844  |  info@zkb.ch")

make_pdf("scan_003_zkb_kontoauszug.pdf", doc_kb_kontoauszug)


# ──────────────────────────────────────────────
# 4. Helsana Krankenkassen-Prämienrechnung
# ──────────────────────────────────────────────
def doc_helsana_praemie(c):
    text(c, 2, 27, "Helsana Versicherungen AG", 13, bold=True)
    text(c, 2, 26.2, "Musterstadtstrasse 130, 8600 Dübendorf   |   www.helsana.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Dübendorf, 20. November 2025")
    text(c, 2, 25.2, "Anna Zimmermann")
    text(c, 2, 24.7, "Rosenweg 8")
    text(c, 2, 24.2, "6300 Zug")
    text(c, 2, 23.2, "PRÄMIENRECHNUNG – Quartal IV / 2025", 13, bold=True)
    text(c, 2, 22.4, "Versicherungsnummer:  HEL-3-44812-ZG")
    text(c, 2, 21.8, "AHV-Nummer:           756.4821.9034.17")
    hline(c, 21.4)
    text(c, 2, 20.8, "KVG Grundversicherung (Franchise CHF 300)");  text(c, 15, 20.8, "CHF 312.50")
    text(c, 2, 20.2, "VVG Zusatz Helsana+ Spital Halbprivat");       text(c, 15, 20.2, "CHF 87.30")
    text(c, 2, 19.6, "VVG Zusatz Helsana+ Alternativmedizin");       text(c, 15, 19.6, "CHF 24.80")
    text(c, 2, 19.0, "Prämienverbilligung");                          text(c, 15, 19.0, "CHF -45.00")
    hline(c, 18.6)
    text(c, 2, 18.0, "Monatsprämie total", 11, bold=True);  text(c, 15, 18.0, "CHF 379.60", bold=True)
    text(c, 2, 17.4, "Quartalsrechnung (×3):", 11, bold=True);  text(c, 15, 17.4, "CHF 1'138.80", bold=True)
    text(c, 2, 16.6, "Zahlbar bis: 31.12.2025")
    text(c, 2, 16.0, "IBAN: CH56 0900 0000 3000 3233 3")
    text(c, 2, 15.4, "Telefon: 0844 80 81 82   |   service@helsana.ch")

make_pdf("scan_004_helsana_praemie.pdf", doc_helsana_praemie)


# ──────────────────────────────────────────────
# 5. Steueramt Kanton Musterstadt – Steuerrechnung
# ──────────────────────────────────────────────
def doc_steuer_kanton(c):
    text(c, 2, 27, "Kantonales Steueramt Musterstadt", 13, bold=True)
    text(c, 2, 26.2, "Bändliweg 21, 8090 Musterstadt   |   www.steueramt.zh.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Musterstadt, 28. März 2026")
    text(c, 2, 25.2, "Peter Huber")
    text(c, 2, 24.7, "Bergstrasse 22")
    text(c, 2, 24.2, "8610 Uster")
    text(c, 2, 23.2, "STEUERRECHNUNG 2025", 14, bold=True)
    text(c, 2, 22.4, "Steuerpflichtiger: Peter Huber, geb. 15.03.1975")
    text(c, 2, 21.8, "AHV-Nummer:        756.9823.4712.06")
    text(c, 2, 21.2, "Steuerjahr:        2025")
    hline(c, 20.8)
    text(c, 2, 20.2, "Kantonssteuern");   text(c, 15, 20.2, "CHF 4'820.00")
    text(c, 2, 19.6, "Gemeindesteuern"); text(c, 15, 19.6, "CHF 3'215.00")
    text(c, 2, 19.0, "Direkte Bundessteuer"); text(c, 15, 19.0, "CHF 1'105.50")
    text(c, 2, 18.4, "Kirchensteuer");  text(c, 15, 18.4, "CHF 320.00")
    text(c, 2, 17.8, "Abzügl. Vorauszahlungen"); text(c, 15, 17.8, "CHF -8'000.00")
    hline(c, 17.4)
    text(c, 2, 16.8, "NACHZAHLUNG", 11, bold=True);  text(c, 15, 16.8, "CHF 1'460.50", bold=True)
    text(c, 2, 16.0, "Zahlbar bis: 30.04.2026")
    text(c, 2, 15.4, "IBAN: CH56 0707 0032 0100 0000 4")
    text(c, 2, 14.8, "Telefon: 043 259 37 00")

make_pdf("scan_005_steueramt_kanton.pdf", doc_steuer_kanton)


# ──────────────────────────────────────────────
# 6. Gemeinde Uster – Steuererklärung Mahnung
# ──────────────────────────────────────────────
def doc_gemeinde_mahnung(c):
    text(c, 2, 27, "Steuerverwaltung Uster", 13, bold=True)
    text(c, 2, 26.2, "Stadthaus, 8610 Uster   |   www.uster.ch/steuern", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Uster, 3. Dezember 2025")
    text(c, 2, 25.2, "Frau Maria Senn")
    text(c, 2, 24.7, "Industrieweg 3")
    text(c, 2, 24.2, "8610 Uster")
    text(c, 2, 23.2, "MAHNUNG – Steuererklärung 2024", 13, bold=True)
    text(c, 2, 22.4, "Sehr geehrte Frau Senn,")
    text(c, 2, 21.6, "Trotz unserer Aufforderung vom 30.09.2025 haben wir die")
    text(c, 2, 21.0, "Steuererklärung 2024 bisher nicht erhalten.")
    text(c, 2, 20.2, "Wir bitten Sie, die Steuererklärung bis spätestens")
    text(c, 2, 19.6, "31. Januar 2026 einzureichen.")
    text(c, 2, 18.8, "Bei Nichteinreichung werden wir die Steuern nach Ermessen")
    text(c, 2, 18.2, "veranlagen und eine Ordnungsbusse von CHF 200.00 erheben.")
    text(c, 2, 17.4, "AHV-Nummer:  756.2211.4499.83")
    text(c, 2, 16.8, "Steuerjahr:  2024")
    text(c, 2, 16.0, "Freundliche Grüsse")
    text(c, 2, 15.4, "Steuerverwaltung Uster")
    text(c, 2, 14.6, "Telefon: 058 610 18 00   |   steuern@uster.ch")

make_pdf("scan_006_gemeinde_mahnung.pdf", doc_gemeinde_mahnung)


# ──────────────────────────────────────────────
# 7. Axa Versicherung – Hausrat/Haftpflicht
# ──────────────────────────────────────────────
def doc_axa_versicherung(c):
    text(c, 2, 27, "AXA Versicherungen AG", 13, bold=True)
    text(c, 2, 26.2, "General-Guisan-Strasse 40, 8401 Winterthur", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Winterthur, 1. Januar 2026")
    text(c, 2, 25.2, "Hans Meier")
    text(c, 2, 24.7, "Parkstrasse 15")
    text(c, 2, 24.2, "4500 Solothurn")
    text(c, 2, 23.2, "PRÄMIENRECHNUNG 2026", 13, bold=True)
    text(c, 2, 22.4, "Police-Nr.:   AXA-CH-7829341")
    text(c, 2, 21.8, "Versicherungsjahr: 01.01.2026 – 31.12.2026")
    hline(c, 21.4)
    text(c, 2, 20.8, "Hausratversicherung  (Versicherungssumme CHF 120'000)");  text(c, 15, 20.8, "CHF 285.00")
    text(c, 2, 20.2, "Privathaftpflicht  (Deckung CHF 5 Mio.)");               text(c, 15, 20.2, "CHF 95.00")
    text(c, 2, 19.6, "Naturgefahren-Zusatz");                                   text(c, 15, 19.6, "CHF 35.00")
    hline(c, 19.2)
    text(c, 2, 18.6, "Jahresprämie total (inkl. Stempelsteuer)", bold=True);  text(c, 15, 18.6, "CHF 415.00", bold=True)
    text(c, 2, 17.8, "Zahlbar bis: 31.01.2026")
    text(c, 2, 17.2, "IBAN: CH56 0900 0000 3100 9999 9")
    text(c, 2, 16.6, "Telefon: 0800 809 809  |  info@axa.ch")

make_pdf("scan_007_axa_versicherung.pdf", doc_axa_versicherung)


# ──────────────────────────────────────────────
# 8. Migros Bank – Kreditkartenabrechnung
# ──────────────────────────────────────────────
def doc_migros_bank_kreditkarte(c):
    text(c, 2, 27, "Migros Bank AG", 13, bold=True)
    text(c, 2, 26.2, "Seidengasse 12, 8001 Musterstadt   |   www.migrosbank.ch", 9)
    hline(c, 25.8)
    text(c, 2, 25.2, "KREDITKARTENABRECHNUNG", 14, bold=True)
    text(c, 2, 24.4, "Karte:       Migros Cumulus Mastercard **** **** **** 7834")
    text(c, 2, 23.8, "Inhaberin:   Claudia Stalder, Lindenstrasse 4, 9000 St. Gallen")
    text(c, 2, 23.2, "Periode:     01.11.2025 – 30.11.2025")
    hline(c, 22.8)
    text(c, 2, 22.4, "Datum       Händler                             Betrag", bold=True)
    hline(c, 22.1)
    rows = [
        ("03.11.2025", "Coop Supermarkt St. Gallen",          "CHF 89.45"),
        ("07.11.2025", "Amazon.de Online",                    "CHF 43.90"),
        ("10.11.2025", "Shell Tankstelle Gossau",             "CHF 124.50"),
        ("14.11.2025", "Restaurant Löwen St. Gallen",         "CHF 67.80"),
        ("18.11.2025", "SBB Online-Ticket",                   "CHF 52.00"),
        ("22.11.2025", "Zalando Fashion",                     "CHF 119.90"),
        ("27.11.2025", "Apotheke St. Gallen",                 "CHF 28.30"),
    ]
    for i, (d, b, amt) in enumerate(rows):
        y = (21.6 - i * 0.55) * cm
        c.setFont("Helvetica", 9)
        c.drawString(2 * cm, y, d)
        c.drawString(5 * cm, y, b)
        c.drawString(15 * cm, y, amt)
    hline(c, 17.6)
    text(c, 2, 17.0, "TOTAL BELASTUNGEN", bold=True); text(c, 15, 17.0, "CHF 525.85", bold=True)
    text(c, 2, 16.2, "Zahlbar bis: 20.12.2025")
    text(c, 2, 15.6, "IBAN: CH56 0840 1016 4344 2000 9")
    text(c, 2, 15.0, "Telefon: 0848 845 400")

make_pdf("scan_008_migros_kreditkarte.pdf", doc_migros_bank_kreditkarte)


# ──────────────────────────────────────────────
# 9. Zurich Insurance – Motorfahrzeugversicherung
# ──────────────────────────────────────────────
def doc_zurich_auto(c):
    text(c, 2, 27, "Zurich Insurance Group", 13, bold=True)
    text(c, 2, 26.2, "Mythenquai 2, 8022 Musterstadt   |   www.zurich.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Musterstadt, 15. Oktober 2025")
    text(c, 2, 25.2, "Kurt Frei")
    text(c, 2, 24.7, "Mühleweg 8")
    text(c, 2, 24.2, "3011 Bern")
    text(c, 2, 23.2, "MOTORFAHRZEUG-PRÄMIENRECHNUNG 2026", 12, bold=True)
    text(c, 2, 22.4, "Police-Nr.:      ZUR-MFZ-2291-B")
    text(c, 2, 21.8, "Fahrzeug:        VW Golf, ZH 447 891")
    text(c, 2, 21.2, "Versicherungsjahr: 01.01.2026 – 31.12.2026")
    hline(c, 20.8)
    text(c, 2, 20.2, "Haftpflichtversicherung");     text(c, 15, 20.2, "CHF 512.00")
    text(c, 2, 19.6, "Vollkaskoversicherung");       text(c, 15, 19.6, "CHF 734.00")
    text(c, 2, 19.0, "Parkschäden-Zusatz");          text(c, 15, 19.0, "CHF 89.00")
    text(c, 2, 18.4, "Bonus-Rabatt –30%");           text(c, 15, 18.4, "CHF -153.60")
    hline(c, 18.0)
    text(c, 2, 17.4, "Jahresprämie total", bold=True); text(c, 15, 17.4, "CHF 1'181.40", bold=True)
    text(c, 2, 16.6, "Zahlbar bis: 30.11.2025")
    text(c, 2, 16.0, "IBAN: CH56 0900 0000 3000 0000 0")
    text(c, 2, 15.4, "Telefon: 044 628 28 28")

make_pdf("scan_009_zurich_auto.pdf", doc_zurich_auto)


# ──────────────────────────────────────────────
# 10. PostFinance – Kontoauszug
# ──────────────────────────────────────────────
def doc_postfinance_konto(c):
    text(c, 2, 27, "PostFinance AG", 13, bold=True)
    text(c, 2, 26.2, "Nordring 8, 3030 Bern   |   www.postfinance.ch", 9)
    hline(c, 25.8)
    text(c, 2, 25.2, "KONTOAUSZUG", 14, bold=True)
    text(c, 2, 24.4, "IBAN: CH56 0900 0000 8706 0000 6")
    text(c, 2, 23.8, "Kontoinhaber: Daniela Wirth, Bahnhofplatz 1, 2500 Biel/Bienne")
    text(c, 2, 23.2, "Auszugsnummer: 12  |  Datum: 31.12.2025")
    hline(c, 22.8)
    text(c, 2, 22.4, "Datum       Text                                    Betrag      Saldo", bold=True)
    hline(c, 22.1)
    rows = [
        ("01.12.2025", "Saldo Vortrag",                     "",             "CHF 1'842.55"),
        ("03.12.2025", "Lohngutschrift",                    "+4'200.00",    "CHF 6'042.55"),
        ("05.12.2025", "E-Rechnung EKZ Strom",              "-388.40",      "CHF 5'654.15"),
        ("10.12.2025", "Dauerauftrag Elternteil",           "-500.00",      "CHF 5'154.15"),
        ("15.12.2025", "TWINT Coop",                        "-123.75",      "CHF 5'030.40"),
        ("20.12.2025", "Krankenkasse Concordia",            "-298.00",      "CHF 4'732.40"),
        ("31.12.2025", "Abschluss Kontogebühr",             "-5.00",        "CHF 4'727.40"),
    ]
    for i, (d, b, amt, sal) in enumerate(rows):
        y = (21.6 - i * 0.55) * cm
        c.setFont("Helvetica", 9)
        c.drawString(2 * cm, y, d)
        c.drawString(5 * cm, y, b)
        c.drawString(13 * cm, y, amt)
        c.drawString(16 * cm, y, sal)
    hline(c, 17.6)
    text(c, 2, 17.0, "Saldo 31.12.2025: CHF 4'727.40", bold=True)
    text(c, 2, 15.8, "Telefon: 0848 888 710   |   info@postfinance.ch")

make_pdf("scan_010_postfinance_kontoauszug.pdf", doc_postfinance_konto)


# ──────────────────────────────────────────────
# 11. Gemeinde Horgen – Wasserrechnung
# ──────────────────────────────────────────────
def doc_gemeinde_wasser(c):
    text(c, 2, 27, "Gemeinde Horgen – Wasserversorgung", 13, bold=True)
    text(c, 2, 26.2, "Gemeindezentrum, 8810 Horgen   |   www.horgen.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Horgen, 15. Dezember 2025")
    text(c, 2, 25.2, "Familie Brändli")
    text(c, 2, 24.7, "Seeblickstrasse 12a")
    text(c, 2, 24.2, "8810 Horgen")
    text(c, 2, 23.2, "WASSERRECHNUNG 2025", 13, bold=True)
    text(c, 2, 22.4, "Objekt:          Einfamilienhaus Seeblickstrasse 12a")
    text(c, 2, 21.8, "Zählerstand Jan: 4'821 m³  |  Zählerstand Dez: 5'218 m³")
    text(c, 2, 21.2, "Jahresverbrauch: 397 m³")
    hline(c, 20.8)
    text(c, 2, 20.2, "Wassergebühr  397 m³ à CHF 1.85");  text(c, 15, 20.2, "CHF 734.45")
    text(c, 2, 19.6, "Grundgebühr");                       text(c, 15, 19.6, "CHF 120.00")
    text(c, 2, 19.0, "Abwassergebühr");                    text(c, 15, 19.0, "CHF 520.00")
    hline(c, 18.6)
    text(c, 2, 18.0, "TOTAL", bold=True);  text(c, 15, 18.0, "CHF 1'374.45", bold=True)
    text(c, 2, 17.2, "Zahlbar bis: 31.01.2026")
    text(c, 2, 16.6, "IBAN: CH56 0077 0016 0444 2600 1")
    text(c, 2, 16.0, "Telefon: 044 728 68 00")

make_pdf("scan_011_horgen_wasser.pdf", doc_gemeinde_wasser)


# ──────────────────────────────────────────────
# 12. Raiffeisen – Hypothekarrechnung
# ──────────────────────────────────────────────
def doc_raiffeisen_hypothek(c):
    text(c, 2, 27, "Raiffeisen Schweiz", 13, bold=True)
    text(c, 2, 26.2, "Raiffeisenplatz 4, 9001 St. Gallen", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "St. Gallen, 1. Oktober 2025")
    text(c, 2, 25.2, "Eheleute Barbara und Rolf Eggenberger")
    text(c, 2, 24.7, "Feldstrasse 29")
    text(c, 2, 24.2, "9200 Gossau SG")
    text(c, 2, 23.2, "HYPOTHEKAR-ZINSABRECHNUNG", 13, bold=True)
    text(c, 2, 22.4, "Kreditnummer:      RFC-2019-08821-SG")
    text(c, 2, 21.8, "Hypothekarbetrag:  CHF 580'000")
    text(c, 2, 21.2, "Periode:           01.10.2025 – 31.12.2025")
    text(c, 2, 20.6, "Zinssatz:          1.72% p.a. (SARON-Hypothek)")
    hline(c, 20.2)
    text(c, 2, 19.6, "Hypothekarzins Q4/2025 (580'000 × 1.72% / 4)"); text(c, 15, 19.6, "CHF 2'494.00")
    text(c, 2, 19.0, "Amortisation");                                  text(c, 15, 19.0, "CHF 2'000.00")
    hline(c, 18.6)
    text(c, 2, 18.0, "TOTAL Quartal", bold=True);  text(c, 15, 18.0, "CHF 4'494.00", bold=True)
    text(c, 2, 17.2, "Belastung IBAN: CH56 8080 8001 2345 6789 0  am 01.10.2025")
    text(c, 2, 16.4, "Telefon: 071 225 84 84")

make_pdf("scan_012_raiffeisen_hypothek.pdf", doc_raiffeisen_hypothek)


# ──────────────────────────────────────────────
# 13. AHV-Beitragsrechnung Ausgleichskasse
# ──────────────────────────────────────────────
def doc_ahv_beitrag(c):
    text(c, 2, 27, "Ausgleichskasse des Kantons Bern", 13, bold=True)
    text(c, 2, 26.2, "Aemmenmattstrasse 43, 3001 Bern   |   www.akbern.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Bern, 15. Januar 2026")
    text(c, 2, 25.2, "Beat Lüthi")
    text(c, 2, 24.7, "Bernstrasse 88")
    text(c, 2, 24.2, "3110 Münsingen")
    text(c, 2, 23.2, "AHV/IV/EO-BEITRAGSRECHNUNG 2026", 13, bold=True)
    text(c, 2, 22.4, "AHV-Nummer:       756.8831.2244.05")
    text(c, 2, 21.8, "Selbständigerwerbend seit: 01.01.2022")
    text(c, 2, 21.2, "Beitragsjahr: 2026")
    hline(c, 20.8)
    text(c, 2, 20.2, "Erwerbseinkommen (Voranmeldung): CHF 98'000")
    text(c, 2, 19.6, "AHV-Beitrag  10.6%");  text(c, 15, 19.6, "CHF 10'388.00")
    text(c, 2, 19.0, "IV-Beitrag   1.4%");   text(c, 15, 19.0, "CHF 1'372.00")
    text(c, 2, 18.4, "EO-Beitrag   0.5%");   text(c, 15, 18.4, "CHF 490.00")
    hline(c, 18.0)
    text(c, 2, 17.4, "Jahresbeitrag total", bold=True); text(c, 15, 17.4, "CHF 12'250.00", bold=True)
    text(c, 2, 16.8, "Quartalsbetrag (×4):"); text(c, 15, 16.8, "CHF 3'062.50")
    text(c, 2, 16.0, "1. Rate fällig: 31.03.2026  |  IBAN: CH56 0900 0000 3000 1111 2")
    text(c, 2, 15.4, "Telefon: 031 379 80 00")

make_pdf("scan_013_ahv_beitrag.pdf", doc_ahv_beitrag)


# ──────────────────────────────────────────────
# 14. SBB – Generalabonnement-Rechnung
# ──────────────────────────────────────────────
def doc_sbb_ga(c):
    text(c, 2, 27, "SBB AG – Kundenservice", 13, bold=True)
    text(c, 2, 26.2, "Postfach 3000, 3030 Bern   |   www.sbb.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Bern, 15. November 2025")
    text(c, 2, 25.2, "Nicole Baumann")
    text(c, 2, 24.7, "Kirchgasse 5")
    text(c, 2, 24.2, "3000 Bern 6")
    text(c, 2, 23.2, "GENERALABONNEMENT – ERNEUERUNGSRECHNUNG", 12, bold=True)
    text(c, 2, 22.4, "GA-Nummer:        GA-BE-8821-204")
    text(c, 2, 21.8, "Gültigkeitsdauer: 01.01.2026 – 31.12.2026")
    text(c, 2, 21.2, "Kategorie:        2. Klasse, Erwachsen")
    hline(c, 20.8)
    text(c, 2, 20.2, "GA 2. Klasse Jahresabo 2026"); text(c, 15, 20.2, "CHF 3'860.00")
    text(c, 2, 19.6, "Frühbucherrabatt –5%");        text(c, 15, 19.6, "CHF -193.00")
    hline(c, 19.2)
    text(c, 2, 18.6, "TOTAL", bold=True);  text(c, 15, 18.6, "CHF 3'667.00", bold=True)
    text(c, 2, 17.8, "Zahlbar bis: 31.12.2025")
    text(c, 2, 17.2, "IBAN: CH56 0900 0000 1515 1515 1")
    text(c, 2, 16.6, "Telefon: 0900 300 300 (CHF 1.19/min)")

make_pdf("scan_014_sbb_ga.pdf", doc_sbb_ga)


# ──────────────────────────────────────────────
# 15. Bildungsdirektion – Schulgeldrechnung
# ──────────────────────────────────────────────
def doc_schulgeld(c):
    text(c, 2, 27, "Bildungsdirektion Kanton Musterstadt", 13, bold=True)
    text(c, 2, 26.2, "Bildungsdirektion, 8090 Musterstadt   |   www.bi.zh.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Musterstadt, 20. August 2025")
    text(c, 2, 25.2, "Eltern von Laura Schmid")
    text(c, 2, 24.7, "Rämistrasse 101")
    text(c, 2, 24.2, "8006 Musterstadt")
    text(c, 2, 23.2, "SCHULGELDRECHNUNG – Schuljahr 2025/2026", 12, bold=True)
    text(c, 2, 22.4, "Kantonales Gymnasium Musterstadt-Nord")
    text(c, 2, 21.8, "Schüler-Nr.:      SGZH-2025-1128")
    text(c, 2, 21.2, "Schuljahr:        2025/2026")
    hline(c, 20.8)
    text(c, 2, 20.2, "Schulgeld Halbjahr 1 (Aug–Jan)"); text(c, 15, 20.2, "CHF 1'400.00")
    text(c, 2, 19.6, "Lehrmittelpauschale");            text(c, 15, 19.6, "CHF 120.00")
    text(c, 2, 19.0, "Exkursionen und Sporttage");      text(c, 15, 19.0, "CHF 80.00")
    hline(c, 18.6)
    text(c, 2, 18.0, "TOTAL", bold=True); text(c, 15, 18.0, "CHF 1'600.00", bold=True)
    text(c, 2, 17.2, "Zahlbar bis: 15.09.2025")
    text(c, 2, 16.6, "IBAN: CH56 0707 0032 0100 2222 2")
    text(c, 2, 16.0, "Telefon: 043 259 23 00")

make_pdf("scan_015_bildung_schulgeld.pdf", doc_schulgeld)


# ──────────────────────────────────────────────
# 16. CSS Krankenkasse – Leistungsabrechnung
# ──────────────────────────────────────────────
def doc_css_leistung(c):
    text(c, 2, 27, "CSS Versicherung AG", 13, bold=True)
    text(c, 2, 26.2, "Tribschenstrasse 21, 6005 Luzern   |   www.css.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Luzern, 5. November 2025")
    text(c, 2, 25.2, "Felix Graf")
    text(c, 2, 24.7, "Löwenstrasse 7")
    text(c, 2, 24.2, "6003 Luzern")
    text(c, 2, 23.2, "LEISTUNGSABRECHNUNG", 13, bold=True)
    text(c, 2, 22.4, "Versicherungsnummer: CSS-LU-8872134")
    text(c, 2, 21.8, "AHV-Nummer:          756.3344.5566.77")
    text(c, 2, 21.2, "Behandlungsperiode:  Oktober 2025")
    hline(c, 20.8)
    text(c, 2, 20.2, "Arztkosten Grundversorger Dr. Müller", 9);  text(c, 15, 20.2, "CHF 185.00")
    text(c, 2, 19.7, "Medikamente Apotheke (Rezept)",          9);  text(c, 15, 19.7, "CHF 43.20")
    text(c, 2, 19.2, "Physiotherapie (5 Sitzungen)",           9);  text(c, 15, 19.2, "CHF 225.00")
    text(c, 2, 18.7, "Franchise-Abzug (CHF 1'500, Status: CHF 1'280 verbraucht)", 9); text(c, 15, 18.7, "CHF -220.00")
    text(c, 2, 18.2, "Selbstbehalt 10% auf CHF 233.20",        9);  text(c, 15, 18.2, "CHF -23.32")
    hline(c, 17.8)
    text(c, 2, 17.2, "KVG-Leistung (wird an Leistungserbringer bezahlt)", bold=True)
    text(c, 15, 17.2, "CHF 209.88", bold=True)
    text(c, 2, 16.4, "Ihr Selbstbehalt:  CHF 23.32")
    text(c, 2, 15.8, "Telefon: 058 277 10 10   |   service@css.ch")

make_pdf("scan_016_css_leistungsabrechnung.pdf", doc_css_leistung)


# ──────────────────────────────────────────────
# 17. Gemeindeverwaltung – Kehrichtrechnnung
# ──────────────────────────────────────────────
def doc_kehricht(c):
    text(c, 2, 27, "Gemeindeverwaltung Küsnacht", 13, bold=True)
    text(c, 2, 26.2, "Obere Dorfstrasse 32, 8700 Küsnacht", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Küsnacht, 30. November 2025")
    text(c, 2, 25.2, "Andreas Maurer")
    text(c, 2, 24.7, "Seestrasse 120")
    text(c, 2, 24.2, "8700 Küsnacht")
    text(c, 2, 23.2, "ABFALLGEBÜHRENRECHNUNG 2025", 13, bold=True)
    hline(c, 22.8)
    text(c, 2, 22.2, "Grundgebühr (Haushalt, 4 Personen)");   text(c, 15, 22.2, "CHF 160.00")
    text(c, 2, 21.6, "Kehrichtsäcke 35L (12 Stk.)");          text(c, 15, 21.6, "CHF 36.00")
    text(c, 2, 21.0, "Sperrgut-Abholtermin");                 text(c, 15, 21.0, "CHF 40.00")
    text(c, 2, 20.4, "Grüngutabfuhr Jahrespauschale");        text(c, 15, 20.4, "CHF 75.00")
    hline(c, 20.0)
    text(c, 2, 19.4, "TOTAL", bold=True); text(c, 15, 19.4, "CHF 311.00", bold=True)
    text(c, 2, 18.6, "Zahlbar bis: 31.01.2026")
    text(c, 2, 18.0, "IBAN: CH56 0023 3233 1131 2300 1")
    text(c, 2, 17.4, "Telefon: 044 913 22 11")

make_pdf("scan_017_kuesenacht_kehricht.pdf", doc_kehricht)


# ──────────────────────────────────────────────
# 18. Pensionskasse – Vorsorgeausweis
# ──────────────────────────────────────────────
def doc_pk_ausweis(c):
    text(c, 2, 27, "Pensionskasse SBB", 13, bold=True)
    text(c, 2, 26.2, "Wylerstrasse 123, 3000 Bern 65   |   www.pksbb.ch", 9)
    hline(c, 25.8)
    text(c, 2, 25.2, "VORSORGEAUSWEIS 2025", 14, bold=True)
    text(c, 2, 24.4, "Versicherte Person: Stefan Ryser")
    text(c, 2, 23.8, "Geburtsdatum:       12.07.1980")
    text(c, 2, 23.2, "AHV-Nummer:         756.1122.3344.55")
    text(c, 2, 22.6, "Pensionskassen-Nr.: PKS-080-29912")
    text(c, 2, 22.0, "Arbeitgeber:        SBB AG, Bern")
    hline(c, 21.6)
    text(c, 2, 21.0, "VORSORGEGUTHABEN per 31.12.2025", bold=True)
    text(c, 2, 20.4, "Altersguthaben BVG-Minimum:");       text(c, 15, 20.4, "CHF 124'800.00")
    text(c, 2, 19.8, "Überobligatorisches Guthaben:");     text(c, 15, 19.8, "CHF 78'200.00")
    text(c, 2, 19.2, "Total Vorsorgeguthaben:");           text(c, 15, 19.2, "CHF 203'000.00")
    hline(c, 18.8)
    text(c, 2, 18.2, "JÄHRLICHE BEITRÄGE 2025", bold=True)
    text(c, 2, 17.6, "Arbeitnehmerbeitrag:");  text(c, 15, 17.6, "CHF 9'240.00")
    text(c, 2, 17.0, "Arbeitgeberbeitrag:");   text(c, 15, 17.0, "CHF 13'860.00")
    text(c, 2, 16.4, "Koordinationsabzug:");  text(c, 15, 16.4, "CHF 25'725.00")
    text(c, 2, 15.8, "Koordinierter Lohn:");  text(c, 15, 15.8, "CHF 64'275.00")
    text(c, 2, 14.8, "Telefon: 051 220 28 28   |   info@pksbb.ch")

make_pdf("scan_018_pksbb_vorsorgeausweis.pdf", doc_pk_ausweis)


# ──────────────────────────────────────────────
# 19. Mietzinsrechnung Immobilienverwaltung
# ──────────────────────────────────────────────
def doc_miete(c):
    text(c, 2, 27, "Wincasa AG – Immobilienverwaltung", 13, bold=True)
    text(c, 2, 26.2, "Pfingstweidstrasse 60, 8080 Musterstadt   |   www.wincasa.ch", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Musterstadt, 25. November 2025")
    text(c, 2, 25.2, "Valeria Costa")
    text(c, 2, 24.7, "Langstrasse 99")
    text(c, 2, 24.2, "8004 Musterstadt")
    text(c, 2, 23.2, "MIETZINSRECHNUNG DEZEMBER 2025", 12, bold=True)
    text(c, 2, 22.4, "Objekt-Nr.: WIN-ZH-4422-B")
    text(c, 2, 21.8, "Wohnung:    Langstrasse 99, 3. OG rechts, 8004 Musterstadt")
    text(c, 2, 21.2, "Mietdauer:  01.03.2023 – laufend")
    hline(c, 20.8)
    text(c, 2, 20.2, "Nettomietzins");     text(c, 15, 20.2, "CHF 1'950.00")
    text(c, 2, 19.6, "Nebenkosten à konto"); text(c, 15, 19.6, "CHF 180.00")
    text(c, 2, 19.0, "Parkplatz Tiefgarage"); text(c, 15, 19.0, "CHF 95.00")
    hline(c, 18.6)
    text(c, 2, 18.0, "TOTAL (brutto)", bold=True); text(c, 15, 18.0, "CHF 2'225.00", bold=True)
    text(c, 2, 17.2, "Fällig: 01.12.2025 (oder vorher)")
    text(c, 2, 16.6, "IBAN: CH56 0483 5012 9988 7700 3")
    text(c, 2, 16.0, "Mietertelefon: 044 215 12 00   |   wohnkunden@wincasa.ch")

make_pdf("scan_019_wincasa_miete.pdf", doc_miete)


# ──────────────────────────────────────────────
# 20. Kanton Basel-Stadt – Fahrzeugsteuer
# ──────────────────────────────────────────────
def doc_fahrzeugsteuer(c):
    text(c, 2, 27, "Strassenverkehrsamt Basel-Stadt", 13, bold=True)
    text(c, 2, 26.2, "Steinenvorstadt 15, 4051 Basel   |   www.bs.ch/sva", 9)
    hline(c, 25.8)
    text(c, 14, 25.2, "Basel, 5. Dezember 2025")
    text(c, 2, 25.2, "Oliver Brunner")
    text(c, 2, 24.7, "Riehenstrasse 44")
    text(c, 2, 24.2, "4058 Basel")
    text(c, 2, 23.2, "MOTORFAHRZEUGSTEUER 2026", 13, bold=True)
    text(c, 2, 22.4, "Kontrollschild: BS 41 200")
    text(c, 2, 21.8, "Fahrzeug:       Toyota Corolla, 2022, Benzin")
    text(c, 2, 21.2, "Hubraum:        1'987 ccm  |  Gewicht: 1'380 kg")
    hline(c, 20.8)
    text(c, 2, 20.2, "Fahrzeugsteuer (hubraumabhängig)");  text(c, 15, 20.2, "CHF 348.00")
    text(c, 2, 19.6, "Strassenverkehrsabgabe");            text(c, 15, 19.6, "CHF 40.00")
    hline(c, 19.2)
    text(c, 2, 18.6, "TOTAL", bold=True); text(c, 15, 18.6, "CHF 388.00", bold=True)
    text(c, 2, 17.8, "Zahlbar bis: 31.01.2026")
    text(c, 2, 17.2, "IBAN: CH56 0070 0110 0030 4400 9")
    text(c, 2, 16.6, "Telefon: 061 267 88 88   |   sva@bs.ch")

make_pdf("scan_020_sva_basel_fahrzeugsteuer.pdf", doc_fahrzeugsteuer)


print(f"\nDone. {len(list(OUT_DIR.glob('*.pdf')))} PDFs generated in {OUT_DIR}/")
