#!/usr/bin/env python3
"""Validate 2026 W-2 updates in a local .xlsx report export."""
import argparse
import json
import re
import sys
from itertools import groupby
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string

from check_w2 import FORM_YEAR, group_employees, inspect_text, load_rules, positive_int

FORM_HEADER = re.compile(r"^(?:a\s+)?Employee[’']s\s+social\s+security\s+number\b", re.I)
NOTICE_HEADER = re.compile(r"^Notice\s+to\s+Employee\s*$", re.I)
INSTRUCTIONS_HEADER = re.compile(r"^Instructions?\s+for\s+Employees?\b", re.I)
OMB_HEADER = re.compile(r"^OMB\s*(?:NO\.?)?\b", re.I)


def cell_text(cell):
    if cell.data_type == 'f':
        raise ValueError("Formula cells are unsupported; export calculated values first")
    if cell.data_type == 'e':
        raise ValueError("Workbook contains an Excel error value")
    value = cell.value
    if value is None:
        return ''
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if '$' in cell.number_format:
            return f'${value:,.2f}'
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
    return ' '.join(str(value).split())


def worksheet_sections(sheet):
    """Read visible cells by row; use headings to bound each exported section."""
    hidden_columns = set()
    for dimension in sheet.column_dimensions.values():
        if dimension.hidden:
            start = dimension.min or column_index_from_string(dimension.index)
            hidden_columns.update(range(start, (dimension.max or start) + 1))
    cells = []
    for row in sheet.iter_rows():
        if sheet.row_dimensions[row[0].row].hidden:
            continue
        for cell in row:
            if cell.column in hidden_columns:
                continue
            text = cell_text(cell)
            if text:
                cells.append((cell.row, cell.column, text))
    events = []
    for row, column, text in cells:
        if FORM_HEADER.match(text):
            events.append((row, 'form', 'primary'))
        elif NOTICE_HEADER.fullmatch(text):
            events.append((row, 'notice', 'primary'))
        elif INSTRUCTIONS_HEADER.match(text):
            events.append((row, 'instructions', 'primary'))
        elif OMB_HEADER.match(text):
            events.append((row, 'form', 'omb'))
    starts = []
    for row, scope, source in sorted(set(events)):
        # OMB is normally one row below the SSN heading. It can also identify a
        # form whose SSN heading is missing; don't merge it into the previous copy.
        if source == 'omb' and starts and starts[-1][1] == 'form' and row - starts[-1][0] <= 3:
            continue
        if starts and starts[-1][0] == row:
            if starts[-1][1] != scope:
                raise ValueError("Sections side by side on a single row are unsupported")
            continue
        starts.append((row, scope))
    if cells and not starts:
        raise ValueError("Nonempty worksheet has no supported W-2 section headers")
    sections = []
    for index, (start, scope) in enumerate(starts):
        end = starts[index + 1][0] - 1 if index + 1 < len(starts) else sheet.max_row
        section_cells = [(row, column, text) for row, column, text in cells if start <= row <= end]
        text = ' '.join(text for row, column, text in section_cells)
        year_fields = []
        if scope == 'form':
            for row, row_cells in groupby(section_cells, key=lambda c: c[0]):
                row_text = ' '.join(c[2] for c in row_cells)
                year_fields.extend(m.group(0) for m in FORM_YEAR.finditer(row_text))
        sections.append((scope, start, end, text, ' '.join(year_fields)))
    return sections


def check_workbook(path, rules, forms_per_employee=3):
    if Path(path).suffix.lower() != '.xlsx':
        raise ValueError("Input must be an .xlsx workbook")
    if forms_per_employee < 1:
        raise ValueError("forms_per_employee must be positive")
    workbook = load_workbook(path, data_only=False, keep_links=False)
    employees, regions, seen = [], [], set()
    try:
        for sheet_number, sheet in enumerate(workbook.worksheets, 1):
            if sheet.sheet_state != 'visible':
                continue
            sheet_regions = []
            for scope, start, end, text, year_text in worksheet_sections(sheet):
                seen.add(scope)
                checks = inspect_text(text, [r for r in rules if r.get('scope', 'all') in {'all', scope}],
                                      form_year_text=year_text)
                if not checks:
                    continue
                # Use a worksheet number rather than its possibly sensitive name.
                region = {'sheet': sheet_number, 'row_start': start, 'row_end': end, 'section': scope,
                          'text_available': bool(text.strip()), 'checks': checks,
                          'passed': bool(text.strip()) and all(c['passed'] for c in checks)}
                sheet_regions.append(region)
            groups = group_employees(sheet_regions, forms_per_employee, rules)
            for employee in groups:
                employee['employee'] = len(employees) + 1
                employees.append(employee)
            regions.extend(sheet_regions)
    finally:
        workbook.close()
    missing = sorted({r['scope'] for r in rules if r.get('scope', 'all') != 'all'} - seen)
    return {'passed': bool(employees) and not missing and all(e['passed'] for e in employees),
            'employees': employees, 'employees_checked': len(employees), 'missing_sections': missing,
            'regions_checked': len(regions), 'results': regions}


def print_report(report):
    for employee in report['employees']:
        print(f"{'PASS' if employee['passed'] else 'FAIL'}: Employee {employee['employee']}")
        for error in employee['errors']:
            print(f'  FAIL: {error}')
        form_number = 0
        for result in employee['results']:
            if result['section'] == 'form':
                form_number += 1
            if result['passed']:
                continue
            label = f'form {form_number}' if result['section'] == 'form' else result['section']
            location = f"{label}, worksheet {result['sheet']}, rows {result['row_start']}-{result['row_end']}"
            if not result['text_available']:
                print(f'  FAIL: {location}: No extractable cell text')
            for check in result['checks']:
                if not check['passed']:
                    print(f"  FAIL: {location}: {check['rule']} "
                          f"(required matches={check['required_matches']}, forbidden matches={check['forbidden_matches']})")
    if not report['employees']:
        print('FAIL: No employee sections were checked')
    passed = sum(e['passed'] for e in report['employees'])
    print(f"Summary: {len(report['employees'])} employee(s), {passed} passed, {len(report['employees']) - passed} failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xlsx', type=Path)
    parser.add_argument('--rules', type=Path, help='Custom JSON validation rules (same as HTML version)')
    parser.add_argument('--json', type=Path, help='Save a report without employee text')
    parser.add_argument('--forms-per-employee', type=positive_int, default=3)
    args = parser.parse_args()
    try:
        report = check_workbook(args.xlsx, load_rules(args.rules), args.forms_per_employee)
        if args.json:
            args.json.write_text(json.dumps(report, indent=2) + '\n')
    except Exception as exc:
        print(f'ERROR ({type(exc).__name__}): unable to check workbook or configuration. '
              'Check paths, rules, and worksheet layout; export formula cells as values.', file=sys.stderr)
        return 2
    print_report(report)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
