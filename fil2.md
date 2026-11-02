Then I'm looking in the wrong place. List what actually exists — make sure the query window is on **BDArchive**:

```sql
USE BDArchive;
SELECT name FROM sys.tables ORDER BY name;
```

Two possibilities that changes between:

- **Tables with a different prefix** (or none) — the wizard may have been given a different table prefix than `HSBC_`, in which case the document table is `Document` or something else, and I'll adjust the queries.
- **No tables at all** — then setup wrote to a different database than the one you're looking at, and the connection string in the service registry is pointing elsewhere. Check with:

  ```powershell
  (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment |
    Where-Object { $_ -like 'OrchardCore*' } | ForEach-Object { ($_ -split 'Password=')[0] }
  ```

  That prints the connection string with the password cut off, so you can see the server and database it really uses.

The empty event log isn't surprising — nothing has been written to that source all session, so it isn't a reliable signal here. The table list is the useful one.
