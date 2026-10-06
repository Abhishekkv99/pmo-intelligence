<#
.SYNOPSIS
    Registers the PMO Intelligence Graph app in Entra ID with the Azure CLI.

.DESCRIPTION
    Run after New-GraphCertificate.ps1, signed in with `az login` as yourself (no admin role needed
    when the tenant lets users register apps). It:
      1. creates a single-tenant app registration and its service principal
      2. uploads the certificate's public key (.cer) as the credential
      3. adds the Graph application permission Chat.Read.All as the fallback route; this stays
         "not granted" until a tenant administrator consents, which is intended
    RSC permissions (ChatMessage.Read.Chat, ChatMember.Read.Chat) are not set here: they live in the
    Teams app manifest (teams-app/).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\teams\Register-GraphApp.ps1
#>
param(
    [string]$DisplayName = "PMO Intelligence Graph",
    [string]$CertPath = (Join-Path $env:USERPROFILE "pmo-intelligence-secrets\pmo-intelligence-graph.cer"),
    [bool]$AddFallbackPermission = $true
)

$ErrorActionPreference = "Stop"

$GraphAppId = "00000003-0000-0000-c000-000000000000"   # Microsoft Graph
$ChatReadAllRoleId = "6b7d71aa-70aa-4810-a8d9-5d9fb2830017"   # Chat.Read.All (application)

function Invoke-Az {
    param([string[]]$AzArgs)
    $out = & az @AzArgs
    if ($LASTEXITCODE -ne 0) { throw "az $($AzArgs -join ' ') failed (exit $LASTEXITCODE)" }
    return $out
}

if (-not (Test-Path $CertPath)) { throw "Certificate not found at $CertPath. Run New-GraphCertificate.ps1 first." }

$tenantId = Invoke-Az @("account", "show", "--query", "tenantId", "-o", "tsv")
$signedInAs = Invoke-Az @("account", "show", "--query", "user.name", "-o", "tsv")
Write-Host "Signed in as $signedInAs (tenant $tenantId)"

$existing = Invoke-Az @("ad", "app", "list", "--display-name", $DisplayName, "--query", "[].appId", "-o", "tsv")
if ($existing) { throw "An app registration named '$DisplayName' already exists (appId $existing). Not creating another." }

Write-Host "Creating app registration '$DisplayName'..."
$appId = Invoke-Az @("ad", "app", "create", "--display-name", $DisplayName, "--sign-in-audience", "AzureADMyOrg", "--query", "appId", "-o", "tsv")

Write-Host "Creating service principal..."
Invoke-Az @("ad", "sp", "create", "--id", $appId, "--query", "id", "-o", "tsv") | Out-Null

Write-Host "Uploading certificate public key..."
Invoke-Az @("ad", "app", "credential", "reset", "--id", $appId, "--cert", "@$CertPath", "--append", "--query", "appId", "-o", "tsv") | Out-Null

if ($AddFallbackPermission) {
    Write-Host "Adding fallback permission Chat.Read.All (requires admin consent; left ungranted)..."
    Invoke-Az @("ad", "app", "permission", "add", "--id", $appId, "--api", $GraphAppId, "--api-permissions", "$ChatReadAllRoleId=Role") | Out-Null
}

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertPath)

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Tenant ID:              $tenantId"
Write-Host "  Graph app (client) ID:  $appId"
Write-Host "  Certificate thumbprint: $($cert.Thumbprint)"
Write-Host "  Certificate expiry:     $($cert.NotAfter.ToString('yyyy-MM-dd'))"
Write-Host ""
Write-Host "Next: build the Teams app package with this app ID:" -ForegroundColor Yellow
Write-Host "  uv run python teams-app\build_package.py --app-id $appId"
