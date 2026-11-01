Good call. Let's read the actual error.

```powershell
Get-Service HSBCArchive
```

If the service is gone (you may have run the teardown), say so and we'll go to the script. Otherwise:

```powershell
Stop-Service HSBCArchive
foreach ($e in (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment) {
    $k, $v = $e -split '=', 2
    Set-Item -Path "Env:$k" -Value $v
}
cd D:\HSBCArchive\app
.\HSBC.Archive.Web.exe 2>&1 | Tee-Object D:\HSBCArchive\error.log
```

Leave that window running. From your laptop, load the site, then load `/Admin`. Both should fail. Then Ctrl+C in the window and:

```powershell
Start-Service HSBCArchive
Select-String -Path D:\HSBCArchive\error.log -Pattern '"LogLevel":"(Error|Critical)"' |
  Select-Object -First 3 | ForEach-Object { $_.Line }
```

I want the **first** one, not the last — the later errors are usually consequences of it. If that returns nothing, run it again with `Warning` added to the pattern and send me the last ten lines instead.
