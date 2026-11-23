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

The visual and this public README are maintained together in the working repository. The public mirror receives `docs/demo-run.png` and this provenance file through the existing allowlist. The sync checks the active README image reference, image signature, provenance link and staged file selection before replacing any public content. A missing or excluded asset stops publication instead of removing the hero.

Update the source README and asset together. The image uses exclusively synthetic data and staged model responses; keep the embedded demo label and caption. Only this reviewed image path is added to the binary allowlist. Existing privacy checks remain in place.
