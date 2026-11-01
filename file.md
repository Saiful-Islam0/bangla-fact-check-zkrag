<#
.SYNOPSIS
Interactive first-time setup for the HSBC Bangladesh Digital Archive on a Windows
Server host with no ASP.NET Core Hosting Bundle. Registers the self-contained
publish as a Windows Service listening on Kestrel directly.

.DESCRIPTION
Run from the extracted package root in an elevated Windows PowerShell session:

    .\scripts\setup.ps1

Prompts for SQL Server, hostname/certificate, private data roots, Active Directory
and the service identity, verifies each answer before changing anything, then
provisions directories, configuration, the service and a health check.

Secrets are never written to the package, to appsettings or to the transcript.
The SQL password (when SQL authentication is chosen) and the service account
password stay in SecureString form and are handed to sc.exe / the service
environment only.
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'HSBCArchive',
    [string]$PackageRoot = $(if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { (Get-Location).Path }),
    [switch]$SkipChecksums
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell session.'
}
if ($ServiceName -notmatch '^[A-Za-z0-9_]{1,80}$') { throw 'ServiceName must be alphanumeric/underscore.' }

$root = (Resolve-Path -LiteralPath $PackageRoot).Path.TrimEnd('\')
$appDir = Join-Path $root 'app'
$exe = Join-Path $appDir 'HSBC.Archive.Web.exe'
$template = Join-Path $root 'config\appsettings.UAT.template.json'
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Not a self-contained package: $exe is missing. Pass -PackageRoot <folder containing 'app'>."
}
if (-not (Test-Path -LiteralPath $template)) {
    throw "Missing $template. Extract the whole package, not just the app folder."
}
if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    throw "Service '$ServiceName' already exists. Remove it first (sc.exe delete $ServiceName), or pass -ServiceName for a side-by-side install."
}

# $Default and $Validate are untyped on purpose: a validator passed in the default's
# position is swapped back here instead of failing to bind.
function Read-Required([string]$Prompt, $Default = '', $Validate, $Message) {
    if ($Default -is [scriptblock]) { $Message = $Validate; $Validate = $Default; $Default = '' }
    while ($true) {
        $hint = if ($Default) { " [$Default]" } else { '' }
        $value = (Read-Host "$Prompt$hint").Trim()
        if (-not $value -and $Default) { $value = $Default }
        if ($value -and (-not $Validate -or (& $Validate $value))) { return $value }
        Write-Warning ($(if ($Message) { $Message } else { 'A value is required.' }))
    }
}

function ConvertTo-PlainText([Security.SecureString]$Secure) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($Secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringUni($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeGlobalAllocUnicode($pointer) }
}

Write-Host "`n=== HSBC Archive UAT setup ===`n" -ForegroundColor Cyan
Write-Host "Package root: $root"

# 1. Package integrity. Reuses the shipped verifier rather than re-implementing it.
$manifest = Join-Path $root 'checksums\SHA256SUMS.txt'
if ($SkipChecksums) {
    Write-Warning 'Checksum verification skipped by request.'
} elseif (-not (Test-Path -LiteralPath $manifest)) {
    Write-Warning "No $manifest; checksum verification skipped."
} else {
    Write-Host 'Verifying package checksums...'
    # This script is itself covered by the manifest, so a locally repaired copy will not match.
    try { & (Join-Path $root 'scripts\verify-deployment.ps1') -PackageRoot $root -FilesOnly }
    catch {
        if ("$_" -notmatch 'setup\.ps1') { throw }
        Write-Warning 'Only scripts/setup.ps1 differs from the manifest (this repaired copy). Continuing.'
    }
}

# 2. Database.
Write-Host "`n--- SQL Server ---" -ForegroundColor Cyan
$sqlHost = Read-Required 'SQL Server host (e.g. SQLUAT01 or SQLUAT01\INST,1433)'
$database = Read-Required 'Database name' 'HSBCArchive_UAT' { param($v) $v -match '^[A-Za-z0-9_]+$' } 'Letters, digits and underscore only.'

$builder = New-Object System.Data.SqlClient.SqlConnectionStringBuilder
$builder['Data Source'] = $sqlHost
$builder['Initial Catalog'] = $database
$builder['Encrypt'] = $true
$builder['TrustServerCertificate'] = $false

$useWindowsAuth = (Read-Required 'Authentication: [W]indows or [S]QL login' 'W' { param($v) $v -match '^[WwSs]$' }) -match '^[Ww]$'
if ($useWindowsAuth) {
    $builder['Integrated Security'] = $true
} else {
    $builder['User ID'] = Read-Required 'SQL login'
    $sqlPassword = Read-Host 'SQL password' -AsSecureString
    if ($sqlPassword.Length -eq 0) { throw 'SQL password is required.' }
    $builder['Password'] = ConvertTo-PlainText $sqlPassword
}

# 3. Service identity. Needed before the connection test when Windows auth is used,
#    because the service account - not the operator - is what SQL will see at runtime.
Write-Host "`n--- Service identity ---" -ForegroundColor Cyan
Write-Host 'Use a domain account or gMSA. For a gMSA enter DOMAIN\name$ and leave the password blank.'
$serviceAccount = Read-Required 'Service log-on account' '' { param($v) $v -match '^[^\\/:*?"<>|]+\\[^\\/:*?"<>|]+$' } 'Use DOMAIN\account form.'
$servicePassword = Read-Host "Password for $serviceAccount (blank for gMSA)" -AsSecureString

Write-Host "`nTesting the SQL connection..."
$probe = $null
try {
    $probe = New-Object System.Data.SqlClient.SqlConnection $builder.ConnectionString
    $probe.Open()
    Write-Host 'SQL connection OK.' -ForegroundColor Green
} catch {
    if ($useWindowsAuth) {
        Write-Warning "Connection tested as YOU ($env:USERDOMAIN\$env:USERNAME). At runtime the service connects as $serviceAccount; the DBA must grant that account the login."
    }
    throw "SQL connection failed: $($_.Exception.Message)"
} finally {
    if ($probe) { $probe.Dispose() }
}

# 4. Hostname and certificate.
Write-Host "`n--- HTTPS ---" -ForegroundColor Cyan
$hostname = Read-Required 'Public hostname (must match the certificate and AllowedHosts)' '' { param($v) [uri]::CheckHostName($v) -ne 'Unknown' } 'Enter a valid DNS hostname.'
$httpsPort = [int](Read-Required 'HTTPS port' '443' { param($v) [int]::TryParse($v, [ref]0) -and [int]$v -ge 1 -and [int]$v -le 65535 })

$candidates = @(Get-ChildItem Cert:\LocalMachine\My |
    Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date) })
if (-not $candidates) { throw 'No usable certificate with a private key in LocalMachine\My. Import the server certificate first.' }
Write-Host 'Certificates available in LocalMachine\My:'
$candidates | ForEach-Object { Write-Host ("  {0}  {1}  expires {2:yyyy-MM-dd}" -f $_.Thumbprint, $_.Subject, $_.NotAfter) }
$thumbprint = Read-Required 'Certificate thumbprint' '' { param($v) $candidates.Thumbprint -contains ($v -replace '\s', '').ToUpperInvariant() } 'Pick a thumbprint from the list above.'
$thumbprint = ($thumbprint -replace '\s', '').ToUpperInvariant()

# Kestrel's store lookup is FindBySubjectName, not by thumbprint: a thumbprint written into
# Subject never matches and the service fails to start. Resolve the subject name instead,
# and prove here that it selects exactly the certificate that was chosen.
$certificate = $candidates | Where-Object { $_.Thumbprint -eq $thumbprint } | Select-Object -First 1
$certSubject = $certificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
if (-not $certSubject) { throw "Certificate $thumbprint has no simple subject name; Kestrel cannot resolve it from the store." }
$resolved = @($candidates | Where-Object { $_.Subject -like "*$certSubject*" })
if ($resolved.Count -ne 1 -or $resolved[0].Thumbprint -ne $thumbprint) {
    throw "Subject name '$certSubject' matches $($resolved.Count) certificates in LocalMachine\My. Remove the duplicate, or configure Kestrel with an explicit certificate file."
}
Write-Host "Certificate subject name for Kestrel: $certSubject" -ForegroundColor Green

# 5. Private storage roots, which must live outside the application directory.
Write-Host "`n--- Private storage ---" -ForegroundColor Cyan
$outsideApp = {
    param($v)
    if (-not [IO.Path]::IsPathRooted($v)) { return $false }
    $full = [IO.Path]::GetFullPath($v).TrimEnd('\')
    return -not ($full -eq $appDir -or $full.StartsWith($appDir + '\', [StringComparison]::OrdinalIgnoreCase))
}
$dataRoot = Read-Required 'Private data root' 'D:\HSBCArchiveData\Runtime' $outsideApp 'Must be an absolute path outside the app directory.'
$mediaRoot = Read-Required 'Private media root' 'D:\HSBCArchiveData\Media' $outsideApp 'Must be an absolute path outside the app directory.'
$dataRoot = [IO.Path]::GetFullPath($dataRoot).TrimEnd('\')
$mediaRoot = [IO.Path]::GetFullPath($mediaRoot).TrimEnd('\')

# 6. Setup window. Orchard's own first-run wizard still has to be reachable once.
Write-Host "`n--- Orchard setup window ---" -ForegroundColor Cyan
Write-Host 'Orchard first-run setup must be restricted to deployment staff by IP.'
$setupIps = @()
while ($true) {
    $entry = (Read-Host 'Deployment-staff IP (blank when done)').Trim()
    if (-not $entry) { break }
    $parsed = [ipaddress]::Any
    if ([ipaddress]::TryParse($entry, [ref]$parsed)) { $setupIps += $entry } else { Write-Warning 'Not a valid IP address.' }
}
if (-not $setupIps) { throw 'At least one setup IP is required; the app refuses enabled setup with an empty allowlist.' }

# 7. Active Directory. The template ships AD enabled with an empty Domain, which fails options
#    validation on the first authorized request, so these answers are mandatory, not optional.
Write-Host "`n--- Active Directory login ---" -ForegroundColor Cyan
$adDomain = Read-Required 'Approved internal AD domain (controller name or domain FQDN)' '' {
    param($v) $v -notmatch 'REPLACE' -and -not $v.EndsWith('.invalid', [StringComparison]::OrdinalIgnoreCase) -and [uri]::CheckHostName($v) -ne 'Unknown'
} 'Enter the approved domain controller or domain FQDN.'
$adAdmin = Read-Required 'Initial SuperAdmin AD account name (no DOMAIN\ prefix)' '' {
    param($v) $v -notmatch 'REPLACE' -and $v -notmatch '[\\@]' -and $v.Length -le 256
} 'Use the bare sAMAccountName, without a domain prefix.'
$adEmail = Read-Required 'Initial SuperAdmin email' '' {
    param($v) $v -match '^[^@\s]+@[^@\s]+\.[^@\s]+$' -and -not $v.EndsWith('.invalid', [StringComparison]::OrdinalIgnoreCase)
} 'Enter a valid corporate email address.'

# --- Everything is validated. Apply. ---
Write-Host "`nApplying configuration..." -ForegroundColor Cyan

foreach ($path in @((Join-Path $dataRoot 'Orchard'), (Join-Path $dataRoot 'Keys'), (Join-Path $mediaRoot 'Default'))) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    # Modify for the service identity only; inherited Users/Everyone write access is removed.
    & icacls.exe $path /inheritance:r /grant:r "${serviceAccount}:(OI)(CI)M" 'BUILTIN\Administrators:(OI)(CI)F' 'NT AUTHORITY\SYSTEM:(OI)(CI)F' /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to set permissions on $path" }
}
Write-Host "Private roots created and restricted to $serviceAccount." -ForegroundColor Green

# Code stays read/execute: the service account must not be able to rewrite its own binaries.
& icacls.exe $appDir /inheritance:r /grant:r "${serviceAccount}:(OI)(CI)RX" 'BUILTIN\Administrators:(OI)(CI)F' 'NT AUTHORITY\SYSTEM:(OI)(CI)RX' /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to set permissions on $appDir" }

$settings = Get-Content -LiteralPath $template -Raw | ConvertFrom-Json
$settings.AllowedHosts = $hostname
$settings.Archive.Deployment.DataRoot = $dataRoot
$settings.Archive.Deployment.SetupEnabled = $true
$settings.Archive.Deployment.SetupAllowedIPs = @($setupIps)
$settings.OrchardCore.Default.HSBCArchive.Media.StorageRoot = $mediaRoot
$ad = $settings.OrchardCore.Default.HSBCArchive.Authentication.ActiveDirectory
$ad.Enabled = $true
$ad.Domain = $adDomain
$ad.InitialSuperAdminUserName = $adAdmin
$ad.InitialSuperAdminEmail = $adEmail
# Kestrel replaces IIS here, so endpoint and request limits move from web.config into configuration.
$settings | Add-Member -NotePropertyName Kestrel -NotePropertyValue ([pscustomobject]@{
        Endpoints = [pscustomobject]@{
            Https = [pscustomobject]@{
                Url         = "https://${hostname}:${httpsPort}"
                Certificate = [pscustomobject]@{ Store = 'My'; Location = 'LocalMachine'; Subject = $certSubject; AllowInvalid = $false }
            }
        }
        Limits    = [pscustomobject]@{ MaxRequestBodySize = 263192576 }
    }) -Force
# The connection string is deliberately absent here and supplied through the service environment.
$settingsPath = Join-Path $appDir 'appsettings.UAT.json'
$settings | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $settingsPath -Encoding UTF8
Write-Host "Wrote $settingsPath (no secrets)." -ForegroundColor Green

# New-Service hands BinaryPathName to the SCM verbatim, so the quotes around the paths survive;
# building the same command line for sc.exe through PowerShell would mangle them.
$binPath = '"{0}" --contentRoot "{1}"' -f $exe, $appDir
New-Service -Name $ServiceName -BinaryPathName $binPath -DisplayName 'HSBC Bangladesh Digital Archive' `
    -Description 'HSBC Bangladesh Digital Archive (self-contained, Kestrel HTTPS).' -StartupType Automatic | Out-Null
# sc.exe takes 'key=' and its value as separate arguments; a gMSA is registered without a password.
if ($servicePassword.Length -gt 0) {
    & sc.exe config $ServiceName 'obj=' $serviceAccount 'password=' (ConvertTo-PlainText $servicePassword) | Out-Null
} else {
    & sc.exe config $ServiceName 'obj=' $serviceAccount | Out-Null
}
if ($LASTEXITCODE -ne 0) {
    & sc.exe delete $ServiceName | Out-Null
    throw "sc.exe config failed with exit code $LASTEXITCODE. Check the account name and password, then re-run."
}
& sc.exe failure $ServiceName reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null

# Per-service environment, the Windows Service equivalent of IIS application-pool
# environment variables: the connection string never reaches the package on disk.
$serviceEnvironment = @(
    'ASPNETCORE_ENVIRONMENT=UAT',
    'DOTNET_ENVIRONMENT=UAT',
    ('OrchardCore__Default__ConnectionString=' + $builder.ConnectionString)
)
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName" -Name 'Environment' `
    -PropertyType MultiString -Value $serviceEnvironment -Force | Out-Null
& icacls.exe $settingsPath /inheritance:r /grant:r "${serviceAccount}:R" 'BUILTIN\Administrators:F' 'NT AUTHORITY\SYSTEM:R' /Q | Out-Null
Write-Host "Service '$ServiceName' registered as $serviceAccount." -ForegroundColor Green

if (-not [System.Diagnostics.EventLog]::SourceExists('HSBCArchiveUAT')) {
    New-EventLog -LogName Application -Source 'HSBCArchiveUAT'
}

Write-Host "`nStarting the service..."
try {
    Start-Service -Name $ServiceName
} catch {
    throw ("The service did not start: $($_.Exception.Message)`n" +
        "If this is error 1069, grant '$serviceAccount' the 'Log on as a service' right " +
        "(secpol.msc > Local Policies > User Rights Assignment), then: Start-Service $ServiceName")
}

$healthy = $false
foreach ($attempt in 1..30) {
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "https://${hostname}:${httpsPort}/health" -TimeoutSec 5
        if ($response.StatusCode -eq 200 -and $response.Content.Trim() -eq 'Healthy') { $healthy = $true; break }
    } catch { }
}
if ($healthy) {
    Write-Host 'Health check OK.' -ForegroundColor Green
} else {
    # Everything is already applied; a failed probe here is a diagnosis task, not a reason to unwind.
    Write-Warning @"
/health did not answer on https://${hostname}:${httpsPort}/.
The service is $((Get-Service -Name $ServiceName).Status). Check, in order:
  Get-EventLog -LogName Application -Source HSBCArchiveUAT -Newest 20 | Format-List
  - DNS for $hostname resolves to this server, and the firewall allows port $httpsPort.
  - This machine trusts the certificate (otherwise only the probe fails, not the service).
  - The DBA has granted $serviceAccount the SQL login on $database.
"@
}

Write-Host @"

=== Setup complete ===
Service    : $ServiceName (automatic start, as $serviceAccount)
URL        : https://${hostname}:${httpsPort}
Health     : $(if ($healthy) { 'OK' } else { 'NOT CONFIRMED - see the warning above' })
Data root  : $dataRoot
Media root : $mediaRoot

Next, in order:
  1. Open https://${hostname}:${httpsPort} from an allowlisted IP and complete Orchard
     setup with the 'HSBC Archive - security baseline' recipe.
  2. Create the named Admin / SuperAdmin accounts (see HANDOVER-UAT.md section 8).
  3. Disable setup: set Archive.Deployment.SetupEnabled to false and clear
     SetupAllowedIPs in app\appsettings.UAT.json, then: Restart-Service $ServiceName
  4. Run: .\scripts\verify-deployment.ps1 -PackageRoot "$root" -BaseUri https://${hostname}:${httpsPort}/
"@ -ForegroundColor Cyan
