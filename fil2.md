Stock Orchard configuration, no custom YesSql setup — so I need the actual column types rather than theory. In SSMS against `BDArchive`:

```sql
SELECT t.name AS table_name, c.name AS column_name, ty.name AS data_type
FROM sys.tables t
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE (t.name = 'HSBC_Document' AND c.name = 'Id')
   OR c.name = 'DocumentId'
ORDER BY t.name;
```

That shows whether `HSBC_Document.Id` is `int` or `bigint`, and what the index tables used. One side will differ, and that difference is the whole bug.

Also tell me:

```sql
SELECT name, collation_name, compatibility_level FROM sys.databases WHERE name = 'BDArchive';
```

My suspicion is that the database was created with a compatibility level or setting that makes YesSql pick a different identity column size than the one it uses for index tables — but I'd rather see it than assert it.

Worth saying plainly: this is the gap the release notes flagged. The package was verified against SQLite in the build, and SQL Server acceptance was recorded as "not executed". This is exactly the class of defect that gap was hiding, and it would have blocked UAT whichever way you deployed — IIS or service.
