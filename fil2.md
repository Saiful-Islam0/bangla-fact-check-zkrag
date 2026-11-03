The filter redacts the message by design, so I need the SQL itself. YesSql logs each command before running it — turn that on and the last statement before the error is the culprit:

```powershell
Stop-Service HSBCArchive
foreach ($e in (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment) {
    $k, $v = $e -split '=', 2
    Set-Item -Path "Env:$k" -Value $v
}
$env:Logging__LogLevel__YesSql = 'Debug'
cd D:\HSBCArchive\app
.\HSBC.Archive.Web.exe 2>&1 | Tee-Object D:\HSBCArchive\search2.log
```

Do **one** search, then Ctrl+C and:

```powershell
Start-Service HSBCArchive
$i = (Select-String -Path D:\HSBCArchive\search2.log -Pattern 'ViewerExceptionFilter' | Select-Object -First 1).LineNumber
Get-Content D:\HSBCArchive\search2.log | Select-Object -Skip ([Math]::Max(0, $i - 6)) -First 6 |
  Out-File D:\HSBCArchive\search-sql.txt
Get-Content D:\HSBCArchive\search-sql.txt
```

That prints the few statements immediately before the failure. Send me those, and **tell me exactly what you typed in the search box** — whether it was English, Bangla, or contained punctuation changes which code path runs.

Where I think this is heading, from reading the query: the search runs five ranked passes over `ArchiveAdminIndex`, and the body match uses `BodyNormalized`, which the schema declares as `Unlimited()` ([ArchiveSchema.cs:234](src/Modules/HSBC.Archive.Core/Persistence/ArchiveSchema.cs#L234)). On SQLite that's just text; on SQL Server an unlimited column has real restrictions about where it can appear — it can be `LIKE`'d but not compared, sorted or de-duplicated. If YesSql emits a `DISTINCT` or a comparison involving that column, SQL Server rejects the statement outright while SQLite runs it happily. That would be the same category of defect as the `IdentityColumnSize` one: invisible to a SQLite-only test suite.

I'd rather confirm that from the actual SQL than fix what I guessed, so send the log lines.
