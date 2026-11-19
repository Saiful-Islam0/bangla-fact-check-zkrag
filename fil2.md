Analyzed UatDeployment.cs:L1-72

The **HTTP 400 Bad Request** happens because ASP.NET Core's Host Filtering middleware checks `AllowedHosts` in `<app>\appsettings.UAT.json`. Right now `AllowedHosts` only lists `bdw25135475`, so any request with `Host: archive.bd.hsbc` is rejected with HTTP 400.

> **Important:** In [UatDeployment.cs](file:///Users/saiful/Documents/HSBC/src/HSBC.Archive.Web/Deployment/UatDeployment.cs#L23-L25), `AllowedHosts` supports multiple hostnames separated by `;` with **no spaces** and **no `*` wildcards** (for example: `"archive.bd.hsbc;bdw25135475;bdw25135475.hbap.adroot.hsbc"`).

---

### Step 1: Fix the HTTP 400 Error (`AllowedHosts` in `appsettings.UAT.json`)

Run this in an **elevated PowerShell** session on the server:

```powershell
Import-Module WebAdministration
$app = (Get-Website -Name HSBCArchive).physicalPath
$settingsPath = Join-Path $app "appsettings.UAT.json"

$json = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json

# Semicolon-separated hostnames, NO spaces around semicolons, NO wildcards
$json.AllowedHosts = "archive.bd.hsbc;bdw25135475;bdw25135475.hbap.adroot.hsbc"

$json | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $settingsPath -Encoding UTF8
Restart-WebAppPool -Name HSBCArchive
```

After running this, test **`https://archive.bd.hsbc:9443`**—the 400 error will be gone.

---

### Step 2: If You Want `https://archive.bd.hsbc` Without `:9443` (Port 443)
If your site is currently bound only to port `9443`, visiting `https://archive.bd.hsbc` without `:9443` goes to port `443` (which may hit IIS's Default Web Site or nothing). To make `https://archive.bd.hsbc` work directly on port `443` with a matching certificate:

```powershell
Import-Module WebAdministration

# 1. Create a certificate that covers both the new FQDN and the server hostname
$cert = New-SelfSignedCertificate -Subject "CN=archive.bd.hsbc" `
  -DnsName "archive.bd.hsbc","bdw25135475","bdw25135475.hbap.adroot.hsbc" `
  -CertStoreLocation "Cert:\LocalMachine\My" `
  -FriendlyName "HSBC Archive UAT (archive.bd.hsbc)" `
  -NotAfter (Get-Date).AddYears(2)

# Trust it on the server
Export-Certificate -Cert $cert -FilePath "C:\Temp\archive-bd-hsbc.cer" | Out-Null
Import-Certificate -FilePath "C:\Temp\archive-bd-hsbc.cer" -CertStoreLocation "Cert:\LocalMachine\Root" | Out-Null

# 2. Update the existing 9443 binding to use the new cert
Get-WebBinding -Name HSBCArchive -Protocol https | ForEach-Object {
    $_.AddSslCertificate($cert.Thumbprint, 'My')
}

# 3. Also bind port 443 for archive.bd.hsbc (if port 443 is free or using SNI)
if (-not (Get-WebBinding -Name HSBCArchive -Protocol https -Port 443 -HostHeader "archive.bd.hsbc" -ErrorAction SilentlyContinue)) {
    New-WebBinding -Name HSBCArchive -Protocol https -Port 443 -HostHeader "archive.bd.hsbc" -SslFlags 1
    (Get-WebBinding -Name HSBCArchive -Protocol https -Port 443 -HostHeader "archive.bd.hsbc").AddSslCertificate($cert.Thumbprint, 'My')
}

# Open firewall for 443 if not already open
if (-not (Get-NetFirewallRule -DisplayName "HSBC Archive UAT HTTPS 443" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "HSBC Archive UAT HTTPS 443" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow | Out-Null
}

Restart-WebAppPool -Name HSBCArchive
```

---

### Step 3: Keep the AD Profile Icon Working on `https://archive.bd.hsbc`
Because `archive.bd.hsbc` contains dots, Windows treats it as the **Internet zone** instead of **Local Intranet** by default (so the browser won't silently send your AD token until it's trusted):
1. On your client machine (or via Group Policy), open **Control Panel → Internet Options → Security → Local intranet → Sites → Advanced** and add **`https://archive.bd.hsbc`**.
2. If you test `https://archive.bd.hsbc` from a browser **on the Windows Server itself**, Windows blocks loopback Windows Auth to a custom FQDN unless `BackConnectionHostNames` is registered on the server:
   ```powershell
   New-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa\MSV1_0" `
     -Name "BackConnectionHostNames" -PropertyType MultiString `
     -Value @("archive.bd.hsbc","bdw25135475","bdw25135475.hbap.adroot.hsbc") -Force
   ```
