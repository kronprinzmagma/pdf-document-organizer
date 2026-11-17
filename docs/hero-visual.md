# README visual provenance

Asset: [demo-run.png](demo-run.png)

Captured from public source commit `44e92191897b0e843594bd42cc7f845f3fb6db38` on 2026-11-17. This is a staged demonstration with exclusively synthetic data, not evidence of a live AI run or measured model performance. The visible application/CLI content is based on existing code, not an invented interface.

## Method

The original process_file function was executed against a newly generated synthetic PDF. PDF reading, in-memory regex redaction, cost formatting, confidence handling, confirmation and file movement used the original code. Only analyze_claude, the elapsed clock and confirmation input were replaced by deterministic fixtures. The captured console output was typeset in a terminal-style frame; this is a staged CLI demonstration, not a live cloud session.

## Synthetic inputs and limits

Input scan0042.pdf: fictional issuer Musterwerke AG; recipient Frau Alex Beispiel, Teststrasse 42, 8000 Zuerich; invoice dated 01.03.2025, CHF 84.50. The actual redactor reported one amount, one address and one name. Mocked response: sender Musterwerke, content Rechnung, date 20250301, confidence high; 312 input / 48 output tokens; clock 1.6 seconds. The original cost formula produces CHF 0.0004. The original default categoriser selects 09_Shopping-Memberships. It is shown as returned, not adjusted for presentation. No API request was made.

## Source references

- [dok_namer.py](../dok_namer.py)
- [categories.yaml.example](../categories.yaml.example)

## Maintenance

The PNG is a static documentation asset; no production code or dependency was changed. Its outer framing was authored in HTML/CSS and captured with Chromium, without generative image synthesis. The demo label is embedded in the pixels as well as the README caption. Keep both when reusing it.

This change targets only this public mirror. The private-to-public synchronisation may replace README.md and may omit or remove public-only assets. Durable preservation would require a separately authorised change to the private sync source/allowlist; none was made here. Recheck the README and asset after future syncs.
