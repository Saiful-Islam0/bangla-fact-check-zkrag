Fix it on the live install — this must be set **before** the tenant is created, so the database has to be empty (it already is):

```powershell
Stop-Service HSBCArchive
$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$j.OrchardCore.Default | Add-Member -NotePropertyName IdentityColumnSize -NotePropertyValue 'Int64' -Force
$j.Archive.Deployment.SetupEnabled = $true
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8
Remove-Item D:\HSBCArchiveData\Runtime\Orchard -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path D:\HSBCArchiveData\Runtime\Orchard -Force | Out-Null
icacls D:\HSBCArchiveData\Runtime\Orchard /inheritance:r /grant:r "NT AUTHORITY\NETWORK SERVICE:(OI)(CI)M" "BUILTIN\Administrators:(OI)(CI)F" "NT AUTHORITY\SYSTEM:(OI)(CI)F" /Q
$j.OrchardCore.Default
Start-Service HSBCArchive
```

Confirm `IdentityColumnSize : Int64` appears in the printed output, then run the wizard again from your laptop.

Right after the wizard finishes, check in SSMS that both sides now agree:

```sql
SELECT t.name AS table_name, c.name AS column_name, ty.name AS data_type
FROM sys.tables t
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE (t.name = 'HSBC_Document' AND c.name = 'Id') OR c.name = 'DocumentId'
ORDER BY t.name;
```

Every row should say `bigint`. If `HSBC_Document.Id` still comes back as `int`, the setting isn't reaching shell settings and I'll find the right key from the assembly rather than guess again.

I've also added the same line to [config/uat/appsettings.UAT.template.json](config/uat/appsettings.UAT.template.json) so future packages carry it.

---

**Being straight about this one:** it's a real product defect, not a deployment mistake, and it was hidden by the release gap you already have on record — the build verifies against SQLite, and SQL Server acceptance was marked "not executed". The fix above is reasoned from the Orchard issue and the shipped assembly's `GetIdentityColumnSize(ShellSettings)` signature, not tested, which is why the verification query matters.

Sources: [OrchardCMS/OrchardCore#16580](https://github.com/OrchardCMS/OrchardCore/issues/16580), [Orchard Core Data reference](https://docs.orchardcore.net/en/latest/reference/modules/Data/)
