# Pravi prenosni paket za novi racunar: Magacin_prenos.zip
# Sadrzi: git fajlove + .env + pg_bin + poslednjih 10 backupova + instalaciju.
# Samo ASCII (PowerShell 5.1).
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$ime = 'Magacin_prenos'
$paket = Join-Path $root $ime

Write-Host 'Pravim prenosni paket...'

# 1) Cist folder + git trackovani fajlovi (bez .venv, .git, backups...)
if (Test-Path $paket) { Remove-Item $paket -Recurse -Force }
New-Item -ItemType Directory -Path $paket | Out-Null
git -C $root archive --format=tar HEAD | tar -x -C $paket
if ($LASTEXITCODE -ne 0) { throw 'git archive nije uspeo' }

# 2) .env (nije u git-u, MORA se preneti rucno)
Copy-Item (Join-Path $root '.env') $paket -Force

# 3) pg_dump alati (backup radi bez instaliranog PostgreSQL-a)
Copy-Item (Join-Path $root 'pg_bin') (Join-Path $paket 'pg_bin') -Recurse -Force

# 4) Poslednjih 10 automatskih backupova (rucni USB/preview backupi NE idu)
$bakSrc = Join-Path $root 'backups'
$bakDst = Join-Path $paket 'backups'
New-Item -ItemType Directory -Path $bakDst -Force | Out-Null
$dumps = Get-ChildItem -Path (Join-Path $bakSrc 'central_????????T??????Z.dump') -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 10
foreach ($d in $dumps) {
    Copy-Item $d.FullName $bakDst -Force
    $sha = $d.FullName + '.sha256'
    if (Test-Path $sha) { Copy-Item $sha $bakDst -Force }
}
Write-Host ('Backup-a u paketu: ' + $dumps.Count)

# 5) Zip
$zip = Join-Path $root ($ime + '.zip')
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $paket '*') -DestinationPath $zip -CompressionLevel Optimal

$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host ''
Write-Host ('PAKET NAPRAVLJEN: ' + $zip + ' (' + $mb + ' MB)')
Write-Host ('Sadrzaj: ' + (Get-ChildItem $paket | Measure-Object).Count + ' stavki u folderu ' + $ime)
