$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Nedostaje .venv. Pratite README za instalaciju.'
}
$pgCtl = Join-Path $PSScriptRoot '.local\pgsql\bin\pg_ctl.exe'
$pgData = Join-Path $PSScriptRoot '.local\pgdata'
if (Test-Path -LiteralPath $pgCtl) {
    & $pgCtl -D $pgData status *> $null
    if ($LASTEXITCODE -ne 0) {
        & $pgCtl -D $pgData -l (Join-Path $PSScriptRoot '.local\postgres.log') -o '-h 127.0.0.1 -p 55432' start
        if ($LASTEXITCODE -ne 0) { throw 'Testna PostgreSQL baza nije pokrenuta.' }
    }
}
Write-Host 'Lokalni pregled: http://localhost:8501'
Write-Host 'Pristupni podaci su u credentials-local.txt. Zaustavljanje: Ctrl+C.'
& $python -m streamlit run (Join-Path $PSScriptRoot 'streamlit_app.py') --server.address=127.0.0.1 --server.port=8501

