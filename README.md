# W-2 HTML update checker

Read a local Strategy/MicroStrategy Report Services HTML export and check each detected W-2 form copy, Notice to Employee, and Instructions for Employee section. This version reads HTML instead of PDF; PDF grid and password options have been removed.

## Install and run

Requires Python 3.10 or newer.

```sh
cd /workspace/read_w2
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python check_w2.py "/path/to/export.html" --json report.json
```

The report directory must already exist. Exit status is `0` for all checks passed, `1` for failed checks or missing sections, and `2` for an input/configuration/parser error. Reports identify HTML block numbers and section types, without employee names or extracted text. Processing is local; scripts are not executed and linked images/styles/resources are not downloaded. Keep employee exports and reports out of Git.

## Employee results

Console output shows one result per employee, with details only for failed checks:

```text
PASS: Employee 1
FAIL: Employee 2
  FAIL: form 1, HTML block 6: Box 14a Other (required matches=0, forbidden matches=1)
PASS: Employee 3
Summary: 3 employee(s), 2 passed, 1 failed
```

Missing/extra sections and sections out of order are also reported for the affected packet. The default expects three form copies per employee. Use `--forms-per-employee 1` for a template with one copy. JSON includes an `employees` array with per-employee status and errors, and retains detailed section results and match counts for troubleshooting.

## Checks

- Each form copy: OMB No. **1545-0029**, **14a Other**, **W-2 Form Page 1 of 1**, and **2026**. Flags old Box 14 and Copy wording and other OMB numbers.
- Each Notice: **2026**, **$11,439.00** in the multiple-employer sentence, and **$6,717.90** in the railroad-employer sentence. The latter accepts the sample's “Tier 2 RRTA” wording as well as “social security.” Flags the two previous amounts.
- Each Instructions section, Box 12: **2026**, **$24,500** in both requested deferral sentences, and **$27,500** for the 403(b) limit. Flags $23,500 and $26,500. The SIMPLE-plan amount is not checked because no change to it was requested.

Each employee packet must contain three consecutive form copies, followed by one Notice and one Instructions section. Every detected copy/section is checked separately; one good form cannot satisfy another form's missing label. Employees are numbered by packet order in the export; names and employee IDs are not extracted. Address blocks do not split a packet. Incomplete packets fail; grouping assumes the repeated layout you described rather than matching employee identities. The year rule flags standalone 20xx numbers other than 2026; unrelated four-digit numbers or historical references may need review.

## Supported HTML structure

The default selects `.mstrDocSubSection > div`, matching the supplied export. Form copies are recognized by OMB, W-2 Form, or Box 14 labels. Unrecognized auxiliary blocks (such as the sample's address block) are counted as ignored. Review `ignored_blocks` in JSON if your template changes: a block stripped of every identifying label could otherwise be ignored. No recognized/checkable sections fails the document.

For shared Notice/Instructions blocks, the checker uses standalone heading spans and their exported CSS `top` pixel positions, rather than DOM ordering. Columns within eight pixels of a heading are included in that section. The supplied export puts some body text before headings in DOM order. Keep one occurrence of each section type per shared block; different report templates, repeated headings within a block, or differently positioned columns may require adapting extraction.

For other templates, use `--block-selector 'CSS selector'` to select disjoint report containers. Explicitly scoped HTML containers can instead be authored as:

```html
<section data-w2-scope="form">...complete W-2 form text...</section>
<section data-w2-scope="notice">...complete notice text...</section>
<section data-w2-scope="instructions">...complete instructions text...</section>
```

The default selector recognizes these too. Nested selected blocks are rejected to avoid double counting. All exported text must be present in the saved HTML, not loaded only by JavaScript.

## Custom rules

```sh
.venv/bin/python check_w2.py export.html --rules rules.example.json
```

The JSON array replaces the defaults. Each rule has `name`, a case-insensitive Python `required` regex, an optional `forbidden` regex, and optional `scope` (`form`, `notice`, `instructions`, or `all`). Required text must occur and forbidden text must not occur. Each requested scope must be found. Escape backslashes in JSON. HTML entities and whitespace are normalized; text may be split across tags.

## Limits and validation

This validates HTML text and the supplied export's block structure, not rendered appearance or IRS compliance. Simple class/inline `display:none`, `visibility:hidden`/`collapse`, and `hidden` elements are excluded. This is not a full browser CSS engine: complex selectors, cascade precedence, external styles, clipping, image text, and visual overlap are not validated. Review a rendered sample before relying on a new export template.

```sh
.venv/bin/python -m unittest -v
```

Tests cover all requested old values, each section's year, both deferral occurrences, multi-form isolation, HTML entities, hidden/script content, out-of-order positioned sections, missing sections, unsupported layouts, CLI exit codes, and report privacy. Tests use synthetic content; the employee attachment is not committed as a fixture.
