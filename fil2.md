Clear picture forming: `UserByRoleNameIndex` has only `AUTHENTICATED` and `ADMINISTRATOR` — **no SuperAdmin rows at all**. Two user documents exist (42 and 44). Let me see exactly what each is:

```sql
USE BDArchive;

SELECT JSON_VALUE(Content, '$.UserName')  AS UserName,
       JSON_QUERY(Content, '$.RoleNames') AS RoleNames,
       JSON_QUERY(Content, '$.LoginInfos') AS Logins
FROM HSBC__Document
WHERE Type LIKE '%Users.Models.User%';

SELECT JSON_VALUE(r.value, '$.RoleName') AS RoleName
FROM HSBC__Document d
CROSS APPLY OPENJSON(d.Content, '$.Roles') r
WHERE d.Type LIKE '%Roles%';

SELECT Content FROM HSBC__Document WHERE Type LIKE '%DataMigrationRecord%';
```

What I'm looking for:

1. Whether `45517160` exists as a user with a `HSBC.ActiveDirectory` login — it must, or you couldn't have logged in.
2. Whether the `SuperAdmin` and `Admin` roles were created at all.
3. The recorded migration version for `ArchiveRoleMigrations`.

The reason the third one matters: provisioning runs inside that migration, and there's a dedicated re-entry point (`UpdateFrom2Async`) that does nothing but provision. If the version reads `3`, setting it back to `2` and restarting makes Orchard re-run provisioning properly — adding the role through the real code path, so the indexes stay consistent.

I'd rather do that than hand-edit your user document. Send me those three results.
