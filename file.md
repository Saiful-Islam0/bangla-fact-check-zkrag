Check whether the service is actually running:

```powershell
Get-Service HSBCArchive
(Invoke-WebRequest https://bdw25135475:9443/health -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode
```

If it's **Stopped**, start it and watch for the reason:

```powershell
Start-Service HSBCArchive
```

If that errors, or it starts and stops again, run it in the foreground to see the real message:

```powershell
Stop-Service HSBCArchive -ErrorAction SilentlyContinue
foreach ($e in (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment) {
    $k, $v = $e -split '=', 2
    Set-Item -Path "Env:$k" -Value $v
}
cd D:\HSBCArchive\app
.\HSBC.Archive.Web.exe
```

Two likely causes, both from the edits just made:

- **The JSON got malformed or lost a required value.** `UatDeployment.Validate` throws at startup if `DataRoot`, `StorageRoot`, `AllowedHosts` or the connection string are missing or invalid, and the service dies immediately. Check it still looks right:

  ```powershell
  Get-Content D:\HSBCArchive\app\appsettings.UAT.json -Raw | ConvertFrom-Json | ConvertTo-Json -Depth 24
  ```

- **The database user wasn't recreated properly**, so the app can't connect at startup.

Send me what the foreground run prints — the first `Error` or `Exception` line is the answer.
