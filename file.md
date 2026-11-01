Good news hidden in that: the account exists and is AD-mapped, so provisioning worked. The lockout is the archive's own Identity lockout — **5 failed attempts, 15 minutes** ([appsettings template](config/uat/appsettings.UAT.template.json)) — triggered by the earlier failed logins.

**Wait 15 minutes**, then try once. Don't keep retrying: every wrong attempt also counts against your **real AD account's** bad-password counter, and you can lock yourself out of Windows domain-wide.

While you wait, verify the password and domain path independently, outside the app. Run this on the server **once**:

```powershell
Add-Type -AssemblyName System.DirectoryServices.AccountManagement
$pc = New-Object System.DirectoryServices.AccountManagement.PrincipalContext('Domain','hbap.adroot.hsbc')
$pc.ValidateCredentials('rmsff01','<your password>')
```

- **True** → password and domain are right; the archive login will work once the lockout expires.
- **False** → wrong password, or `rmsff01` isn't the right account name. Check with `whoami` on your laptop — it prints `domain\username`, and the archive needs just the username part.
- **An exception** → the service can't reach the domain this way; we'd switch `Domain` to a specific domain controller hostname.

This uses exactly the same call the archive uses ([ArchiveAdVerifier.cs:33-35](src/Modules/HSBC.Archive.Admin/Security/Ad/ArchiveAdVerifier.cs#L33-L35)), so whatever it returns is what the login will do.

Same caution: that call hits AD for real. Run it once with the password you're confident about, not repeatedly.
