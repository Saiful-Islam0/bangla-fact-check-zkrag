Thanks — that changes the answer completely. You're on the **self-contained Kestrel service**, and Kestrel picks the certificate by **subject name** from the store, not by thumbprint like IIS. (My project memory says IIS; that's wrong for your actual server and I'll fix it — see the end.)

## 1. Find a trusted certificate

```powershell
Get-ChildItem Cert:\LocalMachine\My | ForEach-Object {
  [pscustomobject]@{
    Thumbprint  = $_.Thumbprint
    SimpleName  = $_.GetNameInfo('SimpleName', $false)
    Issuer      = $_.Issuer
    Expires     = $_.NotAfter.ToString('yyyy-MM-dd')
    DnsNames    = ($_.DnsNameList | ForEach-Object { $_.Unicode }) -join ', '
    PrivateKey  = $_.HasPrivateKey
    Trusted     = [bool](Test-Certificate -Cert $_ -ErrorAction SilentlyContinue -WarningAction SilentlyContinue)
  }
} | Format-List
```

You need `Trusted: True`, `PrivateKey: True`, an `Issuer` that isn't itself, and a `DnsNames` entry matching the name people type. Note the **`SimpleName`** of the one you pick — that's the value Kestrel needs, not the thumbprint.

## 2. Check the subject name is unambiguous

Kestrel matches by *substring*, so this must return exactly one row:

```powershell
$cert = Get-Item Cert:\LocalMachine\My\<thumbprint>
$subject = $cert.GetNameInfo('SimpleName', $false)
$subject
@(Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.Subject -like "*$subject*" }) |
  Select-Object Thumbprint, Subject
```

Two rows means Kestrel could pick the wrong one — delete the stale certificate first.

## 3. Grant the service read on the private key

This is the one that silently drops every TLS handshake while the service shows `Running`:

```powershell
$name = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert).Key.UniqueName
$keyFile = Join-Path $env:ProgramData "Microsoft\Crypto\Keys\$name"
if (-not (Test-Path -LiteralPath $keyFile)) { $keyFile = Join-Path $env:ProgramData "Microsoft\Crypto\RSA\MachineKeys\$name" }
icacls $keyFile /grant "NT AUTHORITY\NETWORK SERVICE:(R)"
```

## 4. Point the app at it and restart

```powershell
$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$j.Kestrel.Endpoints.Https.Certificate.Subject = $subject
$j.AllowedHosts = 'bdw25135475;bdw25135475.hbap.adroot.hsbc'
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8
Restart-Service HSBCArchive
Start-Sleep 25
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest https://bdw25135475.hbap.adroot.hsbc:9443/health -UseBasicParsing | Select-Object -Expand Content
```

Use whichever name the certificate actually covers — usually the FQDN for a machine certificate, which is why `AllowedHosts` gets both. No bypass of certificate validation in that test: if it returns `Healthy`, the chain is genuinely trusted.

## If no trusted certificate exists

Then the server doesn't have one yet and you request it from the internal CA — same `certreq` route as any Windows host. Tell me and I'll give you the request file. The key point is that browsers stop warning only when they trust the **issuer**, which every domain-joined machine does for an internal CA; distributing your self-signed `.cer` means touching each machine instead.

---

**About my memory:** it currently records this deployment as IIS with ANCM in-process, and says the installed package is `0.18.x`. If you're still on the self-contained service at `0.17.0-uat.1`, that's wrong and will mislead the next chat — including the patch-version rule, which would hand you a DLL that won't load. Say the word and I'll correct it; I don't want to overwrite it on a guess, since something updated those files between sessions.
