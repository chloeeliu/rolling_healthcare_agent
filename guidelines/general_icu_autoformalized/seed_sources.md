# Seed Sources For General ICU Autoformalized Benchmark

This file tracks initial external sources to seed the guideline corpus for the benchmark.

The benchmark should prefer concise task-specific `.txt` guideline summaries in the flat `txt/` directory, but these links are a good starting point for curation.

## Suggested seed sources

- Sepsis:
  - [Early Recognition and Initial Management of Sepsis in Adult Patients](https://www.ncbi.nlm.nih.gov/books/NBK598311/)
- Respiratory failure:
  - [Respiratory Failure - What Is Respiratory Failure? | NHLBI, NIH](https://www.nhlbi.nih.gov/health/respiratory-failure)
  - [Acute Respiratory Distress Syndrome | NHLBI, NIH](https://www.nhlbi.nih.gov/health/ards)
- Kidney injury:
  - [Acute Kidney Injury - NIDDK](https://www.niddk.nih.gov/research-funding/research-programs/acute-kidney-injury)

## Recommended first curation batch

The first pass does not need a perfect source for every head.

The practical starting point is:

- `sepsis.txt`
  - summarize recognition, hypoperfusion, vasopressor escalation, and timing cues from the NCBI Bookshelf sepsis guideline
- `respiratory_support.txt`
  - summarize what constitutes respiratory failure and why escalating support matters from NHLBI background material
- `aki.txt`
  - summarize why AKI severity and worsening renal function matter using NIDDK background material

Then add benchmark-specific summary files for:

- `oliguria.txt`
- `vasoactive_support.txt`
- `hyperlactatemia.txt`
- `severe_acidemia.txt`
- `neurologic_deterioration.txt`
- `coagulopathy.txt`

## Curation notes

- NIH-family sources are a good default seed source.
- Some benchmark heads will likely need non-NIH society guidance as well.
- AKI is the clearest example: KDIGO-style guidance may still be needed for the final frozen benchmark spec.
- The `.txt` files used by the benchmark should be compact benchmark summaries, not raw full-page dumps.
