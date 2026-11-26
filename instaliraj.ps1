# Instalacija magacina na novom racunaru. Samo ASCII znakovi (PowerShell 5.1)!
# Pokreni preko: Instaliraj.bat
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$greske = 0

function Korak([string]$t) { Write-Host ''; Write-Host ('=== ' + $t + ' ===') -ForegroundColor Cyan }
function OK([string]$t) { Write-Host ('[OK] ' + $t) -ForegroundColor Green }
function Fail([string]$t) { Write-Host ('[PROBLEM] ' + $t) -ForegroundColor Red; $script:greske++ }

Write-Host '==================================================='
Write-Host '  INSTALACIJA MAGACINA'
Write-Host ('  Folder: ' + $root)
Write-Host '==================================================='

# --- 1) .env (sadrzi adresu baze i internet adresu) -------------------------
Korak '1/7 Provera podešavanja (.env)'
$envFajl = Join-Path $root '.env'
if (-not (Test-Path $envFajl)) {
    Fail 'Nedostaje .env fajl. Prebacite CELU prenosnu fasciklu (ne samo ovaj fajl).'
} else {
    $linije = Get-Content $envFajl -ErrorAction SilentlyContinue
    $imaBaza = [bool]($linije | Where-Object { $_ -match '^DATABASE_URL\s*=' })
    $imaWeb = [bool]($linije | Where-Object { $_ -match '^MAGACIN_WEB_URL\s*=' })
    if ($imaBaza) { OK 'DATABASE_URL postoji' } else { Fail '.env nema DATABASE_URL' }
    if ($imaWeb) { OK 'MAGACIN_WEB_URL postoji' } else { Fail '.env nema MAGACIN_WEB_URL' }
}

# --- 2) Python ---------------------------------------------------------------
Korak '2/7 Pronalazenje Python-a (3.13 ili noviji)'
$py = $null

# py launcher: prvo 3.13, pa bilo koja 3.13+/3.14+
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    foreach ($ver in @('-3.13', '-3.14', '')) {
        $exe = & py $ver -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) {
            $pyVer = & $exe -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null
            if ($pyVer -and $pyVer -ge '3.13') { $py = "$exe".Trim(); break }
        }
    }
}
# python sa PATH-a
if (-not $py) {
    foreach ($ime in @('python3', 'python')) {
        $c = Get-Command $ime -ErrorAction SilentlyContinue
        if ($c) {
            $pyVer = & $c.Source -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null
            if ($pyVer -and $pyVer -ge '3.13') { $py = $c.Source; break }
        }
    }
}
# standardne lokacije
if (-not $py) {
    $kandidati = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe')
    )
    foreach ($k in $kandidati) { if (Test-Path $k) { $py = $k; break } }
}

if ($py) {
    $v = & $py -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>$null
    OK ('Python ' + $v + ' -> ' + $py)
} else {
    Write-Host '[...] Python nije nadjen. Pokusavam instalaciju preko winget-a...'
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        & winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements --silent
        Start-Sleep -Seconds 3
        foreach ($k in @(
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe')
        )) {
            if (Test-Path $k) {
                if ($k -like '*py.exe') {
                    $exe = & $k -3.13 -c 'import sys; print(sys.executable)' 2>$null
                    if ($exe) { $py = "$exe".Trim() }
                } else { $py = $k }
                break
            }
        }
        if ($py) { OK ('Python instaliran: ' + $py) }
        else { Fail 'Winget instalacija nije uspela. Instalirajte Python 3.13 rucno: https://www.python.org/downloads/ pa pokrenite Instaliraj.bat ponovo.' }
    } else {
        Fail 'Nema winget-a. Instalirajte Python 3.13 rucno: https://www.python.org/downloads/ pa pokrenite Instaliraj.bat ponovo.'
    }
}

# --- 3) venv + paketi -------------------------------------------------------
Korak '3/7 Kreiranje virtualnog okruzenja i instalacija paketa'
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
if (-not $py) {
    Fail 'Nema Python-a, preskacem pakete.'
} else {
    if (-not (Test-Path $venvPy)) {
        & $py -m venv (Join-Path $root '.venv')
        if (Test-Path $venvPy) { OK '.venv kreiran' } else { Fail '.venv NIJE kreiran' }
    } else {
        OK '.venv vec postoji (preskacem kreiranje)'
    }
    if (Test-Path $venvPy) {
        $lock = Join-Path $root 'requirements.lock.txt'
        if (Test-Path $lock) {
            Write-Host '[...] Instalacija paketa (moze potrajati par minuta)...'
            & $venvPy -m pip install --no-warn-script-location --disable-pip-version-check -q -r $lock
            if ($LASTEXITCODE -eq 0) { OK 'Svi paketi instalirani' }
            else { Fail 'Instalacija paketa nije uspela (proverite internet vezu).' }
        } else {
            Fail 'Nedostaje requirements.lock.txt'
        }
    }
}

# --- 4) pg_dump (za backup baze) -------------------------------------------
Korak '4/7 Provera alata za backup (pg_bin)'
$pgDump = Join-Path $root 'pg_bin\pg_dump.exe'
if (Test-Path $pgDump) {
    $pv = & $pgDump --version 2>$null
    OK ($pv)
} else {
    Fail 'Nedostaje pg_bin\pg_dump.exe - backup baze nece raditi.'
}

# --- 5) Prvi backup ---------------------------------------------------------
Korak '5/7 Prvi backup baze na ovaj racunar'
if ((Test-Path $venvPy) -and (Test-Path (Join-Path $root 'backup_database.py'))) {
    & $venvPy (Join-Path $root 'backup_database.py') --keep 10
    if ($LASTEXITCODE -eq 0) { OK 'Backup napravljen (folder backups, cuva poslednjih 10)' }
    else { Fail 'Backup nije uspeo - proverite .env i internet vezu.' }
} else {
    Fail 'Preskacem backup (nedostaje venv ili backup_database.py).'
}

# --- 6) Desktop prečica -----------------------------------------------------
Korak '6/7 Prečica na Desktopu'
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'Magacin.lnk'
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$launch = Join-Path $root 'launch_web.py'
$ikona = Join-Path $root 'ikona.ico'
if ((Test-Path $pythonw) -and (Test-Path $launch)) {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($lnkPath)
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = '"' + $launch + '"'
    $lnk.WorkingDirectory = $root
    if (Test-Path $ikona) { $lnk.IconLocation = $ikona + ',0' }
    $lnk.Description = 'Pokreni Magacin (backup + internet adresa)'
    $lnk.WindowStyle = 7
    $lnk.Save()
    if (Test-Path $lnkPath) { OK ('Prečica: ' + $lnkPath) }
    else { Fail 'Prečica nije napravljena.' }
} else {
    Fail 'Preskacem prečicu (nedostaje pythonw.exe ili launch_web.py).'
}

# --- 7) Dnevna provera (zakazani zadatak) -----------------------------------
Korak '7/7 Dnevna provera u 09:00'
$provera = Join-Path $root 'provera.ps1'
if (Test-Path $provera) {
    try {
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
            -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + $provera + '"')
        $trigger = New-ScheduledTaskTrigger -Daily -At '09:00'
        Register-ScheduledTask -TaskName 'Magacin provera' -Action $action -Trigger $trigger `
            -Description 'Dnevna provera baze, stranice i backup-a magacina' -Force | Out-Null
        OK 'Zakazani zadatak "Magacin provera" registrovan (svakog dana u 09:00)'
    } catch {
        Fail ('Zakazani zadatak nije mogao da se napravi: ' + $_.Exception.Message)
    }
} else {
    Fail 'Nedostaje provera.ps1'
}

# --- Završna provera --------------------------------------------------------
Korak 'Zavrsna provera sistema'
if (Test-Path $provera) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $provera
    if ($LASTEXITCODE -eq 0) { OK 'Provera sistema: SVE OK' }
    else { Fail 'Provera sistema ima problema (vidi iznad).' }
}

Write-Host ''
Write-Host '==================================================='
if ($greske -eq 0) {
    Write-Host '  INSTALACIJA ZAVRSENA - SVE OK' -ForegroundColor Green
    Write-Host ''
    Write-Host '  Pokretanje: dvaput klik na ikonicu Magacin (Desktop)'
    Write-Host '  Ili direktno u browseru adresa iz .env fajla.'
} else {
    Write-Host ('  INSTALACIJA ZAVRSENA SA ' + $greske + ' PROBLEM(A)') -ForegroundColor Red
    Write-Host '  Procitajte poruke iznad i pokrenite Instaliraj.bat ponovo.'
}
Write-Host '==================================================='
exit $greske
