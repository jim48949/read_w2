import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from openpyxl import Workbook

from check_w2 import DEFAULT_RULES, check_document, print_report
from check_w2_xlsx import check_workbook
from test_check_w2 import FORM, NOTICE, INSTRUCTIONS


def page_labels(total):
    return [(page, total) for page in range(1, total + 1) for _ in range(3)]


def form_text(page, total):
    return FORM.replace('Page 1 of 1', f'Page {page} of {total}')


class MultipageTests(unittest.TestCase):
    def report(self, packets, kind):
        with tempfile.TemporaryDirectory() as tmp:
            if kind == 'html':
                path = Path(tmp) / 'input.html'
                sections = []
                for labels in packets:
                    sections.extend(f'<section data-w2-scope="form">{form_text(p, n)}</section>' for p, n in labels)
                    sections.extend(f'<section data-w2-scope="{scope}">{text}</section>'
                                    for scope, text in [('notice', NOTICE), ('instructions', INSTRUCTIONS)])
                path.write_text(''.join(sections))
                return check_document(path, DEFAULT_RULES)
            path = Path(tmp) / 'input.xlsx'
            book = Workbook()
            sheet = book.active
            row = 1
            for labels in packets:
                for page, total in labels:
                    sheet.cell(row, 1, "a Employee's social security number")
                    sheet.cell(row + 1, 1, 'OMB No. 1545-0029')
                    sheet.cell(row + 2, 1, form_text(page, total).replace('OMB No. 1545-0029', ''))
                    row += 6
                sheet.cell(row, 1, 'Notice to Employee')
                sheet.cell(row + 1, 1, NOTICE)
                sheet.cell(row + 3, 1, 'Instructions for Employee')
                sheet.cell(row + 4, 1, INSTRUCTIONS.split('2026 ', 1)[1] + ' 2026')
                row += 7
            book.save(path)
            book.close()
            return check_workbook(path, DEFAULT_RULES)

    def test_mixed_single_two_three_page_employees(self):
        for kind in ('html', 'xlsx'):
            with self.subTest(kind=kind):
                report = self.report([page_labels(n) for n in (1, 2, 1, 3)], kind)
                self.assertTrue(report['passed'], report)
                self.assertEqual(report['employees_checked'], 4)
                self.assertEqual([e['page_count'] for e in report['employees']], [1, 2, 1, 3])
                self.assertEqual([len(e['results']) for e in report['employees']], [5, 8, 5, 11])

    def test_missing_last_page_does_not_swallow_next_employee(self):
        for kind in ('html', 'xlsx'):
            report = self.report([[(1, 2)] * 3, page_labels(1)], kind)
            self.assertEqual([e['passed'] for e in report['employees']], [False, True])
            self.assertIn('Expected 6 form section(s); found 3', report['employees'][0]['errors'])

    def test_missing_page_copy_fails(self):
        for kind in ('html', 'xlsx'):
            report = self.report([page_labels(2)[:-1], page_labels(1)], kind)
            self.assertEqual([e['passed'] for e in report['employees']], [False, True])

    def test_inconsistent_totals_fail(self):
        for kind in ('html', 'xlsx'):
            labels = page_labels(2)
            labels[4] = (2, 3)
            report = self.report([labels, page_labels(1)], kind)
            self.assertEqual([e['passed'] for e in report['employees']], [False, True])
            self.assertIn('Form 5: expected Page 2 of 2; found Page 2 of 3', report['employees'][0]['errors'])

    def test_missing_middle_page_and_duplicate_page_fail(self):
        for kind in ('html', 'xlsx'):
            for bad in ([(1, 3)] * 3 + [(3, 3)] * 6,
                        [(1, 3)] * 3 + [(2, 3)] * 6):
                report = self.report([bad, page_labels(1)], kind)
                self.assertEqual([e['passed'] for e in report['employees']], [False, True])

    def test_invalid_page_numbers_fail(self):
        for kind in ('html', 'xlsx'):
            for page, total in ((0, 1), (2, 1), (1, 0)):
                self.assertFalse(self.report([[(page, total)] * 3], kind)['passed'])

    def test_numbering_order_checked(self):
        for kind in ('html', 'xlsx'):
            labels = page_labels(2)
            labels[1], labels[4] = labels[4], labels[1]
            self.assertFalse(self.report([labels], kind)['passed'])

    def test_one_pass_line_for_multipage_employee(self):
        report = self.report([page_labels(2), page_labels(1)], 'html')
        output = StringIO()
        with redirect_stdout(output):
            print_report(report)
        self.assertEqual(output.getvalue().splitlines(), [
            'PASS: Employee 1', 'PASS: Employee 2', 'Summary: 2 employee(s), 2 passed, 0 failed'])
