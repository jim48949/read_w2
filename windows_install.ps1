# Installs into this project folder, without administrator privileges.
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

function Find-Python {
    $candidates = @(
        @{ Command = 'py'; Prefix = @('-3') },
        @{ Command = 'python'; Prefix = @() },
        @{ Command = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'); Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) { continue }
        $prefix = $candidate.Prefix
        try {
            & $candidate.Command @prefix -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { continue }
    }
    return $null
}

try {
    Set-Location -LiteralPath $projectRoot
    if (Test-Path -LiteralPath $venvPython) {
        & $venvPython -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
        if ($LASTEXITCODE -ne 0) { throw 'Existing .venv is unusable. Rename it, then run install.bat again.' }
    } else {
        $python = Find-Python
        if (-not $python) {
            if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
                throw 'Python 3.10+ is required. Install it from https://www.python.org/downloads/windows/ with the Python launcher, then rerun install.bat.'
            }
            Write-Host 'Installing Python 3.12 for the current Windows user with WinGet...'
            & winget install --exact --id Python.Python.3.12 --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { throw 'Python installation failed. Install Python 3.10+ from python.org, then rerun install.bat.' }
            $python = Find-Python
            if (-not $python) { throw 'Python was installed but is not available yet. Reopen this folder and rerun install.bat.' }
        }
        $prefix = $python.Prefix
        Write-Host 'Creating the project virtual environment...'
        & $python.Command @prefix -m venv (Join-Path $projectRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Extract the project to a writable folder and retry.' }
    }
    Write-Host 'Installing HTML and Excel dependencies...'
    & $venvPython -m pip install -r (Join-Path $projectRoot 'requirements-xlsx.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check Internet access and rerun install.bat.' }
    & $venvPython -c 'import bs4, openpyxl; import check_w2, check_w2_xlsx'
    if ($LASTEXITCODE -ne 0) { throw 'Installed checker could not be imported.' }
    Write-Host 'Installation complete. Use launch_html.bat or launch_xlsx.bat.'
    exit 0
} catch {
    Write-Host ('INSTALLATION FAILED: ' + $_.Exception.Message)
    exit 2
}
