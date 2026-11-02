Two separate things, and the answer differs.

## Viewing — yes, subject to four practical details

- **Network:** the firewall rule opens 9443 to the corporate network, so reachable.
- **URL:** they must use `https://bdw25135475:9443` — with `https`, with the port, and with the **short** name. `AllowedHosts` is only `bdw25135475`, so the FQDN returns 400. Add more names if you want them to work:
  ```json
  "AllowedHosts": "bdw25135475;bdw25135475.hbap.adroot.hsbc"
  ```
- **Certificate warning** on every machine, because it's self-signed. They can click through, or push `D:\HSBCArchive\archive-uat.cer` to Trusted Root via GPO — worth asking your Windows team for, since a security warning trains people badly.
- **Not Internet Explorer.** Edge or Chrome.

To see exactly what a visitor gets without signing in, open the site in a **private window**. That's the definitive check and takes a few seconds.

## Logging in — no, not until you add each person

There's no "any domain user can sign in" mode. Sign-in requires an account that already exists in the archive with an AD link ([ArchiveAdSignInManager.cs:31-33](src/Modules/HSBC.Archive.Admin/Security/Ad/ArchiveAdSignInManager.cs#L31-L33)); the password is then checked against AD. Your own account works because setup provisioned it.

To add someone, signed in as SuperAdmin:

1. Go to **`https://bdw25135475:9443/Admin/HSBCArchive/Users/Create`**
2. Enter their **AD username** (employee ID form, no domain prefix, no `@`) and email
3. On the next screen assign a role — `Admin` for editors, `SuperAdmin` only for people who manage users

They then sign in with that username and their normal Windows password. No password is ever stored by the archive.

## One thing to do right now

The Orchard setup window is still open. Close it before you tell anyone the URL:

```powershell
$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$j.Archive.Deployment.SetupEnabled = $false
$j.Archive.Deployment.SetupAllowedIPs = @()
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8
Restart-Service HSBCArchive
```

While it's open, anyone on an allow-listed address can reach the first-run wizard. Low risk on an internal network, but it's not a window to leave open once people start using the site.
