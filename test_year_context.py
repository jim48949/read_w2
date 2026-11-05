import unittest

from check_w2 import DEFAULT_RULES, inspect_text


class YearContextTests(unittest.TestCase):
    def check_year(self, scope, text):
        rules = [r for r in DEFAULT_RULES if r.get('year_context') == scope]
        return inspect_text(text, rules)[0]

    def test_unrelated_form_numbers_are_ignored(self):
        result = self.check_year('form', '2025 Main Street Account 2099 Amount 2000 Wage and Tax Statement 2026')
        self.assertTrue(result['passed'])
        self.assertEqual(result['required_matches'], 1)
        self.assertEqual(result['forbidden_matches'], 0)

    def test_wrong_field_year_cannot_be_hidden_by_2026_in_address(self):
        for year in ('2025', '2027', '1999'):
            with self.subTest(year=year):
                result = self.check_year('form', f'2026 Main Street Wage and Tax Statement {year}')
                self.assertFalse(result['passed'])
                self.assertEqual(result['required_matches'], 0)
                self.assertEqual(result['forbidden_matches'], 1)

    def test_missing_year_field_does_not_use_other_numbers(self):
        result = self.check_year('form', '2026 Main Street Wage and Tax Statement Department of the Treasury')
        self.assertFalse(result['passed'])
        self.assertEqual(result['required_matches'], 0)
        self.assertEqual(result['forbidden_matches'], 0)

    def test_notice_references_are_each_checked(self):
        text = ('EITC for 2026. Specified amount for 2026. For 2026 income limits. '
                'If you had more than one employer in 2026. Publication 2025. 2099 Main Street.')
        result = self.check_year('notice', text)
        self.assertTrue(result['passed'])
        self.assertEqual(result['required_matches'], 4)
        result = self.check_year('notice', text.replace('EITC for 2026', 'EITC for 2025'))
        self.assertFalse(result['passed'])
        self.assertEqual(result['required_matches'], 3)
        self.assertEqual(result['forbidden_matches'], 1)

    def test_instructions_references_are_each_checked(self):
        text = 'At least age 50 in 2026; age 60 through 63 as of December 31, 2026. Account 2025.'
        result = self.check_year('instructions', text)
        self.assertTrue(result['passed'])
        self.assertEqual(result['required_matches'], 2)
        result = self.check_year('instructions', text.replace('December 31, 2026', 'December 31, 2025'))
        self.assertFalse(result['passed'])
        self.assertEqual(result['forbidden_matches'], 1)

    def test_missing_narrative_year_is_not_satisfied_by_unrelated_2026(self):
        self.assertFalse(self.check_year('instructions', 'Box 12. Account number 2026.')['passed'])

    def test_positioned_html_year_can_precede_label_in_dom(self):
        from bs4 import BeautifulSoup
        from check_w2 import html_form_year_text
        block = BeautifulSoup('''<div><span style="top:100px;left:200px">2026</span>
            <span style="top:98px;left:50px">Wage and Tax Statement</span>
            <span style="top:50px;left:200px">2025</span></div>''', 'html.parser').div
        text = html_form_year_text(block, {})
        self.assertEqual(text, 'Wage and Tax Statement 2026')
        self.assertTrue(self.check_year('form', text)['passed'])

    def test_positioned_html_wrong_or_missing_year_not_hidden(self):
        from bs4 import BeautifulSoup
        from check_w2 import html_form_year_text
        for field in ('<span style="top:100px;left:200px">2025</span>', ''):
            block = BeautifulSoup('<div>' + field + '''
                <span style="top:100px;left:50px">Wage and Tax Statement</span>
                <span style="top:50px;left:200px">2026</span></div>''', 'html.parser').div
            self.assertFalse(self.check_year('form', html_form_year_text(block, {}))['passed'])
