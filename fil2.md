That happens because your existing company certificate (`BDW25135475_bdw25135475`) was issued by HSBC's internal CA **only** for the server's machine name (`bdw25135475` / `bdw25135475.hbap.adroot.hsbc`) before the `archive.bd.hsbc` domain name was created.

In HTTPS, a browser requires the exact hostname in the URL bar (`archive.bd.hsbc`) to be inside the certificate's **Subject Alternative Name (SAN)** list, and a signed certificate cannot have a new domain name added to it without being re-issued by the Certificate Authority (CA).

Here is how to fix it:

---

### Step 1: Check if the Server Can Request the Updated Company Certificate Directly

First, run this in PowerShell on the server to see which internal HSBC CA issued `BDW25135475_bdw25135475`:

```powershell
Get-ChildItem Cert:\LocalMachine\My |
  Where-Object { $_.FriendlyName -like '*25135475*' -or $_.Subject -like '*25135475*' } |
  Select-Object FriendlyName, Subject, Issuer, DnsNameList |
  Format-List
```

Now check if this server has permission to request a new certificate from that same HSBC CA with `archive.bd.hsbc` included:
1. Press `Win + R` on the server, type **`certlm.msc`**, and press Enter.
2. Go to **Personal → Certificates**.
3. Right-click your existing **`BDW25135475_bdw25135475`** certificate → **All Tasks → Advanced Operations → Renew This Certificate with the Same Key...** (or right-click **Certificates → All Tasks → Request New Certificate...**).
4. If the wizard shows an active HSBC template with **"More information is required..."**:
   - Click the link to open **Properties**.
   - Go to the **Subject** tab → under **Alternative name**, select **Type: DNS**, and add:
     - `archive.bd.hsbc`
     - `bdw25135475`
     - `bdw25135475.hbap.adroot.hsbc`
   - Click **OK → Enroll**.
   - Once enrolled, select the newly issued certificate in **IIS Manager → Sites → HSBCArchive → Bindings → https → Edit**.

---

### Step 2: If `certlm.msc` Does Not Allow Self-Enrollment (Generate a CSR for the IT / DNS Team)

If the HSBC CA requires the IT/PKI team (or the colleague who set up `archive.bd.hsbc`) to approve a custom domain certificate, run this script in **elevated PowerShell** on the server. It generates a ready-to-submit **Certificate Signing Request (`C:\Temp\archive-bd-hsbc.csr`)** with `archive.bd.hsbc` and `bdw25135475` in the SANs:

```powershell
New-Item -ItemType Directory -Path "C:\Temp" -Force | Out-Null

$inf = @"
[Version]
Signature="`$Windows NT`$"

[NewRequest]
Subject = "CN=archive.bd.hsbc"
KeyLength = 2048
Exportable = TRUE
MachineKeySet = TRUE
ProviderName = "Microsoft RSA SChannel Cryptographic Provider"
RequestType = PKCS10
KeyUsage = 0xa0

[EnhancedKeyUsageExtension]
OID=1.3.6.1.5.5.7.3.1

[Extensions]
2.5.29.17 = "{text}"
_continue_ = "dns=archive.bd.hsbc&"
_continue_ = "dns=bdw25135475&"
_continue_ = "dns=bdw25135475.hbap.adroot.hsbc"
"@

$inf | Set-Content -LiteralPath "C:\Temp\request.inf" -Encoding ASCII
certreq.exe -new -f "C:\Temp\request.inf" "C:\Temp\archive-bd-hsbc.csr"
Write-Host "CSR created at C:\Temp\archive-bd-hsbc.csr" -ForegroundColor Green
```

Send **`C:\Temp\archive-bd-hsbc.csr`** to the colleague/team who set up `archive.bd.hsbc` so they can sign it with HSBC's internal CA and return the `.cer` file. Once they send back `archive-bd-hsbc.cer`, you just run:
```powershell
certreq.exe -accept "C:\Temp\archive-bd-hsbc.cer"
```
and pick it in IIS Bindings—then **every HSBC laptop will trust `https://archive.bd.hsbc` with a green/valid lock and zero warnings**.
