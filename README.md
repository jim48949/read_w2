# W-2 HTML and Excel update checkers

Read a local Strategy/MicroStrategy Report Services HTML export and check each detected W-2 form copy, Notice to Employee, and Instructions for Employee section. This version reads HTML instead of PDF; PDF grid and password options have been removed.

## Windows first-time setup and launchers

1. Download and extract the complete project ZIP to a writable folder. Keep the scripts together.
2. Double-click **install.bat**. It finds Python 3.10 or newer, creates `.venv`, and installs both HTML and Excel dependencies. If Python is missing, it attempts a per-user Python 3.12 installation through Windows Package Manager (WinGet). Internet access is needed during installation. If WinGet is unavailable, the installer explains how to install Python from python.org and rerun it. No administrator terminal is required for the intended per-user setup.
3. Drag **one HTML file onto launch_html.bat**, or **one Excel file onto launch_xlsx.bat**. Alternatively, double-click the appropriate launcher and paste the file path when prompted; surrounding quotes are accepted.
4. Read the employee results in the window. A separate report is saved under the project's `reports` folder on each run. Press a key to close the window.

The installer can be rerun to refresh dependencies. Launchers use this project's virtual environment, regardless of the terminal's current folder. If it is missing, they ask you to run `install.bat`. Installer/launcher windows stay open on errors too. Keep `windows_install.ps1` and `windows_launcher.py` beside the batch files; they provide the shared setup and launch logic. The installer runs its local PowerShell helper with a process-only execution-policy override; it does not change the machine's execution-policy settings. Organization-managed restrictions may still require your IT team's assistance.

This is a Python-based installation, not a standalone `.exe`. After installation, checking files is local and requires no Internet access. The batch/PowerShell entry points need a Windows smoke test; their shared Python launch logic is covered by automated tests on Linux.

## Install and run

Requires Python 3.10 or newer.

```sh
cd /workspace/read_w2
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python check_w2.py "/path/to/export.html" --json report.json
```

The report directory must already exist. Exit status is `0` for all checks passed, `1` for failed checks or missing sections, and `2` for an input/configuration/parser error. Reports identify HTML block numbers and section types, without employee names or extracted text. Processing is local; scripts are not executed and linked images/styles/resources are not downloaded. Keep employee exports and reports out of Git.

## Separate Excel version (.xlsx)

`check_w2_xlsx.py` reads the supplied workbook format directly. The HTML version remains `check_w2.py`; neither input file is modified. Both versions share the validation rules and employee grouping, so keep both Python files together.

Install the optional Excel dependencies on Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-xlsx.txt
.\.venv\Scripts\python.exe check_w2_xlsx.py "C:\Documents\W2 2026 emp3.xlsx" --json report.json
```

On Linux/macOS, use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`. The same `--rules` and `--forms-per-employee` options are supported. The result uses one PASS/FAIL per employee; failures identify the worksheet number, row range, and failed rule. JSON excludes employee text and worksheet names. The supplied sample was checked successfully: **3 employees, 15 sections, all passed**.

The Excel reader supports the sample's vertically stacked layout, including merged cells, three copies of each numbered form page followed by Notice and Instructions, and multiple visible worksheets. It finds each form using the “a Employee's social security number” header; an OMB heading within three rows is part of that form. An OMB heading farther away can identify a form with a missing SSN header. Notice and Instructions must have recognizable heading cells. Rows are read top to bottom, cells left to right; text within each cell is preserved. Numeric years are supported, and simple dollar-formatted numeric cells are converted to dollar strings.

Each employee packet must be complete within one worksheet. Visible nonempty worksheets without recognized headers produce an input error; blank worksheets are ignored. Hidden worksheets, rows, and columns are excluded. Formula and Excel error cells in visible content are rejected: export/recalculate to a workbook containing values before checking. The checker never evaluates formulas, runs macros, or retrieves external links. Password-encrypted workbooks, legacy `.xls`, `.xlsm`, side-by-side forms, and labels stored only in images/text boxes are unsupported. If both form-start identifiers disappear, section detection can fail; review a rendered workbook and validate new layouts. Cell text checks do not verify formatting, printed appearance, clipping, conditional formatting, or IRS compliance.

Run the full HTML and Excel suites after installing `requirements-xlsx.txt`:

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

For an HTML-only installation, run `python -m unittest -v test_check_w2` instead. Employee workbook attachments and generated reports are ignored by Git and are not test fixtures.

## Employee results

Console output shows one result per employee, with details only for failed checks:

```text
PASS: Employee 1
FAIL: Employee 2
  FAIL: form 1, HTML block 6: Box 14a Other (required matches=0, forbidden matches=1)
PASS: Employee 3
Summary: 3 employee(s), 2 passed, 1 failed
```

Missing/extra sections and sections out of order are also reported for the affected packet. The default expects three copies **per numbered page**. Page labels determine how many pages belong to the employee. For example, three “Page 1 of 2” forms and three “Page 2 of 2” forms, followed by Notice and Instructions, produce one employee result. Single-page and multi-page employees may appear in the same file. Use `--forms-per-employee 1` for a template with one copy per page; the option name is retained for compatibility.

Each form must have one “W-2 Form Page X of Y” label. All copies must agree on Y, each page must have the expected number of copies, and pages must appear in order. Missing copies/pages, duplicate or invalid page numbers, inconsistent totals, and legacy “Copy” wording fail. When a new Page 1 begins after a completed copy set, or forms follow Notice/Instructions, a new employee group begins. A packet missing its Notice/Instructions still fails rather than borrowing those sections from the next group. Grouping uses label order, not employee identities; severely damaged/missing labels can make boundaries ambiguous and require review. An employee absent entirely from the input cannot be detected without an external employee list. JSON includes an `employees` array with per-employee status and errors, and retains detailed section results and match counts for troubleshooting.

## Checks

- Each form copy: OMB No. **1545-0029**, **14a Other**, **W-2 Form Page X of Y**, and **2026**. Flags old Box 14 and Copy wording and other OMB numbers.
- Each Notice: **2026**, **$11,439.00** in the multiple-employer sentence, and **$6,717.90** in the railroad-employer sentence. The latter accepts the sample's “Tier 2 RRTA” wording as well as “social security.” Flags the two previous amounts.
- Each Instructions section, Box 12: **2026**, **$24,500** in both requested deferral sentences, and **$27,500** for the 403(b) limit. Flags $23,500 and $26,500. The SIMPLE-plan amount is not checked because no change to it was requested.

Each employee packet must contain three consecutive copies of each numbered page (Page 1 through Page Y), followed by one Notice and one Instructions section. Every detected copy/section is checked separately; one good form cannot satisfy another form's missing label. Employees are numbered by packet order in the export; names and employee IDs are not extracted. Address blocks do not split a packet. Incomplete packets fail; grouping assumes the repeated layout you described rather than matching employee identities. The year check examines contextual references rather than every four-digit number. In Excel, it reads the year immediately following “Wage and Tax Statement” (or an explicit “Tax year”/“Calendar year” label) on the same row. For the positioned HTML export it reads the year span to the right of “Wage and Tax Statement,” within an eight-pixel vertical band, even if DOM order differs. Other HTML templates can use explicit tax-year labels.

Notice/Instructions year checks cover the sample's EITC, specified-amount, income-limit, multiple-employer, age-in-year, and December 31 references, plus explicit tax/calendar-year labels. Street addresses, account numbers, and unrelated amounts are excluded. A recognized reference with an incorrect year fails; no recognized year also fails instead of accepting an unrelated 2026. New wording or layouts may require extending these contexts. This is template-based validation, not a general detector of every possible year reference.

For these checks, `required matches` counts recognized tax-year references equal to 2026; `forbidden matches` counts recognized references with a different four-digit year. Missing fields can produce zero for both counts and still fail. If you use `--rules` with an older custom JSON, update its year entries (including `year_context`) and page-label rule from `rules.example.json` to enable context checking and accept multiple pages.

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

The JSON array replaces the defaults. Each rule has `name`, a case-insensitive Python `required` regex, an optional `forbidden` regex, and optional `scope` (`form`, `notice`, `instructions`, or `all`). Required text must occur and forbidden text must not occur. Each requested scope must be found. Optional `year_context` (`form`, `notice`, or `instructions`) restricts a year rule to recognized tax-year references before applying its regexes. Escape backslashes in JSON. HTML entities and whitespace are normalized; text may be split across tags.

## Limits and validation

This validates HTML text and the supplied export's block structure, not rendered appearance or IRS compliance. Simple class/inline `display:none`, `visibility:hidden`/`collapse`, and `hidden` elements are excluded. This is not a full browser CSS engine: complex selectors, cascade precedence, external styles, clipping, image text, and visual overlap are not validated. Review a rendered sample before relying on a new export template.

```sh
.venv/bin/python -m unittest -v test_check_w2
```

Tests cover all requested old values, each section's year, both deferral occurrences, multi-form isolation, HTML entities, hidden/script content, out-of-order positioned sections, missing sections, unsupported layouts, CLI exit codes, and report privacy. Tests use synthetic content; the employee attachment is not committed as a fixture.
