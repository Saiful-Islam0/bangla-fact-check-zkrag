That first attempt got far enough to create tables, so Orchard now refuses to set up over them. You need a clean slate.

**1. Stop the app**

```powershell
Stop-Service HSBCArchive
```

**2. Clear the database.** In SSMS on BDW25135476, if `BDArchive` is dedicated to this app (it is), the cleanest route:

```sql
USE master;
ALTER DATABASE BDArchive SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
DROP DATABASE BDArchive;
CREATE DATABASE BDArchive;
```

Then re-grant the login, since dropping the database drops its users:

```sql
USE BDArchive;
CREATE USER bdarchive FOR LOGIN bdarchive;
ALTER ROLE db_owner ADD MEMBER bdarchive;
```

If you'd rather not drop the database, drop just the archive's tables instead — run this and then execute the statements it produces:

```sql
USE BDArchive;
SELECT 'DROP TABLE [' + s.name + '].[' + t.name + '];'
FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
WHERE t.name LIKE 'HSBC[_]%';
```

**3. Clear the tenant state on the server**, or Orchard will still think a site exists:

```powershell
Remove-Item D:\HSBCArchiveData\Runtime\Orchard\Sites -Recurse -Force -ErrorAction SilentlyContinue
Start-Service HSBCArchive
```

**4. Redo the wizard from your laptop** in Edge or Chrome.

On the email: Orchard validates the format strictly, and the super-user email also has to differ from anything already taken. Use a plain, real-looking corporate address — if `saiful.islam@noexternalmail.hsbc.com` was rejected, that's likely the `noexternalmail` subdomain tripping its check, so use your normal address.

Nothing else needs redoing — the service, certificate, permissions and connection string all stay as they are.
