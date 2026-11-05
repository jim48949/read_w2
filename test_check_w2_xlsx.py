import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from openpyxl import Workbook, load_workbook

from check_w2 import DEFAULT_RULES
from check_w2_xlsx import check_workbook, print_report
from test_check_w2 import FORM, NOTICE, INSTRUCTIONS


def add_employee(sheet, start=1):
    for index in range(3):
        row = start + index * 6
        sheet.cell(row, 1, "a Employee's social security number")
        sheet.cell(row + 1, 1, 'OMB No. 1545-0029')
        sheet.cell(row + 2, 1, FORM.replace('OMB No. 1545-0029', '').replace('2026', ''))
        sheet.cell(row + 3, 2, 2026)
    sheet.cell(start + 18, 1, 'Notice to Employee')
    sheet.cell(start + 19, 1, NOTICE.replace('Notice to Employee', ''))
    sheet.cell(start + 21, 1, 'Instructions for Employee (See also Notice to Employee on the back of Copy B.)')
    sheet.cell(start + 22, 1, INSTRUCTIONS.split('2026 ', 1)[1] + ' 2026')
    return start + 25


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'input.xlsx'
        self.book = Workbook()
        self.addCleanup(self.book.close)
        self.sheet = self.book.active

    def check(self):
        self.book.save(self.path)
        return check_workbook(self.path, DEFAULT_RULES)

    def test_three_employees_one_pass_each(self):
        start = 1
        for _ in range(3):
            start = add_employee(self.sheet, start)
        report = self.check()
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['employees_checked'], 3)
        self.assertEqual(report['regions_checked'], 15)
        output = StringIO()
        with redirect_stdout(output):
            print_report(report)
        self.assertEqual(output.getvalue().splitlines(), [
            'PASS: Employee 1', 'PASS: Employee 2', 'PASS: Employee 3',
            'Summary: 3 employee(s), 3 passed, 0 failed'])

    def test_only_middle_employee_fails_with_cell_location(self):
        next_start = add_employee(self.sheet)
        end = add_employee(self.sheet, next_start)
        add_employee(self.sheet, end)
        cell = self.sheet.cell(next_start + 2, 1)
        cell.value = cell.value.replace('14a Other', '14 Other')
        report = self.check()
        self.assertEqual([e['passed'] for e in report['employees']], [True, False, True])
        output = StringIO()
        with redirect_stdout(output):
            print_report(report)
        self.assertIn('Box 14a Other', output.getvalue())
        self.assertIn('worksheet 1, rows 26-31', output.getvalue())
        self.assertNotIn('OMB number', output.getvalue())

    def test_missing_omb_is_not_hidden_by_another_copy(self):
        add_employee(self.sheet)
        self.sheet['A8'] = None
        report = self.check()
        self.assertFalse(report['passed'])
        self.assertEqual(report['regions_checked'], 5)
        self.assertFalse(report['results'][1]['passed'])

    def test_missing_ssn_header_uses_omb_fallback(self):
        add_employee(self.sheet)
        self.sheet['A7'] = None
        self.assertTrue(self.check()['passed'])

    def test_merged_cells_and_split_cell_labels(self):
        add_employee(self.sheet)
        self.sheet.merge_cells('A1:D1')
        self.sheet.merge_cells('A19:D19')
        self.sheet['A2'] = 'OMB No.'
        self.sheet['B2'] = '1545-0029'
        self.assertTrue(self.check()['passed'])

    def test_old_notice_and_instruction_amounts_fail(self):
        for address, new, old in [('A20', '$11,439.00', '$10,918.20'),
                                  ('A20', '$6,717.90', '$6,409.20'),
                                  ('A23', '$27,500', '$26,500'),
                                  ('A23', '$24,500', '$23,500')]:
            with self.subTest(old=old):
                add_employee(self.sheet)
                self.sheet[address] = self.sheet[address].value.replace(new, old, 1)
                self.assertFalse(self.check()['passed'])

    def test_numeric_wrong_year_fails(self):
        add_employee(self.sheet)
        self.sheet['B10'] = 2025
        self.assertFalse(self.check()['passed'])

    def test_missing_notice_not_borrowed_from_next_employee(self):
        next_start = add_employee(self.sheet)
        self.sheet['A19'] = None
        self.sheet['A20'] = None
        add_employee(self.sheet, next_start)
        report = self.check()
        self.assertEqual([e['passed'] for e in report['employees']], [False, True])

    def test_multiple_visible_sheets_and_hidden_sheet(self):
        add_employee(self.sheet)
        other = self.book.create_sheet('PRIVATE EMPLOYEE')
        add_employee(other)
        hidden = self.book.create_sheet('ignored')
        hidden.sheet_state = 'hidden'
        hidden['A1'] = 'not a W-2'
        report = self.check()
        self.assertTrue(report['passed'])
        self.assertEqual(report['employees_checked'], 2)
        self.assertNotIn('PRIVATE EMPLOYEE', json.dumps(report))

    def test_sheet_boundaries_do_not_complete_incomplete_employee(self):
        add_employee(self.sheet)
        self.sheet['A22'] = None
        self.sheet['A23'] = None
        other = self.book.create_sheet()
        add_employee(other)
        report = self.check()
        self.assertEqual([e['passed'] for e in report['employees']], [False, True])

    def test_hidden_rows_and_column_ranges_cannot_satisfy_rules(self):
        add_employee(self.sheet)
        self.sheet['A3'] = self.sheet['A3'].value.replace('14a Other', '')
        self.sheet['D3'] = '14a Other'
        self.sheet.column_dimensions.group('C', 'E', hidden=True)
        self.assertFalse(self.check()['passed'])
        self.sheet['A3'] = self.sheet['A3'].value + ' 14a Other'
        self.sheet.row_dimensions[2].hidden = True
        self.assertFalse(self.check()['passed'])

    def test_formula_and_excel_error_rejected(self):
        add_employee(self.sheet)
        for value in ('=2026', '#VALUE!'):
            self.sheet['B4'] = value
            with self.assertRaises(ValueError):
                self.check()

    def test_blank_and_unknown_workbooks(self):
        self.assertFalse(self.check()['passed'])
        self.sheet['A1'] = 'Unknown template'
        with self.assertRaises(ValueError):
            self.check()

    def test_cli_report_privacy_and_exit_codes(self):
        add_employee(self.sheet)
        self.sheet['D3'] = 'PRIVATE EMPLOYEE'
        self.book.save(self.path)
        report_path = Path(self.temp.name) / 'report.json'
        command = [sys.executable, str(Path(__file__).with_name('check_w2_xlsx.py')), str(self.path), '--json', str(report_path)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(report_path.read_text())['passed'])
        self.assertNotIn('PRIVATE EMPLOYEE', report_path.read_text() + result.stdout)
        self.sheet['B4'] = 2025
        self.book.save(self.path)
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
        self.path.unlink()
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
