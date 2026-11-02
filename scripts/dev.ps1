[CmdletBinding()]
param(
    [switch]$Check
)

$root = Resolve-Path "$PSScriptRoot/.."
Set-Location $root

if ($Check) {
    Write-Host "Checking prerequisites..." -ForegroundColor Cyan
    if (-not (Test-Path "backend/.env")) {
        Write-Error "backend/.env is missing. Copy backend/.env.example to backend/.env."
        exit 1
    }
    if (-not (Test-Path "frontend/.env")) {
        Write-Error "frontend/.env is missing. Copy frontend/.env.example to frontend/.env."
        exit 1
    }
    Write-Host "Invoice Review is ready to start." -ForegroundColor Green
    exit 0
}

Write-Host "Starting Invoice Review Backend (:8000) and Frontend (:5173)..." -ForegroundColor Cyan

$backendJob = Start-Job -ScriptBlock {
    param($rootPath)
    Set-Location "$rootPath/backend"
    cmd.exe /c "uv run --locked --no-sync uvicorn app.main:create_app --factory --reload --port 8000 2>&1"
} -ArgumentList $root

$frontendJob = Start-Job -ScriptBlock {
    param($rootPath)
    Set-Location "$rootPath/frontend"
    cmd.exe /c "pnpm dev 2>&1"
} -ArgumentList $root

Write-Host "Services running. Press Ctrl+C to terminate both servers." -ForegroundColor Green

try {
    while ($true) {
        $bOut = Receive-Job -Job $backendJob -ErrorAction SilentlyContinue
        if ($bOut) {
            foreach ($line in $bOut) {
                Write-Host "[backend]  $line"
            }
        }
        $fOut = Receive-Job -Job $frontendJob -ErrorAction SilentlyContinue
        if ($fOut) {
            foreach ($line in $fOut) {
                Write-Host "[frontend] $line"
            }
        }
        if ($backendJob.State -ne "Running" -and $frontendJob.State -ne "Running") {
            break
        }
        Start-Sleep -Milliseconds 250
    }
} finally {
    Write-Host "`nStopping background jobs..." -ForegroundColor Yellow
    Stop-Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
}
