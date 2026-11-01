Worth saying once: a clean reinstall won't fix the error you're seeing now, because that error happens *after* setup — it's the tenant failing to activate, and the same thing will most likely happen again. But the rebuild is cheap, the script genuinely should carry what we learned, and if it recurs we'll have a clean log to read. So: teardown first, new script, then run it.

## Teardown

```powershell
Stop-Service HSBCArchive -ErrorAction SilentlyContinue
sc.exe delete HSBCArchive
Remove-Item D:\HSBCArchiveData -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item D:\HSBCArchive\app\appsettings.UAT.json -Force -ErrorAction SilentlyContinue
Remove-Item D:\HSBCArchive\error.log, D:\HSBCArchive\foreground.log, D:\HSBCArchive\setup-log.txt -Force -ErrorAction SilentlyContinue
```

In SSMS on BDW25135476:

```sql
USE master;
ALTER DATABASE BDArchive SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
DROP DATABASE BDArchive;
CREATE DATABASE BDArchive;
GO
USE BDArchive;
CREATE USER bdarchive FOR LOGIN bdarchive;
ALTER ROLE db_owner ADD MEMBER bdarchive;
```

Leave the certificate and the 9443 firewall rule — the new script handles both. Now let me write the script.


Replace `D:\HSBCArchive\scripts\setup.ps1` with this, then run it from an elevated **Windows PowerShell** (not IE, not "Run with PowerShell"):

```powershell
cd D:\HSBCArchive
Start-Transcript -Path D:\HSBCArchive\setup-log.txt
.\scripts\setup.ps1
Stop-Transcript
```

### Everything we hit, now handled by the script

| What bit us | What it does now |
|---|---|
| Parameter binding crash at the service-account prompt | Fixed in `Read-Required`, tolerant of argument order |
| SQL cert "chain not trusted" | Asks whether to trust it, defaults to yes |
| Named instance, error 26 | Prompt explains `SERVER\INSTANCE,PORT` and why the instance name alone fails |
| "Database, table prefix already in use" | Queries for `HSBC_` tables and warns *before* changing anything |
| Port 8443 taken by Tomcat | Rejects any port that already has a listener; defaults to 9443 |
| Certificate CN didn't match the hostname | Offers to create a correct self-signed cert with the hostnames as SANs, and trusts it locally |
| Kestrel can't find a cert by thumbprint | Writes the subject name, and refuses if two certs share it |
| TLS handshakes dropped | Grants the service read access to the certificate's private key |
| 403 from the IPv6 link-local address | Allowlists every local address automatically, zone index included |
| IE can't complete the wizard | Prompts for your workstation IP and says plainly to use Edge/Chrome |
| `hpab` vs `hbap` typo | Defaults the domain from `$env:USERDNSDOMAIN` |
| `rmsff01` wasn't a real AD account | **Validates the account against AD before provisioning it** |
| Health probe failing on PowerShell TLS | Forces TLS 1.2 and accepts the self-signed cert for the probe |
| Stale `tenants.json` causing 404 | Detects it and offers to clear it |
| Firewall | Opens the chosen port |

When it finishes, open the URL from your **laptop** in Edge or Chrome, run the wizard with the **HSBC Archive — security baseline** recipe, and sign in with `45517160` and your Windows password.

---

**Two things I want to be straight about.** First, as I said at the top, this rebuild does not address the "temporarily unavailable / error executing this request" you got after the last successful setup — that failure is in tenant activation, after everything this script does. If it comes back, run the foreground capture and we read the first `Error` line; don't rebuild a third time.

Second, I still cannot test any of this — no Windows here — so the script is reasoned, not run. Keep your current `setup.ps1` as a backup before overwriting. The two new parts I'd watch are the AD verification block and the private-key `icacls`, both of which print a clear message if they misbehave rather than failing silently.






cat > scripts/setup.ps1 <<'PSEOF'
<#
.SYNOPSIS
Interactive first-time setup for the HSBC Bangladesh Digital Archive on a Windows
Server host with no ASP.NET Core Hosting Bundle. Registers the self-contained
publish as a Windows Service listening on Kestrel directly.

.DESCRIPTION
Run from the extracted package root in an elevated Windows PowerShell session:

    .\scripts\setup.ps1

Every answer is validated against the live machine before anything is changed:
the SQL connection is opened, the HTTPS port is checked for a listener, the
certificate's subject name is resolved the way Kestrel resolves it, and the
Active Directory account is verified against the domain.

Secrets are never written to the package, to appsettings or to the transcript.
Passwords stay in SecureString form and reach only sc.exe and the per-service
environment.
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'HSBCArchive',
    [string]$PackageRoot = $(if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { (Get-Location).Path }),
    [switch]$SkipChecksums
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

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

function Read-YesNo([string]$Prompt, [string]$Default = 'Y') {
    (Read-Required "$Prompt [Y/N]" $Default { param($v) $v -match '^[YyNn]$' } 'Answer Y or N.') -match '^[Yy]$'
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
Write-Host 'A named instance needs its port: SERVER\INSTANCE,PORT. The instance name alone only works'
Write-Host 'when the SQL Browser service is reachable on UDP 1434.'
$sqlHost = Read-Required 'SQL Server host (e.g. SQLUAT01,1433 or SQLUAT01\INST,2433)'
$database = Read-Required 'Database name' 'HSBCArchive_UAT' { param($v) $v -match '^[A-Za-z0-9_]+$' } 'Letters, digits and underscore only.'

$builder = New-Object System.Data.SqlClient.SqlConnectionStringBuilder
$builder['Data Source'] = $sqlHost
$builder['Initial Catalog'] = $database
$builder['Encrypt'] = $true
# A SQL Server with a self-signed certificate fails validation; the traffic stays encrypted either way.
$builder['TrustServerCertificate'] = Read-YesNo 'Trust the SQL Server certificate without validating it (needed for a self-signed SQL cert)' 'Y'

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
Write-Host 'A domain account or gMSA (DOMAIN\name$, blank password), or the built-in'
Write-Host 'NT AUTHORITY\NETWORK SERVICE when the database uses a SQL login.'
$serviceAccount = Read-Required 'Service log-on account' 'NT AUTHORITY\NETWORK SERVICE' { param($v) $v -match '^[^\\/:*?"<>|]+\\[^\\/:*?"<>|]+$' } 'Use DOMAIN\account form.'
$servicePassword = Read-Host "Password for $serviceAccount (blank for gMSA or a built-in account)" -AsSecureString

Write-Host "`nTesting the SQL connection..."
$probe = $null
try {
    $probe = New-Object System.Data.SqlClient.SqlConnection $builder.ConnectionString
    $probe.Open()
    Write-Host 'SQL connection OK.' -ForegroundColor Green
    # Orchard refuses to set up over its own tables; catch that here rather than at the wizard.
    $command = $probe.CreateCommand()
    $command.CommandText = "SELECT COUNT(*) FROM sys.tables WHERE name LIKE 'HSBC[_]%'"
    if ([int]$command.ExecuteScalar() -gt 0) {
        Write-Warning "$database already contains HSBC_ tables from an earlier setup."
        Write-Warning 'Orchard will refuse the wizard with "database, table prefix schema are already in use".'
        if (-not (Read-YesNo 'Continue anyway' 'N')) { throw 'Drop and recreate the database, then re-run.' }
    }
} catch [System.Data.SqlClient.SqlException] {
    if ($useWindowsAuth) {
        Write-Warning "Connection tested as YOU ($env:USERDOMAIN\$env:USERNAME). At runtime the service connects as $serviceAccount; the DBA must grant that account the login."
    }
    throw "SQL connection failed: $($_.Exception.Message)"
} finally {
    if ($probe) { $probe.Dispose() }
}

# 4. Hostname, port and certificate.
Write-Host "`n--- HTTPS ---" -ForegroundColor Cyan
$hostname = Read-Required 'Public hostname (short name or FQDN; must match the certificate)' $env:COMPUTERNAME.ToLowerInvariant() {
    param($v) [uri]::CheckHostName($v) -ne 'Unknown'
} 'Enter a valid DNS hostname.'
$httpsPort = [int](Read-Required 'HTTPS port' '9443' {
        param($v)
        if (-not ([int]::TryParse($v, [ref]0)) -or [int]$v -lt 1 -or [int]$v -gt 65535) { return $false }
        # Another service on the port means Kestrel cannot bind and the service dies at start.
        if (Get-NetTCPConnection -State Listen -LocalPort ([int]$v) -ErrorAction SilentlyContinue) {
            Write-Warning "Port $v is already in use on this server."
            return $false
        }
        return $true
    } 'Enter a free TCP port.')

$candidates = @(Get-ChildItem Cert:\LocalMachine\My |
    Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date) })
if ($candidates) {
    Write-Host 'Certificates available in LocalMachine\My:'
    $candidates | ForEach-Object { Write-Host ("  {0}  {1}  expires {2:yyyy-MM-dd}" -f $_.Thumbprint, $_.Subject, $_.NotAfter) }
}
$certificate = $null
if (-not $candidates -or (Read-YesNo 'Create a new self-signed certificate for this hostname' 'Y')) {
    # Subject deliberately avoids the hostname: Kestrel matches the store by subject-name substring,
    # so a subject that also appears in another certificate cannot be resolved unambiguously.
    $names = @($hostname)
    if ($env:USERDNSDOMAIN -and $hostname -notlike '*.*') { $names += "$hostname.$($env:USERDNSDOMAIN.ToLowerInvariant())" }
    $certificate = New-SelfSignedCertificate -Subject 'CN=HSBCArchiveUAT' -DnsName $names `
        -CertStoreLocation Cert:\LocalMachine\My -FriendlyName 'HSBC Archive UAT' -NotAfter (Get-Date).AddYears(2)
    $export = Join-Path $root 'archive-uat.cer'
    Export-Certificate -Cert $certificate -FilePath $export | Out-Null
    Import-Certificate -FilePath $export -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    Write-Host "Created and trusted a self-signed certificate for: $($names -join ', ')" -ForegroundColor Green
    Write-Host "Install $export in Trusted Root on client machines to avoid browser warnings."
} else {
    $thumbprint = Read-Required 'Certificate thumbprint' '' { param($v) $candidates.Thumbprint -contains ($v -replace '\s', '').ToUpperInvariant() } 'Pick a thumbprint from the list above.'
    $certificate = $candidates | Where-Object { $_.Thumbprint -eq ($thumbprint -replace '\s', '').ToUpperInvariant() } | Select-Object -First 1
}

$certSubject = $certificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
if (-not $certSubject) { throw 'The chosen certificate has no simple subject name; Kestrel cannot resolve it from the store.' }
$resolved = @(Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.Subject -like "*$certSubject*" })
if ($resolved.Count -ne 1 -or $resolved[0].Thumbprint -ne $certificate.Thumbprint) {
    throw "Subject name '$certSubject' matches $($resolved.Count) certificates in LocalMachine\My. Remove the duplicate and re-run."
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
# Orchard records the tenant here. Left behind, the archive serves 404 instead of the wizard.
$tenants = Join-Path $dataRoot 'Orchard\tenants.json'
if (Test-Path -LiteralPath $tenants) {
    Write-Warning "$tenants records an existing tenant from a previous setup."
    if (-not (Read-YesNo 'Delete it so the setup wizard runs again' 'Y')) { throw 'Remove the stale tenant state, then re-run.' }
    Remove-Item -LiteralPath (Join-Path $dataRoot 'Orchard') -Recurse -Force
}

# 6. Setup window. Orchard's own first-run wizard still has to be reachable once.
Write-Host "`n--- Orchard setup window ---" -ForegroundColor Cyan
# A browser on the console reaches the app over the IPv6 link-local address, zone index included,
# so every local address is allowed; the filter compares addresses exactly, with no ranges.
$setupIps = @('127.0.0.1', '::1')
foreach ($address in Get-NetIPAddress) {
    $value = ($address.IPAddress -split '%')[0]
    $setupIps += $(if ($value -like 'fe80*') { "$value%$($address.InterfaceIndex)" } else { $value })
}
Write-Host 'This server''s own addresses are allowed automatically.'
Write-Host 'Add the workstation you will run the wizard from - the server console only has Internet'
Write-Host 'Explorer, which cannot complete the setup form.'
while ($true) {
    $entry = (Read-Host 'Additional deployment-staff IP (blank when done)').Trim()
    if (-not $entry) { break }
    $parsed = [ipaddress]::Any
    if ([ipaddress]::TryParse($entry, [ref]$parsed)) { $setupIps += $entry } else { Write-Warning 'Not a valid IP address.' }
}
$setupIps = @($setupIps | Sort-Object -Unique)

# 7. Active Directory. The template ships AD enabled with an empty Domain, which fails options
#    validation on the first authorized request, so these answers are mandatory, not optional.
Write-Host "`n--- Active Directory login ---" -ForegroundColor Cyan
Write-Host 'Local passwords are refused outside Development: the first SuperAdmin signs in with'
Write-Host 'an AD account, so this must be the real account name, not a Windows profile folder name.'
$adDomain = Read-Required 'Approved internal AD domain (controller name or domain FQDN)' $env:USERDNSDOMAIN {
    param($v) $v -notmatch 'REPLACE' -and -not $v.EndsWith('.invalid', [StringComparison]::OrdinalIgnoreCase) -and [uri]::CheckHostName($v) -ne 'Unknown'
} 'Enter the approved domain controller or domain FQDN.'
$adAdmin = Read-Required 'Initial SuperAdmin AD account name (no DOMAIN\ prefix)' '' {
    param($v) $v -notmatch 'REPLACE' -and $v -notmatch '[\\@]' -and $v.Length -le 256
} 'Use the bare sAMAccountName, without a domain prefix.'
$adEmail = Read-Required 'Initial SuperAdmin email' '' {
    param($v) $v -match '^[^@\s]+@[^@\s]+\.[^@\s]+$' -and -not $v.EndsWith('.invalid', [StringComparison]::OrdinalIgnoreCase)
} 'Enter a valid corporate email address.'

Write-Host "`nThe archive validates this account against the domain at every login."
Write-Host 'Checking it now avoids provisioning a SuperAdmin that can never sign in.'
Write-Warning 'A wrong password counts towards the domain lockout policy for this account. Enter it once, or skip.'
if (Read-YesNo "Verify $adAdmin against $adDomain now" 'Y') {
    $adPassword = Read-Host "Windows password for $adAdmin" -AsSecureString
    Add-Type -AssemblyName System.DirectoryServices.AccountManagement
    $directory = $null
    try {
        $directory = New-Object System.DirectoryServices.AccountManagement.PrincipalContext('Domain', $adDomain)
        if ($directory.ValidateCredentials($adAdmin, (ConvertTo-PlainText $adPassword))) {
            Write-Host 'Active Directory accepted the account.' -ForegroundColor Green
        } else {
            throw "Active Directory rejected '$adAdmin'. Run 'whoami' on your own machine and use the part after the backslash."
        }
    } catch [System.DirectoryServices.AccountManagement.PrincipalException] {
        throw "Could not reach the domain '$adDomain': $($_.Exception.Message)"
    } finally {
        if ($directory) { $directory.Dispose() }
    }
}

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

# New-SelfSignedCertificate grants the private key to SYSTEM and Administrators only. Without this
# the service starts, binds the port, and then drops every TLS handshake.
$keyName = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($certificate).Key.UniqueName
$keyFile = Join-Path $env:ProgramData "Microsoft\Crypto\Keys\$keyName"
if (-not (Test-Path -LiteralPath $keyFile)) { $keyFile = Join-Path $env:ProgramData "Microsoft\Crypto\RSA\MachineKeys\$keyName" }
if (Test-Path -LiteralPath $keyFile) {
    & icacls.exe $keyFile /grant "${serviceAccount}:(R)" /Q | Out-Null
    Write-Host "Certificate private key readable by $serviceAccount." -ForegroundColor Green
} else {
    Write-Warning "Could not locate the certificate private key file ($keyName). If TLS handshakes fail, grant $serviceAccount read access to it manually."
}

$settings = Get-Content -LiteralPath $template -Raw | ConvertFrom-Json
$settings.AllowedHosts = $hostname
$settings.Archive.Deployment.DataRoot = $dataRoot
$settings.Archive.Deployment.SetupEnabled = $true
$settings.Archive.Deployment.SetupAllowedIPs = [string[]]$setupIps
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

if (-not (Get-NetFirewallRule -DisplayName "HSBC Archive UAT HTTPS" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'HSBC Archive UAT HTTPS' -Direction Inbound -Protocol TCP `
        -LocalPort $httpsPort -Action Allow | Out-Null
    Write-Host "Firewall opened for inbound TCP $httpsPort." -ForegroundColor Green
}

# New-Service hands BinaryPathName to the SCM verbatim, so the quotes around the paths survive;
# building the same command line for sc.exe through PowerShell would mangle them.
$binPath = '"{0}" --contentRoot "{1}"' -f $exe, $appDir
New-Service -Name $ServiceName -BinaryPathName $binPath -DisplayName 'HSBC Bangladesh Digital Archive' `
    -Description 'HSBC Bangladesh Digital Archive (self-contained, Kestrel HTTPS).' -StartupType Automatic | Out-Null
# sc.exe takes 'key=' and its value as separate arguments; gMSA and built-in accounts take no password.
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

# The probe must not fail merely because this machine does not trust a self-signed certificate.
$previousValidation = [Net.ServicePointManager]::ServerCertificateValidationCallback
[Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
$healthy = $false
try {
    foreach ($attempt in 1..30) {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "https://${hostname}:${httpsPort}/health" -TimeoutSec 5
            if ($response.StatusCode -eq 200 -and $response.Content.Trim() -eq 'Healthy') { $healthy = $true; break }
        } catch { }
    }
} finally {
    [Net.ServicePointManager]::ServerCertificateValidationCallback = $previousValidation
}
if ($healthy) {
    Write-Host 'Health check OK.' -ForegroundColor Green
} else {
    # Everything is already applied; a failed probe here is a diagnosis task, not a reason to unwind.
    Write-Warning @"
/health did not answer on https://${hostname}:${httpsPort}/.
The service is $((Get-Service -Name $ServiceName).Status). Check, in order:
  Get-EventLog -LogName Application -Source HSBCArchiveUAT -Newest 20 | Format-List
  - $hostname resolves to this server, and nothing else holds port $httpsPort.
  - $serviceAccount can read the certificate's private key.
  - The DBA has granted the SQL login used by the service on $database.
To see the real error, stop the service and run: $exe --contentRoot "$appDir"
"@
}

Write-Host @"

=== Setup complete ===
Service    : $ServiceName (automatic start, as $serviceAccount)
URL        : https://${hostname}:${httpsPort}
Health     : $(if ($healthy) { 'OK' } else { 'NOT CONFIRMED - see the warning above' })
Data root  : $dataRoot
Media root : $mediaRoot
AD login   : $adAdmin on $adDomain

Next, in order:
  1. From an allowlisted workstation, in Edge or Chrome - NOT Internet Explorer - open
     https://${hostname}:${httpsPort} and complete Orchard setup with the
     'HSBC Archive - security baseline' recipe.
  2. Sign in as $adAdmin with that account's Windows password. The Orchard super-user
     password does not work: Active Directory is the only accepted credential.
  3. Disable setup: set Archive.Deployment.SetupEnabled to false and clear
     SetupAllowedIPs in app\appsettings.UAT.json, then: Restart-Service $ServiceName
  4. Run: .\scripts\verify-deployment.ps1 -PackageRoot "$root" -BaseUri https://${hostname}:${httpsPort}/

To start over: stop and delete the service, drop and recreate the database, and delete
$dataRoot\Orchard - all three, or the wizard will not run again.
"@ -ForegroundColor Cyan
PSEOF
grep -c "" scripts/setup.ps1
