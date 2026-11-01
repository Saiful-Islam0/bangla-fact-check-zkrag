That's the answer: your AD account name is the employee ID, not `rmsff01` — that's just the local Windows profile folder name on the server.

The SuperAdmin was provisioned as `rmsff01`, which doesn't exist in AD, so it can never log in. Since the database is brand new and holds nothing, the clean fix is to redo setup with the right username.

**1. Fix the username and stop the service**

```powershell
Stop-Service HSBCArchive
$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$j.OrchardCore.Default.HSBCArchive.Authentication.ActiveDirectory.InitialSuperAdminUserName = '<your employee ID>'
$j.Archive.Deployment.SetupEnabled = $true
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8
$j.OrchardCore.Default.HSBCArchive.Authentication.ActiveDirectory
```

**2. Reset the database** in SSMS:

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

**3. Clear tenant state and restart**

```powershell
Remove-Item D:\HSBCArchiveData\Runtime\Orchard\Sites -Recurse -Force -ErrorAction SilentlyContinue
Start-Service HSBCArchive
```

**4. Run the wizard again** from your laptop browser, then log in with your **employee ID** and Windows password. The lockout is gone with the old database.

Type the employee ID exactly as AD has it — no domain prefix, no `@`. The check you just ran returning `True` is the same call the login makes, so if that account name worked there, it will work here.
