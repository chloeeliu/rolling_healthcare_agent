# General ICU Autoformalized Guideline Folder

This folder is the scaffold for the guideline corpus used by the autoformalized general ICU monitoring benchmark.

## Layout

- [txt](/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/txt)
  - flat `.txt` guideline files for `search_guidelines`
- [seed_sources.md](/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/seed_sources.md)
  - initial external source ideas and curation notes

## Important runtime note

The current DuckDB helper `search_guidelines()` expects a flat directory of `.txt` files.

So when configuring the session, point `guidelines_dir` at:

- `/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/txt`

## Intended use

This directory should contain compact, benchmark-appropriate guideline text files that help the model:

- orient to the disease head
- understand clinically meaningful thresholds
- map disease names to likely evidence functions

These files should be:

- concise
- task-focused
- stable over time
- not excessively long

## Suggested file pattern

The easiest pattern for `search_guidelines()` is one head per file:

- `infection.txt`
- `sepsis.txt`
- `aki.txt`
- `oliguria.txt`
- `respiratory_support.txt`
- `vasoactive_support.txt`
- `neurologic_deterioration.txt`
- `hyperlactatemia.txt`
- `severe_acidemia.txt`
- `coagulopathy.txt`

Each file should include:

- a short head description
- key escalation thresholds
- likely relevant autoformalized functions
- source links used for curation

The guideline files should be compact summaries, not raw webpage dumps.
