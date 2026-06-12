$ErrorActionPreference = "Stop"

$source = "C:\Sade"
$backupRoot = "C:\Sade\Backups"
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$stage = Join-Path $env:TEMP "SadeBackup_$timestamp"
$zip = Join-Path $backupRoot "Sade_backup_$timestamp.zip"
$logFile = Join-Path $backupRoot "backup_log.md"

Write-Host "Säde v1 backup alkaa..." -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
New-Item -ItemType Directory -Force -Path $stage | Out-Null

$excludeDirs = @(
    "Backups",
    ".git",
    ".venv",
    "__pycache__",
    "logs"
)

$excludeFiles = @(
    "*.pyc",
    "*.log",
    "*.tmp"
)

Write-Host "Kopioidaan tiedostot väliaikaiseen kansioon..." -ForegroundColor Yellow

robocopy $source $stage /MIR /XD $excludeDirs /XF $excludeFiles | Out-Null

if ($LASTEXITCODE -gt 7) {
    throw "Robocopy epäonnistui. Exit code: $LASTEXITCODE"
}

Write-Host "Pakataan zip-tiedostoksi..." -ForegroundColor Yellow

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force

Remove-Item $stage -Recurse -Force

$sizeMb = [math]::Round((Get-Item $zip).Length / 1MB, 2)

$logEntry = "- $timestamp : $zip ($sizeMb MB)"
Add-Content -Path $logFile -Value $logEntry -Encoding UTF8

Write-Host ""
Write-Host "Backup valmis." -ForegroundColor Green
Write-Host "Tiedosto: $zip"
Write-Host "Koko: $sizeMb MB"
Write-Host ""