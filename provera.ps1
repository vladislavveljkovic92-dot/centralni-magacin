# Provera stanja sistema magacin (Ekavica, bez strucnog znanja).
# Rezultat se upisuje u logovi\provera.log i prikazuje na ekranu.
# Ne upisuje lozinke ni URL baze - samo status i brojeve zapisa.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$root = $PSScriptRoot
$logDir = Join-Path $root 'logovi'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir 'provera.log'

$lines = @('=== Provera stanja: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ===')
$imaProblema = $false
$imaUpozorenje = $false

function Zapis([string]$status, [string]$poruka) {
    $global:lines += ('[' + $status + '] ' + $poruka)
    if ($status -eq 'PROBLEM') { $global:imaProblema = $true }
    if ($status -eq 'UPOZORENJE') { $global:imaUpozorenje = $true }
    Write-Host ('[' + $status + '] ' + $poruka)
}

# --- 1) Baza podataka -------------------------------------------------------
$py = Join-Path $root '.venv\Scripts\python.exe'
$manage = Join-Path $root 'manage.py'
if (-not (Test-Path $py)) {
    Zapis 'PROBLEM' 'Nedostaje .venv folder (Python okruzenje). Aplikacija se lokalno ne moze pokrenuti.'
} elseif (-not (Test-Path $manage)) {
    Zapis 'PROBLEM' 'Nedostaje manage.py - nepotpuna instalacija programa.'
} else {
    $out = (& $py -X utf8 $manage check 2>&1 | Out-String)
    $json = $null
    try { $json = $out | ConvertFrom-Json } catch {}
    if ($LASTEXITCODE -eq 0 -and $json) {
        $c = $json.counts
        Zapis 'OK' ('Baza radi. Verzija seme: ' + $json.revision +
            ' | delova: ' + $c.inventory_parts + ' | pokreta: ' + $c.stock_movements +
            ' | naloga: ' + $c.work_orders + ' | korisnika: ' + $c.app_users)
    } else {
        $detalj = ($out -replace '\s+', ' ').Trim()
        if ($detalj.Length -gt 300) { $detalj = $detalj.Substring(0, 300) + '...' }
        Zapis 'PROBLEM' ('Baza ne odgovara. Detalj: ' + $detalj)
    }
}

# --- 2) Web stranica (gde korisnici otvaraju magacin) ------------------------
$web = 'https://vladislavveljkovic92-dot-centralni-magacin-streamlit-app-a82wgy.streamlit.app'
$htmlDostupna = $false
try {
    $resp = Invoke-WebRequest -Uri ($web + '/') -UseBasicParsing -TimeoutSec 30
    if ($resp.StatusCode -eq 200) {
        Zapis 'OK' 'Web stranica je dostupna (otvara se na internetu).'
        $htmlDostupna = $true
    } else {
        Zapis 'PROBLEM' ('Web stranica vraca status ' + $resp.StatusCode + '.')
    }
} catch {
    Zapis 'PROBLEM' ('Web stranica ne odgovara: ' + $_.Exception.Message)
}

# --- 3) JavaScript fajlovi (poznati hosting bag - polja ne reaguju) ----------
if ($htmlDostupna) {
    try {
        $stranica = Invoke-WebRequest -Uri ($web + '/~/+/') -UseBasicParsing -TimeoutSec 30
        $putanje = [regex]::Matches($stranica.Content, '(?:src|href)="(\./static/js/[^"]+\.js)"') |
            ForEach-Object { $_.Groups[1].Value } | Select-Object -First 6
        if (-not $putanje) {
            Zapis 'UPOZORENJE' 'Nije moguce naci JS fajlove za proveru (izmenjen izgled stranice).'
        } else {
            $greske = @()
            foreach ($p in $putanje) {
                try {
                    $r = Invoke-WebRequest -Uri ($web + '/~/+/' + $p.Substring(2)) -UseBasicParsing -TimeoutSec 20 -Method Head
                    if ($r.StatusCode -ne 200) { $greske += ($p + ' -> ' + $r.StatusCode) }
                } catch {
                    $greske += ($p + ' -> ' + $_.Exception.Response.StatusCode.value__)
                }
            }
            if ($greske.Count -eq 0) {
                Zapis 'OK' ('Programski fajlovi se ucitavaju ispravno (' + $putanje.Count + '/6).')
            } else {
                Zapis 'PROBLEM' ('Hosting ne isporucuje JS fajlove (' + $greske.Count + '/' + $putanje.Count +
                    ' losih). To je poznati problem hostinga: polja za prijavu tada ne reaguju. Resenje: osveziti stranicu. Detalj: ' +
                    ($greske -join '; '))
            }
        }
    } catch {
        Zapis 'UPOZORENJE' ('Provera JS fajlova nije uspela: ' + $_.Exception.Message)
    }
}

# --- 4) Lokalni pregled (port 8501) -----------------------------------------
$lokalan = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if ($lokalan) {
    Zapis 'OK' 'Lokalni pregled je pokrenut na portu 8501.'
} else {
    Zapis 'INFO' 'Lokalni pregled trenutno nije pokrenut (to je normalno ako ga ne koristis).'
}

# --- 5) Backup baze ---------------------------------------------------------
$dumps = Get-ChildItem -Path (Join-Path $root 'backups\*.dump') -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
if (-not $dumps) {
    Zapis 'PROBLEM' 'Nema nijednog backup fajla u folders backups. Pokreni: .venv\Scripts\python.exe backup_database.py --pg-bin "C:\Program Files\PostgreSQL\17\bin"'
} else {
    $poslednji = $dumps[0]
    $dana = [int]((Get-Date) - $poslednji.LastWriteTime).TotalDays
    if ($dana -le 7) {
        Zapis 'OK' ('Poslednji backup je ' + $poslednji.Name + ' (star ' + $dana + ' dana).')
    } else {
        Zapis 'UPOZORENJE' ('Poslednji backup je star ' + $dana + ' dana (' + $poslednji.Name + '). Preporuka: napravi novi backup.')
    }
}

# --- Zakljucak --------------------------------------------------------------
if ($imaProblema) {
    $lines += '=== NADJEN PROBLEM: posalji ovaj log (logovi\provera.log) vlasniku sistema. ==='
    Write-Host ''
    Write-Host '=== NADJEN PROBLEM: posalji ovaj log (logovi\provera.log) vlasniku sistema. ===' -ForegroundColor Red
    $izlaz = 1
} elseif ($imaUpozorenje) {
    $lines += '=== SVE RADI, ALI IMA UPOZORENJA (vidi gore). ==='
    Write-Host ''
    Write-Host '=== SVE RADI, ALI IMA UPOZORENJA. ===' -ForegroundColor Yellow
    $izlaz = 0
} else {
    $lines += '=== SVE OK: baza, stranica i backup rade ispravno. ==='
    Write-Host ''
    Write-Host '=== SVE OK: baza, stranica i backup rade ispravno. ===' -ForegroundColor Green
    $izlaz = 0
}
$lines += ''
try {
    Add-Content -Path $logFile -Value ($lines -join "`r`n") -Encoding UTF8
    Write-Host ('Upisano u: ' + $logFile)
} catch {
    Write-Host ('Nije moguce upisati log: ' + $_.Exception.Message) -ForegroundColor Yellow
}
exit $izlaz
