"""Shared implementation for the Windows batch launchers."""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def launch(mode, filename='', project_root=PROJECT_ROOT):
    if not filename:
        filename = input(f'Enter the {mode.upper()} file path (or drag it here), then press Enter: ')
    # Explorer's Copy as path and dragging into a console may include quotes.
    filename = filename.strip().strip('"')
    if not filename:
        print('No file selected.')
        return 2
    source = Path(filename).expanduser().resolve()
    allowed = {'.html', '.htm'} if mode == 'html' else {'.xlsx'}
    if not source.is_file() or source.suffix.lower() not in allowed:
        print(f'Please select an existing {mode.upper()} file.')
        return 2
    report_path = None
    try:
        reports = project_root / 'reports'
        reports.mkdir(exist_ok=True)
        # A fresh filename avoids overwriting a previous run or the input file.
        with tempfile.NamedTemporaryFile(prefix=f'{mode}-report-', suffix='.json', dir=reports, delete=False) as report:
            report_path = Path(report.name)
        script = 'check_w2.py' if mode == 'html' else 'check_w2_xlsx.py'
        result = subprocess.run([sys.executable, str(project_root / script), str(source), '--json', str(report_path)],
                                cwd=project_root, check=False)
        if result.returncode in (0, 1) and report_path.stat().st_size:
            print(f'\nReport saved to: {report_path}')
        else:
            report_path.unlink(missing_ok=True)
            print('\nThe checker could not complete. Run install.bat if dependencies are missing.')
        return result.returncode
    except OSError:
        if report_path is not None:
            report_path.unlink(missing_ok=True)
        print('Unable to launch the checker or save its report. Check folder permissions and rerun install.bat.')
        return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('html', 'xlsx'))
    parser.add_argument('file', nargs='?', default='')
    args = parser.parse_args()
    try:
        return launch(args.mode, args.file)
    except (EOFError, KeyboardInterrupt):
        print('\nCancelled.')
        return 2


if __name__ == '__main__':
    sys.exit(main())
