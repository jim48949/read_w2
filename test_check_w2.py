import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from check_w2 import DEFAULT_RULES, check_document, load_rules

FORM = 'W-2 Form Page 1 of 1 OMB No. 1545-0029 2026 14a Other'
NOTICE = ('Notice to Employee 2026 If you had more than one employer in 2026 and more than '
          '$11,439.00 in social security taxes. If you had more than one railroad employer and more than '
          '$6,717.90 in Tier 2 RRTA tax was withheld.')
INSTRUCTIONS = ('Instructions for Employee (See also Notice to Employee on the back of Copy B.) 2026 '
                'Box 12.The following explains codes. Elective deferrals (codes E) and designated Roth '
                'contributions (codes BB and EE) under all plans are generally limited to a total of '
                '$24,500 ($17,000 if you only have SIMPLE plans; $27,500 for section 403(b) plans '
                'if you qualify for the 15-year rule explained in Pub. 571). '
                'Deferrals under code G are limited to $24,500.')


def document(form=FORM, notice=NOTICE, instructions=INSTRUCTIONS):
    return ''.join(f'<section data-w2-scope="{scope}">{text}</section>' for scope, text in
                   [('form', form)] * 3 + [('notice', notice), ('instructions', instructions)])


class HTMLTests(unittest.TestCase):
    def check(self, html, forms_per_employee=3):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'forms.html'
            path.write_text(html)
            return check_document(path, DEFAULT_RULES, forms_per_employee=forms_per_employee)

    def test_current_values_pass(self):
        report = self.check(document())
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['regions_checked'], 5)

    def test_every_requested_old_value_fails(self):
        html = document()
        for new, old in [('1545-0029', '1545-0008'), ('14a Other', '14 Other'),
                         ('Page 1 of 1', 'Copy 1 of 1'), ('2026', '2025'),
                         ('$11,439.00', '$10,918.20'), ('$6,717.90', '$6,409.20'),
                         ('$27,500', '$26,500')]:
            with self.subTest(old=old):
                self.assertFalse(self.check(html.replace(new, old))['passed'])

    def test_both_deferral_occurrences_required(self):
        for index in (1, 2):
            text = INSTRUCTIONS.replace('$24,500', '$23,500', index)
            if index == 2:
                text = text.replace('$23,500', '$24,500', 1)
            self.assertFalse(self.check(document(instructions=text))['passed'])

    def test_each_section_year_checked(self):
        for field, text in [('form', FORM), ('notice', NOTICE), ('instructions', INSTRUCTIONS)]:
            self.assertFalse(self.check(document(**{field: text.replace('2026', '2025')}))['passed'])

    def test_good_form_cannot_hide_bad_form(self):
        report = self.check(document() + '<section data-w2-scope="form">' + FORM.replace('14a Other', '') + '</section>')
        self.assertFalse(report['passed'])
        self.assertTrue(report['results'][0]['passed'])
        self.assertFalse(report['results'][-1]['passed'])

    def test_missing_sections_fail(self):
        report = self.check(f'<section data-w2-scope="form">{FORM}</section>')
        self.assertEqual(report['missing_sections'], ['instructions', 'notice'])
        self.assertFalse(report['passed'])

    def test_scripts_hidden_content_and_entities(self):
        html = document().replace('OMB No.', 'OMB&nbsp;<b>No.</b>')
        html += '<script>2025 $10,918.20</script><style>.hide {display:none}</style>'
        html = html.replace('14a Other', '14a Other <span class="hide">14 Other</span>')
        self.assertTrue(self.check(html)['passed'])
        html = document(form='<span hidden>' + FORM + '</span>')
        self.assertFalse(self.check(html)['passed'])

    def test_report_blocks_and_coordinate_sections(self):
        # Deliberately place content before headings in DOM order, matching the export.
        html = '''<style>.notice {top:150px} .noticebody {top:180px}
        .instructions {top:1370px} .instructionbody {top:1368px}</style>'''
        html += '<div class="mstrDocSubSection"><div>' + FORM + '</div></div>'
        html += '<div class="mstrDocSubSection"><div>'
        html += '<span class="noticebody">' + NOTICE.replace('Notice to Employee', '') + '</span>'
        html += '<span class="instructionbody">' + INSTRUCTIONS.split('2026 ', 1)[1] + ' 2026</span>'
        html += '<span class="notice">Notice to Employee</span>'
        html += '<span class="instructions">Instructions for Employee (See also Notice to Employee on the back of Copy B.)</span>'
        html += '</div></div>'
        report = self.check(html, forms_per_employee=1)
        self.assertTrue(report['passed'], report)

    def test_unknown_template_fails(self):
        with self.assertRaises(ValueError):
            self.check('<html><body>Unrecognized export</body></html>')

    def test_overlapping_blocks_fail(self):
        with self.assertRaises(ValueError):
            self.check('<div data-w2-scope="form"><div data-w2-scope="notice">x</div></div>')

    def test_example_rules(self):
        self.assertEqual(load_rules(Path(__file__).with_name('rules.example.json')), DEFAULT_RULES)

    def test_cli_and_private_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, report = Path(tmp) / 'input.html', Path(tmp) / 'report.json'
            path.write_text(document(form=FORM + ' PRIVATE EMPLOYEE'))
            command = [sys.executable, str(Path(__file__).with_name('check_w2.py')), str(path), '--json', str(report)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('PRIVATE EMPLOYEE', report.read_text() + result.stdout)
            self.assertTrue(json.loads(report.read_text())['passed'])
            path.write_text(document(form=FORM.replace('14a Other', '14 Other')))
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
            path.unlink()
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)


class EmployeeOutputTests(unittest.TestCase):
    check = HTMLTests.check
    def test_three_employees_print_one_line_each(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from check_w2 import print_report
        report = self.check(document() * 3)
        self.assertTrue(report['passed'])
        self.assertEqual(report['employees_checked'], 3)
        output = StringIO()
        with redirect_stdout(output):
            print_report(report)
        self.assertEqual(output.getvalue().splitlines(), [
            'PASS: Employee 1', 'PASS: Employee 2', 'PASS: Employee 3',
            'Summary: 3 employee(s), 3 passed, 0 failed'])

    def test_only_failed_checks_shown_for_middle_employee(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from check_w2 import print_report
        bad = document().replace('14a Other', '14 Other', 1)
        report = self.check(document() + bad + document())
        self.assertFalse(report['passed'])
        self.assertEqual([e['passed'] for e in report['employees']], [True, False, True])
        output = StringIO()
        with redirect_stdout(output):
            print_report(report)
        text = output.getvalue()
        self.assertIn('PASS: Employee 1\nFAIL: Employee 2\n', text)
        self.assertIn('form 1, HTML block 6: Box 14a Other', text)
        self.assertIn('PASS: Employee 3', text)
        self.assertNotIn('OMB number', text)
        self.assertNotIn('Tax year', text)
        self.assertNotIn('PASS: HTML block', text)

    def test_missing_notice_does_not_borrow_next_employees_notice(self):
        bad = document().replace(f'<section data-w2-scope="notice">{NOTICE}</section>', '')
        report = self.check(bad + document())
        self.assertEqual([e['passed'] for e in report['employees']], [False, True])
        self.assertIn('Expected 1 notice section(s); found 0', report['employees'][0]['errors'])

    def test_missing_all_back_sections_still_starts_new_employee(self):
        forms = ''.join(f'<section data-w2-scope="form">{FORM}</section>' for _ in range(3))
        report = self.check(forms + document())
        self.assertEqual([e['passed'] for e in report['employees']], [False, True])

    def test_incomplete_final_employee_fails(self):
        report = self.check(document() + f'<section data-w2-scope="form">{FORM}</section>')
        self.assertEqual([e['passed'] for e in report['employees']], [True, False])
        self.assertIn('Expected 3 form section(s); found 1', report['employees'][1]['errors'])

    def test_ignored_address_block_does_not_split_employee(self):
        html = document().replace('<section data-w2-scope="notice">',
            '<div class="mstrDocSubSection"><div>Address block</div></div><section data-w2-scope="notice">')
        report = self.check(html * 2)
        self.assertTrue(report['passed'])
        self.assertEqual(report['ignored_blocks'], 2)
        self.assertEqual(report['employees_checked'], 2)
