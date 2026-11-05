import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from test_check_w2 import document
from test_check_w2_xlsx import add_employee
from windows_launcher import launch


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='W2 launch & space ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        real_run = subprocess.run
        mock_run = patch('windows_launcher.subprocess.run',
                         side_effect=lambda *args, **kwargs: real_run(*args, **kwargs, capture_output=True, text=True))
        mock_run.start()
        self.addCleanup(mock_run.stop)
        for script in ('check_w2.py', 'check_w2_xlsx.py'):
            shutil.copy(Path(__file__).with_name(script), self.root / script)

    def test_html_spaces_special_characters_and_unique_reports(self):
        source = self.root / 'Employee & sample ! 2026.html'
        source.write_text(document())
        for _ in range(2):
            with redirect_stdout(StringIO()) as output:
                result = launch('html', str(source), self.root)
            self.assertEqual(result, 0)
            self.assertIn('Report saved to:', output.getvalue())
        reports = list((self.root / 'reports').glob('*.json'))
        self.assertEqual(len(reports), 2)
        self.assertTrue(all(json.loads(p.read_text())['passed'] for p in reports))
        self.assertEqual(source.read_text(), document())

    def test_xlsx_launcher(self):
        source = self.root / 'Employee sample.xlsx'
        book = Workbook()
        add_employee(book.active)
        book.save(source)
        book.close()
        with redirect_stdout(StringIO()):
            self.assertEqual(launch('xlsx', str(source), self.root), 0)
        report = next((self.root / 'reports').glob('*.json'))
        self.assertTrue(json.loads(report.read_text())['passed'])

    def test_failed_validation_keeps_report_and_exit_code(self):
        source = self.root / 'failure.html'
        source.write_text(document().replace('14a Other', '14 Other', 1))
        with redirect_stdout(StringIO()):
            self.assertEqual(launch('html', str(source), self.root), 1)
        report = next((self.root / 'reports').glob('*.json'))
        self.assertFalse(json.loads(report.read_text())['passed'])

    def test_input_prompt_accepts_quoted_path(self):
        source = self.root / 'prompt.html'
        source.write_text(document())
        with patch('builtins.input', return_value=f'"{source}"'), redirect_stdout(StringIO()):
            self.assertEqual(launch('html', project_root=self.root), 0)

    def test_wrong_type_missing_file_and_cancel_do_not_launch(self):
        for filename in ('missing.html', 'wrong.xlsx', ''):
            with patch('builtins.input', return_value=''), patch('windows_launcher.subprocess.run') as run, redirect_stdout(StringIO()):
                self.assertEqual(launch('html', filename, self.root), 2)
                run.assert_not_called()

    def test_parser_error_does_not_claim_saved_report(self):
        source = self.root / 'unsupported.html'
        source.write_text('<p>Unknown template</p>')
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(launch('html', str(source), self.root), 2)
        self.assertNotIn('Report saved to:', output.getvalue())
        self.assertEqual(list((self.root / 'reports').glob('*.json')), [])
