That message is the viewer's generic 500 page ([Error.cshtml:3](src/Modules/HSBC.Archive.Frontend/Views/Archive/Error.cshtml#L3)) — so search is throwing, and the real exception is hidden behind it. Same drill as the migration bug:

```powershell
Stop-Service HSBCArchive
foreach ($e in (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment) {
    $k, $v = $e -split '=', 2
    Set-Item -Path "Env:$k" -Value $v
}
cd D:\HSBCArchive\app
.\HSBC.Archive.Web.exe 2>&1 | Tee-Object D:\HSBCArchive\search.log
```

Leave it running, do a search from your laptop browser, then Ctrl+C and:

```powershell
Start-Service HSBCArchive
Select-String -Path D:\HSBCArchive\search.log -Pattern '"LogLevel":"(Error|Critical)"' |
  Select-Object -First 2 | ForEach-Object { $_.Line }
```

Send me the **first** error line.

My guess, for what it's worth: another SQL Server difference, like the `IdentityColumnSize` one. The build verifies against SQLite, so a query that relies on SQLite behaviour — collation, a LIKE pattern, or a type coercion — passes every test here and fails on SQL Server. That's the same gap that produced the schema bug, and it's why SQL Server acceptance being "not executed" matters.

If the log shows nothing at `Error` level, re-run the Select-String with `Warning` included and send the last twenty lines instead — and tell me what you typed in the search box, since a specific character (an apostrophe, a `%`, Bangla text) would point somewhere quite different.
