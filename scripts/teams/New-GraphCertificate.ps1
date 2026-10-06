<#
.SYNOPSIS
    Creates the certificate credential for the PMO Intelligence Graph app.

.DESCRIPTION
    Generates a self-signed RSA 2048 / SHA-256 certificate in the current user's store and exports:
      - <OutDir>\pmo-intelligence-graph.cer  (public key: upload this to the Entra app registration)
      - <OutDir>\pmo-intelligence-graph.pfx  (private key, password-protected: never commit, never email)
    OutDir defaults to a folder in your user profile, outside the repository.
    With -GeneratePassword, a random .pfx password is written to <OutDir>\pmo-intelligence-graph.pfx-password.txt
    instead of being prompted for; it is never printed.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\teams\New-GraphCertificate.ps1
#>
param(
    [string]$OutDir = (Join-Path $env:USERPROFILE "pmo-intelligence-secrets"),
    [int]$ValidMonths = 12,
    [switch]$GeneratePassword
)

$ErrorActionPreference = "Stop"

$cerPath = Join-Path $OutDir "pmo-intelligence-graph.cer"
$pfxPath = Join-Path $OutDir "pmo-intelligence-graph.pfx"
if ((Test-Path $cerPath) -or (Test-Path $pfxPath)) {
    throw "A certificate already exists in $OutDir. Move it aside first if you really want a new one."
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$cert = New-SelfSignedCertificate `
    -Subject "CN=PMO Intelligence Graph" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyExportPolicy Exportable `
    -KeySpec Signature `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -NotAfter (Get-Date).AddMonths($ValidMonths)

Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

if ($GeneratePassword) {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $plain = [Convert]::ToBase64String($bytes)
    $passwordFile = Join-Path $OutDir "pmo-intelligence-graph.pfx-password.txt"
    [System.IO.File]::WriteAllText($passwordFile, $plain)
    $password = ConvertTo-SecureString $plain -AsPlainText -Force
    $plain = $null
    Write-Host "Random .pfx password written to $passwordFile (not displayed)."
} else {
    $password = Read-Host -AsSecureString "Choose a password for the private key file (.pfx)"
}
Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $password | Out-Null

Write-Host ""
Write-Host "Certificate created." -ForegroundColor Green
Write-Host "  Public key (upload to Entra): $cerPath"
Write-Host "  Private key (keep secret):    $pfxPath"
Write-Host "  Thumbprint:                   $($cert.Thumbprint)"
Write-Host "  Expires:                      $($cert.NotAfter.ToString('yyyy-MM-dd'))"
Write-Host ""
Write-Host "Record the thumbprint and expiry date; an alert must fire before the expiry." -ForegroundColor Yellow
