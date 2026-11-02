Now it's unambiguous:

- **`45517160`** exists with the `HSBC.ActiveDirectory` login but **`RoleNames: []`** — that's your 403.
- `hsbcbd` is the Orchard super-user with `Administrator` (can't log in: AD only).
- All five roles exist, including `SuperAdmin`.

So provisioning created the account and the login, then failed before attaching the role ([ArchiveAdProvisioning.cs:51-53](src/Modules/HSBC.Archive.Admin/Security/Ad/ArchiveAdProvisioning.cs#L51-L53)) — and because the migration swallows that failure by design (your choice earlier, and the right one: it left the schema intact), it did so silently.

The migration has a re-entry point that does nothing but provision. Rewind it and let it run again.

**1. Stop the service** — Orchard caches documents in memory and would overwrite your edit:

```powershell
Stop-Service HSBCArchive
```

**2. In SSMS:**

```sql
USE BDArchive;

DECLARE @idx INT = (
    SELECT TRY_CAST(m.[key] AS INT)
    FROM HSBC__Document d
    CROSS APPLY OPENJSON(d.Content, '$.DataMigrations') m
    WHERE d.Type LIKE '%DataMigrationRecord%'
      AND JSON_VALUE(m.value, '$.DataMigrationClass') LIKE '%ArchiveRoleMigrations%');

UPDATE HSBC__Document
SET Content = JSON_MODIFY(Content,
        '$.DataMigrations[' + CAST(@idx AS NVARCHAR(10)) + '].Version', CAST(2 AS INT))
WHERE Type LIKE '%DataMigrationRecord%';

SELECT JSON_VALUE(m.value, '$.DataMigrationClass') AS cls, JSON_VALUE(m.value, '$.Version') AS ver
FROM HSBC__Document d CROSS APPLY OPENJSON(d.Content, '$.DataMigrations') m
WHERE d.Type LIKE '%DataMigrationRecord%';
```

The last query should show `ArchiveRoleMigrations` at version **2**.

**3. Start and sign in:**

```powershell
Start-Service HSBCArchive
```

On restart Orchard runs `UpdateFrom2Async`, which only calls provisioning — and this time the role and the user both already exist and are committed, so attaching the role should succeed. Log in as `45517160` and you should land in the admin panel.

If you still get 403, check straight away:

```sql
SELECT * FROM HSBC__UserByRoleNameIndex;
```

A `SuperAdmin` row means it worked and it's a stale cookie — sign out and back in. No row means it failed again, and then I want the foreground log, because that would tell us *why* `AddToRoleAsync` is rejecting and that's a code fix, not a deployment one.
