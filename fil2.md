Login is working then — that 403 means you authenticated but have no permissions. `SuperAdmin` does include `AccessAdminPanel` ([ArchiveRoles.cs:18-20](src/Modules/HSBC.Archive.Admin/Security/ArchiveRoles.cs#L18-L20)), so the role never got attached to your account. (The super-user being rejected is expected — AD is the only accepted credential.)

Confirm which way it failed:

```powershell
Get-EventLog -LogName Application -Source HSBCArchiveUAT -Newest 40 |
  Where-Object { $_.EventID -in 2100, 2110, 2111, 2112 } |
  Format-List TimeGenerated, EventID, Message
```

- **2111** — provisioned fine, and the role is there; then the 403 is something else.
- **2112** — provisioning aborted partway. It creates the user, adds the AD login, *then* adds the role ([ArchiveAdProvisioning.cs:45-53](src/Modules/HSBC.Archive.Admin/Security/Ad/ArchiveAdProvisioning.cs#L45-L53)) — a failure in between leaves exactly what you're seeing: an account that can log in but owns nothing.

And check what the account actually has, in SSMS:

```sql
SELECT Content FROM HSBC_Document WHERE Type LIKE '%OrchardCore.Users.Models.User%';
```

Look for `"RoleNames"` in that JSON — I expect it to be empty.

Don't try to fix it through the admin UI; you can't get in, and the Orchard super-user can't log in either by design. Once I know which of the two it is, the fix is to make the migration re-run so provisioning completes — send me the event log output and the `RoleNames` value.
