param([switch]$NoBuild)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$vaultDockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$vaultDocker = if ($vaultDockerCommand) { $vaultDockerCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe' }
if (-not (Test-Path -LiteralPath $vaultDocker)) { throw 'Khong tim thay docker.exe. Hay cai Docker Desktop va mo Docker Engine.' }
& $vaultDocker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Engine chua san sang. Hay mo Docker Desktop va cho Engine running.' }
$vaultEnvPath = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $vaultEnvPath)) {
    function New-VaultSecret {
        $vaultBytes = New-Object byte[] 24
        $vaultRng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $vaultRng.GetBytes($vaultBytes) } finally { $vaultRng.Dispose() }
        return [Convert]::ToBase64String($vaultBytes).TrimEnd('=').Replace('+','-').Replace('/','_')
    }
    $vaultNames = @('MINIO_ROOT_USER','MINIO_ROOT_PASSWORD','S3_ACCESS_KEY','S3_SECRET_KEY','DEMO_PASSWORD_HIEU','DEMO_PASSWORD_MINH')
    $vaultLines = @('# Local-only lab secrets. Keep this file private.')
    foreach ($vaultName in $vaultNames) { $vaultLines += ($vaultName + '=' + (New-VaultSecret)) }
    [IO.File]::WriteAllLines($vaultEnvPath, $vaultLines, (New-Object Text.UTF8Encoding($false)))
    Write-Host 'Da tao .env moi. Giu tep nay rieng tu va khong dua vao ZIP.'
}
if ($NoBuild) { & $vaultDocker compose up -d --no-build } else { & $vaultDocker compose up --build -d }
if ($LASTEXITCODE -ne 0) { throw 'Khoi dong that bai. Xem docker compose logs bootstrap app minio.' }
$vaultReady = $false
for ($vaultAttempt=0; $vaultAttempt -lt 40; $vaultAttempt++) {
    try { $vaultHealth = Invoke-RestMethod 'http://localhost:8000/api/health' -TimeoutSec 3; if ($vaultHealth.status -eq 'ok') { $vaultReady=$true; break } } catch { }
    Start-Sleep -Seconds 2
}
if (-not $vaultReady) { throw 'Ung dung chua san sang. Xem docker compose logs app bootstrap minio.' }
$vaultValues = @{}
Get-Content -LiteralPath $vaultEnvPath | ForEach-Object { if ($_ -match '^([^#=]+)=(.*)$') { $vaultValues[$Matches[1]]=$Matches[2] } }
Write-Host ''
Write-Host 'N11 Vault da san sang: http://localhost:8000' -ForegroundColor Green
Write-Host ('Tai khoan hieu / mat khau: ' + $vaultValues['DEMO_PASSWORD_HIEU'])
Write-Host ('Tai khoan minh / mat khau: ' + $vaultValues['DEMO_PASSWORD_MINH'])
Write-Host 'Dung dich vu va giu du lieu: docker compose stop'
