Two separate problems, and your Tomcat discovery explains the first one.

**8443 was already taken by Apache Tomcat.** Kestrel couldn't bind it, so the service started and immediately died — that's the `Stopped` in the warning. My earlier suggestion to check 8443 was free clearly didn't get run; my fault for treating it as optional.

**Also, the AD domain has a typo.** You entered `hpab.adroot.hsbc`, but your server's FQDN is `bdw25135475.HBAP.ADROOT.HSBC` — it's **hbap**, not **hpab**.

### 1. Confirm the cause and find a free port

```powershell
$cert = Get-Item Cert:\LocalMachine\My\F3BF32F7B80337F8C6345DD2E481193E0CF49B13
$name = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert).Key.UniqueName
$keyFile = Join-Path $env:ProgramData "Microsoft\Crypto\Keys\$name"
icacls $keyFile /grant "NT AUTHORITY\NETWORK SERVICE:(R)"
Restart-Service HSBCArchive
Start-Sleep 25
(Invoke-WebRequest https://bdw25135475:9443/health -UseBasicParsing).Content
```

Pick a port that isn't in that list — `9443` is a good bet. Verify:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 9443 -ErrorAction SilentlyContinue
```

No output = free.

### 2. Fix both in one go

```powershell
$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$j.Kestrel.Endpoints.Https.Url = 'https://bdw25135475:9443'
$j.OrchardCore.Default.HSBCArchive.Authentication.ActiveDirectory.Domain = 'hbap.adroot.hsbc'
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8
New-NetFirewallRule -DisplayName 'HSBC Archive UAT HTTPS' -Direction Inbound -Protocol TCP -LocalPort 9443 -Action Allow | Out-Null
Restart-Service HSBCArchive
Start-Sleep 20
Get-Service HSBCArchive
Invoke-WebRequest https://bdw25135475:9443/health -UseBasicParsing | Select-Object -Expand Content
```

You want `Running` and `Healthy`. Then the wizard is at **https://bdw25135475:9443**.

No need to re-run setup — the service, permissions and connection string are all in place; only the config file needed changing.

If the service still stops, paste the event log output from step 1 and I'll read the real error rather than guess again.
