The per-file loop catches everything, so this is an exception escaping before or after it — and the filter logs only the type name under event 2202. That type will tell us where:

```powershell
Stop-Service HSBCArchive
foreach ($e in (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment) {
    $k, $v = $e -split '=', 2
    Set-Item -Path "Env:$k" -Value $v
}
cd D:\HSBCArchive\app
.\HSBC.Archive.Web.exe 2>&1 | Tee-Object D:\HSBCArchive\ingest.log
```

Reproduce the ingest from your laptop, Ctrl+C, then:

```powershell
Start-Service HSBCArchive
Select-String -Path D:\HSBCArchive\ingest.log -Pattern '"LogLevel":"(Error|Critical)"' |
  ForEach-Object { $_.Line } | Select-Object -Last 3
```

Send me that. The message will read `Archive administration request failed: <TypeName>.` — the type name alone narrows it sharply:

- `ArchiveValidationException` → something rejected the batch before the per-file loop
- `UnauthorizedAccessException` or `IOException` → the service account can't read the drop folder or move the file out of it
- `ArchiveConcurrencyException` → the import batch bookkeeping disagreed
- anything else → I'll trace it from there

Also tell me: **what's the filename**, and did you fill in the **Title (English)** field? And confirm the photo is a `.jpg`/`.jpeg`/`.png`/`.webp` — if the thumbnail rendered on the page, the file is readable, which already rules out the permissions answer.
