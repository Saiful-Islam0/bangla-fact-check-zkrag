The HTTPS warning happens because the original certificate bound to IIS only had `bdw25135475` on it—not `archive.bd.hsbc` (`ERR_CERT_COMMON_NAME_INVALID`).

Here are the two ways to fix it:

---

### 1. Immediate Fix: Replace the IIS Certificate with One Covering `archive.bd.hsbc`

Run this in **elevated PowerShell** on the server (this creates the folder if missing, generates a certificate covering both `archive.bd.hsbc` and `bdw25135475`, trusts it on the server, and rebinds IIS to it):

```powershell
Import-Module WebAdministration
New-Item -ItemType Directory -Path "C:\Temp" -Force | Out-Null

# 1. Create a certificate with Subject Alternative Names for archive.bd.hsbc + bdw25135475
$cert = New-SelfSignedCertificate -Subject "CN=archive.bd.hsbc" `
  -DnsName "archive.bd.hsbc","bdw25135475","bdw25135475.hbap.adroot.hsbc" `
  -CertStoreLocation "Cert:\LocalMachine\My" `
  -FriendlyName "HSBC Archive UAT (archive.bd.hsbc)" `
  -KeyExportPolicy Exportable `
  -NotAfter (Get-Date).AddYears(2)

# 2. Trust it in the Server's Trusted Root store
$cerPath = "C:\Temp\archive-bd-hsbc.cer"
Export-Certificate -Cert $cert -FilePath $cerPath -Force | Out-Null
Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\LocalMachine\Root" | Out-Null

# 3. Rebind all HTTPS bindings on HSBCArchive to this new certificate
Get-WebBinding -Name HSBCArchive -Protocol https | ForEach-Object {
    $_.AddSslCertificate($cert.Thumbprint, "My")
}

Write-Host "Bound new cert ($($cert.Thumbprint)) to HSBCArchive. Exported to $cerPath" -ForegroundColor Green
```

- **On the server itself:** Close and reopen Edge/Chrome, then open `https://archive.bd.hsbc:9443`—the warning will be gone.
- **On your laptop:** Copy `C:\Temp\archive-bd-hsbc.cer` from the server to your laptop, double-click it → **Install Certificate** → **Local Machine** → **Place all certificates in the following store** → **Browse** → **Trusted Root Certification Authorities** → **Finish**, then restart your browser.

---

### 2. So Every HSBC Laptop Trusts It Automatically (For CEO / CIO / ExCo Review)

A self-signed certificate is only trusted by machines that have `archive-bd-hsbc.cer` in their Trusted Root store. So that **nobody else (like the CEO or CIO) sees a certificate warning** on their laptop:

Check if the server can request a certificate from HSBC's internal Active Directory Enterprise CA:
1. On the server, press `Win + R`, type **`certlm.msc`**, and press Enter.
2. Expand **Personal → Certificates**, right-click **Certificates → All Tasks → Request New Certificate...** → click **Next → Next**.
3. If you see an internal template such as **Web Server** (or **HSBC Internal Web Server**):
   - Click **More information is required to enroll for this certificate. Click here to configure settings.**
   - Under **Subject → Subject name → Type: Common name**, add `archive.bd.hsbc`.
   - Under **Alternative name → Type: DNS**, add `archive.bd.hsbc`, `bdw25135475`, and `bdw25135475.hbap.adroot.hsbc`.
   - Click **OK → Enroll**, and then select that certificate in **IIS Manager → Sites → HSBCArchive → Bindings → https → Edit → SSL certificate**.
4. If no template is listed there, send the hostname `archive.bd.hsbc` (or a CSR from **IIS Manager → Server Certificates → Create Certificate Request**) to the network/IT team who set up the `archive.bd.hsbc` DNS record—they can issue an internal HSBC CA `.pfx`/`.cer` that every HSBC laptop already trusts automatically.
