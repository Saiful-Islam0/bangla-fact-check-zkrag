That's the certificate you want: **issued by `CN=HSBC Issuing CA02-G2`** (internal CA), `Trusted: True`, private key present. Every domain-joined machine will accept it with no warning.

Two things went wrong in what you ran: `<thumbprint>` was pasted literally, so `$cert` was null — which meant `$subject` was null and got written into `appsettings.UAT.json`. That's why the site is now unreachable: Kestrel has no certificate to bind.

Note the certificate's DNS names are **`BDW25135475`** and `BDW25135475_bdw25135475` — **not** the FQDN. So the URL stays the short name.

Save this as `D:\HSBCArchive\fixcert.ps1` and run it, rather than pasting (the console has been merging lines all session):

```powershell
$thumb = '1D5A59D7A72F6AF3B64F23A8DD76312311A6D831'
$cert = Get-Item "Cert:\LocalMachine\My\$thumb"
$subject = $cert.GetNameInfo('SimpleName', $false)
Write-Host "Subject name for Kestrel: $subject"

$name = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert).Key.UniqueName
$keyFile = Join-Path $env:ProgramData "Microsoft\Crypto\Keys\$name"
if (-not (Test-Path -LiteralPath $keyFile)) { $keyFile = Join-Path $env:ProgramData "Microsoft\Crypto\RSA\MachineKeys\$name" }
icacls $keyFile /grant "NT AUTHORITY\NETWORK SERVICE:(R)"

$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$j.Kestrel.Endpoints.Https.Certificate.Subject = $subject
$j.AllowedHosts = 'bdw25135475'
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8

Restart-Service HSBCArchive
Start-Sleep 25
Get-Service HSBCArchive
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
(Invoke-WebRequest https://bdw25135475:9443/health -UseBasicParsing).Content
```

Run it with:

```powershell
powershell -ExecutionPolicy Bypass -File D:\HSBCArchive\fixcert.ps1
```

`Healthy` with no certificate warning and no validation bypass means it's done. Then open **https://bdw25135475:9443** in Edge or Chrome — the padlock should be clean.

Two things to watch:

- **If `GetRSAPrivateKey` errors**, the key is the older CAPI type. Do it by hand instead: `certlm.msc` → Personal → Certificates → right-click the certificate → All Tasks → **Manage Private Keys** → Add `NETWORK SERVICE` with Read. Then re-run the rest.
- **I dropped the FQDN from `AllowedHosts`** deliberately. The certificate doesn't cover `bdw25135475.hbap.adroot.hsbc`, so allowing it would let people reach the site on a URL that always warns. If you want the FQDN to work cleanly, request a new certificate from that CA with both names as SANs.

One cleanup: your earlier run granted NETWORK SERVICE read on a key file while `$cert` was null — it looks like it hit the old self-signed key, which is harmless, but confirm it didn't land on the whole `Keys` folder:

```powershell
icacls "$env:ProgramData\Microsoft\Crypto\Keys"
```

If `NETWORK SERVICE` appears on the **folder** itself, remove it — the service should be able to read its own key, not every machine key on the box:

```powershell
icacls "$env:ProgramData\Microsoft\Crypto\Keys" /remove "NT AUTHORITY\NETWORK SERVICE"
```
