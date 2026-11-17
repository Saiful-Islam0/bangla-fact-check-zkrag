Analyzed uat-iis-deployment.md:L1-336
Analyzed frontend.md:L1-332
Analyzed frontend.md:L1-332
Analyzing setup-iis.ps1:L1-800
Analyzed Program.cs:L1-4
Analyzed ArchiveApplication.cs:L1-177
Analyzed setup-iis.ps1:L1-638
Analyzed ArchiveController.cs:L1-107
Ran list Frontend controllers
Analyzed BrandingController.cs:L1-23
Analyzed archive.js:L1-346
Ran find whoami endpoint in source
Analyzed web.config:L1-44
Analyzed ArchiveProfileController.cs:L1-50
Analyzed ArchiveWindowsProfile.cs:L1-86

Under IIS, the profile chip works through `/archive/whoami`:
1. The browser calls `/archive/whoami` anonymously.
2. The app returns `401 Unauthorized` once so **IIS** can attach a `WWW-Authenticate: Negotiate` challenge.
3. The browser replies with your Windows token, IIS populates `HttpContext.User`, and `/archive/whoami` returns your account/admin JSON.

Because `setup-iis.ps1` leaves **Windows Authentication disabled** in IIS (and the earlier `Install-WindowsFeature` command did not include the `Web-Windows-Auth` role service), IIS sends back a bare `401` with no `WWW-Authenticate` header, so the browser never sends a token and the chip stays hidden.

### Step 1: Install & enable Windows Authentication on the IIS site (keep Anonymous enabled)

Run this in an **elevated PowerShell** session on the UAT server:

```powershell
# 1. Ensure the IIS Windows Authentication role feature is installed
Install-WindowsFeature -Name Web-Windows-Auth

# 2. Keep Anonymous Authentication ENABLED (so public pages don't challenge),
#    and enable Windows Authentication alongside it (so /archive/whoami's 401 gets a Negotiate header)
Import-Module WebAdministration

Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Location 'HSBCArchive' `
  -Filter 'system.webServer/security/authentication/anonymousAuthentication' `
  -Name 'enabled' -Value $true

Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Location 'HSBCArchive' `
  -Filter 'system.webServer/security/authentication/windowsAuthentication' `
  -Name 'enabled' -Value $true

Restart-WebAppPool -Name HSBCArchive
```

### Step 2: Verify the challenge header on the server

Still in PowerShell on the server, run:

```powershell
[Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
try {
    Invoke-WebRequest -UseBasicParsing -Uri "https://localhost:9443/archive/whoami"
} catch {
    $_.Exception.Response.StatusCode
    $_.Exception.Response.Headers['WWW-Authenticate']
}
```
*(Replace `9443` if you bound the site to `443`.)*
- It should print `Unauthorized` followed by **`Negotiate, NTLM`**.

### Step 3: Check in your browser
Reload the site from your domain-joined HSBC laptop:
- If you access the site via its **short hostname** (e.g. `https://servername:9443`), Edge/Chrome automatically treats it as **Local Intranet** and silently answers the challenge—the AD profile chip should appear immediately.
- If you access it via an **FQDN with dots** (or IP address) and either see a login popup or still no chip, the URL isn't in Windows' Local Intranet zone yet. To test on your laptop, open **Control Panel → Internet Options → Security → Local intranet → Sites → Advanced**, add `https://<your-hostname>`, and reload.

Run Step 1 and Step 2 and let me know what the test command outputs (or what happens in the browser)!
