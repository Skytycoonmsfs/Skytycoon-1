# SkyTycoon — GitHub-Repo unter Skytycoonmsfs/Skytycoon einrichten (einmalig).
# Als Account Skytycoonmsfs bei GitHub anmelden, wenn der Browser aufgeht.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [System.Environment]::GetEnvironmentVariable("Path", "User")

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    winget install --id GitHub.cli -e --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
        [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Host "[SkyTycoon] GitHub-Login (Account: Skytycoonmsfs wählen) …" -ForegroundColor Cyan
gh auth login --hostname github.com --git-protocol https --web --skip-ssh-key -s repo,workflow,read:org

$exists = $false
try {
    gh repo view Skytycoonmsfs/Skytycoon 2>$null | Out-Null
    $exists = $true
} catch { }

if (-not $exists) {
    Write-Host "[SkyTycoon] Leeres Repo Skytycoonmsfs/Skytycoon anlegen …" -ForegroundColor Cyan
    gh repo create Skytycoonmsfs/Skytycoon --public --description "SkyTycoon Pro — Platin MSFS Airline Tycoon"
}

git remote remove origin 2>$null
git remote add origin https://github.com/Skytycoonmsfs/Skytycoon.git
git branch -M main
git push -u origin main

Write-Host "[SkyTycoon] Fertig: https://github.com/Skytycoonmsfs/Skytycoon" -ForegroundColor Green
