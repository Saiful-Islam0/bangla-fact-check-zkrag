The schema built completely — all 30 tables including `HSBC__UserIndex` and the story/import/insights indexes. **The `IdentityColumnSize: Int64` fix worked.** The table name is `HSBC__Document` with a double underscore (prefix + separator), which is why my earlier query failed.

Now the roles:

```sql
USE BDArchive;
SELECT * FROM HSBC__UserByRoleNameIndex;
SELECT Id, Type, Content FROM HSBC__Document WHERE Type LIKE '%Users.Models.User%';
```

- `HSBC__UserByRoleNameIndex` should have a row with `RoleName = SuperAdmin` for your account. If it's empty, the role was never attached.
- In the `Content` JSON, look for `"UserName"`, `"RoleNames"` and `"LoginInfos"`. I expect `UserName` to be `45517160` with a `HSBC.ActiveDirectory` login entry and an **empty** `RoleNames`.

Also check the roles themselves exist:

```sql
SELECT Content FROM HSBC__Document WHERE Type LIKE '%Roles%';
```

Paste those and I'll tell you whether to re-run provisioning or just grant the role directly. Don't edit the JSON by hand yet — Orchard caches documents, and a manual edit done the wrong way is harder to undo than a clean re-provision.
