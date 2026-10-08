<#
.SYNOPSIS
    Creates or updates the PMO Intelligence SSO app in Entra ID and writes its credentials into an
    environment's app secret in AWS Secrets Manager.

.DESCRIPTION
    Run signed in with `az login` as yourself (the tenant lets users register apps) and with a valid
    `aws sso login --profile pmo-intelligence`. Safe to re-run. It:
      1. creates the single-tenant app registration (or finds the existing one by exact name)
      2. adds the Web redirect URIs (keeps any already there) and the delegated OpenID scopes
         openid, email, profile and offline_access
      3. creates the service principal, makes you an owner of it, and sets "assignment required"
         from -RequireAssignment (off by default)
      4. assigns the users in -AssignUsers (default access); this only limits sign-in when
         assignment is required
      5. creates a client secret named after the environment and writes AZURE_CLIENT_ID,
         AZURE_CLIENT_SECRET and AZURE_TENANT_ID into pmo-intelligence/<env>/app, keeping every
         other key. The secret value is never printed
    Redirect URIs are Web, not SPA: the browser does PKCE, but the backend redeems the code with the
    client secret, and Entra refuses a server-side redemption for an SPA redirect.

    Assignment required stays off unless -RequireAssignment is given. When it is on, Entra demands
    admin consent for the app even though the tenant lets users consent to the OpenID scopes, so
    nobody can sign in until a tenant administrator grants it (Enterprise apps > the app >
    Permissions > Grant admin consent). With it off, any account in the tenant can sign in but has
    no role, and sees nothing, until a PMO manager gives it one.

    An environment that already has a secret is left alone unless -RotateSecret is given. A rotation
    keeps the old secret, so running tasks still sign in; delete it (the key id is printed) after the
    backend has been redeployed.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\entra\Register-SsoApp.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\entra\Register-SsoApp.ps1 -Environment prod `
        -RedirectUris https://pmo-intelligence.itcapp.ai/auth/callback/microsoft
#>
param(
    [string]$DisplayName = "PMO Intelligence",
    [string]$Environment = "staging",
    [string[]]$RedirectUris = @(
        "http://localhost:3000/auth/callback/microsoft",
        "http://localhost:3100/auth/callback/microsoft",
        "https://pmo-intelligence-staging.itcapp.ai/auth/callback/microsoft"
    ),
    [switch]$RequireAssignment,
    [string[]]$AssignUsers = @(),
    [int]$SecretMonths = 12,
    [switch]$RotateSecret,
    [string]$AwsProfile = "pmo-intelligence",
    [string]$AwsRegion = "eu-west-2"
)

$ErrorActionPreference = "Stop"

$GraphAppId = "00000003-0000-0000-c000-000000000000"   # Microsoft Graph
$GraphApi = "https://graph.microsoft.com/v1.0"
$DefaultAccessRoleId = "00000000-0000-0000-0000-000000000000"   # assignment without an app role
$OidcScopes = @("openid", "email", "profile", "offline_access")
$SecretId = "pmo-intelligence/$Environment/app"

function Invoke-Az {
    param([string[]]$AzArgs)
    $out = & az @AzArgs
    if ($LASTEXITCODE -ne 0) { throw "az $($AzArgs[0..2] -join ' ') failed (exit $LASTEXITCODE)" }
    return $out
}

function Invoke-Aws {
    param([string[]]$AwsArgs)
    $out = & aws @AwsArgs --profile $AwsProfile --region $AwsRegion
    if ($LASTEXITCODE -ne 0) { throw "aws $($AwsArgs[0..1] -join ' ') failed (exit $LASTEXITCODE)" }
    return $out
}

function Write-TempJson {
    param($Value)
    # UTF-8 without a BOM: az and aws read the file as JSON
    $path = [IO.Path]::GetTempFileName()
    # -InputObject keeps a one-item array an array; piping would unwrap it
    [IO.File]::WriteAllText($path, (ConvertTo-Json -InputObject $Value -Depth 10 -Compress), (New-Object Text.UTF8Encoding $false))
    return $path
}

function Invoke-GraphPost {
    param([string]$Uri, $Body)
    $file = Write-TempJson $Body
    try { Invoke-Az @("rest", "--method", "POST", "--uri", $Uri, "--body", "@$file", "--headers", "Content-Type=application/json") | Out-Null }
    finally { Remove-Item $file -Force }
}

$tenantId = Invoke-Az @("account", "show", "--query", "tenantId", "-o", "tsv")
$signedInAs = Invoke-Az @("account", "show", "--query", "user.name", "-o", "tsv")
$myObjectId = Invoke-Az @("ad", "signed-in-user", "show", "--query", "id", "-o", "tsv")
Write-Host "Signed in as $signedInAs (tenant $tenantId)"
$awsAccount = Invoke-Aws @("sts", "get-caller-identity", "--query", "Account", "--output", "text")
if ($awsAccount -ne "260172548683") { throw "AWS profile $AwsProfile is in account $awsAccount, expected 260172548683." }

# 1. App registration (az ad app list matches names by prefix, so filter for the exact name)
$apps = @(Invoke-Az @("ad", "app", "list", "--display-name", $DisplayName, "-o", "json") | Out-String | ConvertFrom-Json |
    Where-Object { $_.displayName -eq $DisplayName })
if ($apps.Count -gt 1) { throw "More than one app registration is named '$DisplayName'. Resolve that first." }
if ($apps.Count -eq 1) {
    $app = $apps[0]
    if ($app.signInAudience -ne "AzureADMyOrg") { throw "'$DisplayName' exists but is not single tenant ($($app.signInAudience))." }
    Write-Host "Found app registration '$DisplayName' ($($app.appId))"
} else {
    Write-Host "Creating single-tenant app registration '$DisplayName'..."
    $app = Invoke-Az @("ad", "app", "create", "--display-name", $DisplayName, "--sign-in-audience", "AzureADMyOrg", "-o", "json") | Out-String | ConvertFrom-Json
}
$appId = $app.appId

# 2. Redirect URIs (union with what is there) and the OpenID scopes
$uris = @(@($app.web.redirectUris) + $RedirectUris | Where-Object { $_ } | Sort-Object -Unique)
Write-Host "Setting Web redirect URIs: $($uris -join ', ')"
Invoke-Az (@("ad", "app", "update", "--id", $appId, "--web-redirect-uris") + $uris) | Out-Null

$graphScopes = Invoke-Az @("ad", "sp", "show", "--id", $GraphAppId, "--query", "oauth2PermissionScopes", "-o", "json") | Out-String | ConvertFrom-Json
$access = @(foreach ($name in $OidcScopes) {
    $scope = $graphScopes | Where-Object { $_.value -eq $name }
    if (-not $scope) { throw "Graph scope $name not found in the tenant." }
    @{ id = $scope.id; type = "Scope" }
})
$file = Write-TempJson @(@{ resourceAppId = $GraphAppId; resourceAccess = $access })
try { Invoke-Az @("ad", "app", "update", "--id", $appId, "--required-resource-accesses", "@$file") | Out-Null }
finally { Remove-Item $file -Force }

# 3. Service principal, its owner, assignment required (needs admin consent when on)
$spId = Invoke-Az @("ad", "sp", "list", "--filter", "appId eq '$appId'", "--query", "[0].id", "-o", "tsv")
if (-not $spId) {
    Write-Host "Creating service principal..."
    $spId = Invoke-Az @("ad", "sp", "create", "--id", $appId, "--query", "id", "-o", "tsv")
}
$owners = @(Invoke-Az @("rest", "--method", "GET", "--uri", "$GraphApi/servicePrincipals/$spId/owners?`$select=id", "--query", "value[].id", "-o", "tsv"))
if ($owners -notcontains $myObjectId) {
    Write-Host "Adding $signedInAs as an owner of the service principal..."
    Invoke-GraphPost "$GraphApi/servicePrincipals/$spId/owners/`$ref" @{ "@odata.id" = "$GraphApi/directoryObjects/$myObjectId" }
}
$required = if ($RequireAssignment) { "true" } else { "false" }
Write-Host "Setting assignment required to $required..."
if ($RequireAssignment) { Write-Warning "Users cannot sign in until a tenant administrator grants admin consent to '$DisplayName'." }
Invoke-Az @("ad", "sp", "update", "--id", $spId, "--set", "appRoleAssignmentRequired=$required") | Out-Null

# 4. User assignments
$assigned = @(Invoke-Az @("rest", "--method", "GET", "--uri", "$GraphApi/servicePrincipals/$spId/appRoleAssignedTo", "--query", "value[].principalId", "-o", "tsv"))
foreach ($user in $AssignUsers) {
    $userId = Invoke-Az @("ad", "user", "show", "--id", $user, "--query", "id", "-o", "tsv")
    if ($assigned -contains $userId) { Write-Host "Already assigned: $user"; continue }
    Write-Host "Assigning $user..."
    Invoke-GraphPost "$GraphApi/servicePrincipals/$spId/appRoleAssignedTo" @{ principalId = $userId; resourceId = $spId; appRoleId = $DefaultAccessRoleId }
}

# 5. Client secret for this environment, straight into Secrets Manager
$existing = @((Invoke-Az @("ad", "app", "show", "--id", $appId, "--query", "passwordCredentials", "-o", "json") | Out-String | ConvertFrom-Json) |
    Where-Object { $_.displayName -eq $Environment })
$secretExpiry = $null
if ($existing.Count -gt 0 -and -not $RotateSecret) {
    Write-Host "A '$Environment' secret already exists (expires $(([datetime]$existing[0].endDateTime).ToString('yyyy-MM-dd'))); not creating another. Use -RotateSecret to replace it."
} else {
    $secretExpiry = (Get-Date).AddMonths($SecretMonths).ToString("yyyy-MM-dd")
    Write-Host "Creating the '$Environment' client secret (expires $secretExpiry)..."
    $secretValue = Invoke-Az @("ad", "app", "credential", "reset", "--id", $appId, "--append", "--display-name", $Environment, "--end-date", $secretExpiry, "--query", "password", "-o", "tsv")

    Write-Host "Writing AZURE_CLIENT_ID, AZURE_CLIENT_SECRET and AZURE_TENANT_ID into $SecretId..."
    $appSecret = Invoke-Aws @("secretsmanager", "get-secret-value", "--secret-id", $SecretId, "--query", "SecretString", "--output", "text") | Out-String | ConvertFrom-Json
    foreach ($pair in @(@("AZURE_CLIENT_ID", $appId), @("AZURE_CLIENT_SECRET", $secretValue), @("AZURE_TENANT_ID", $tenantId))) {
        $appSecret | Add-Member -NotePropertyName $pair[0] -NotePropertyValue $pair[1] -Force
    }
    $file = Write-TempJson $appSecret
    try { Invoke-Aws @("secretsmanager", "put-secret-value", "--secret-id", $SecretId, "--secret-string", "file://$file") | Out-Null }
    finally { Remove-Item $file -Force; $secretValue = $null; $appSecret = $null }
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Tenant ID:            $tenantId"
Write-Host "  SSO app (client) ID:  $appId"
Write-Host "  Service principal:    $spId (assignment required: $required)"
Write-Host "  Redirect URIs:        $($uris -join ', ')"
if ($secretExpiry) {
    Write-Host "  '$Environment' secret expires: $secretExpiry (value written to $SecretId, not shown)"
    Write-Host ""
    Write-Host "Next:" -ForegroundColor Yellow
    Write-Host "  1. Add entra-sso-client-secret-$Environment = `"$secretExpiry`" to credential_expiries in infra/shared/variables.tf, then plan and apply"
    Write-Host "  2. Redeploy the backend so it reads the new values"
    foreach ($old in $existing) {
        Write-Host "  3. After the redeploy, delete the old secret: az ad app credential delete --id $appId --key-id $($old.keyId)"
    }
}
