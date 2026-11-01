Then it isn't that branch. The gap is that your foreground run never captured the Finish click — the log only shows page loads, then shutdown.

Run it again with debug logging turned up, which makes the two silent rejectors (host filtering and antiforgery) print:

```powershell
Stop-Service HSBCArchive
foreach ($e in (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment) {
    $k, $v = $e -split '=', 2
    Set-Item -Path "Env:$k" -Value $v
}
$env:Logging__LogLevel__Default = 'Debug'
$env:Logging__LogLevel__Microsoft_AspNetCore = 'Debug'
cd D:\HSBCArchive\app
.\HSBC.Archive.Web.exe 2>&1 | Tee-Object D:\HSBCArchive\foreground.log
```

Now go to the browser, load the setup page fresh, fill it in and **click Finish**. Then Ctrl+C and:

```powershell
Start-Service HSBCArchive
Select-String -Path D:\HSBCArchive\foreground.log -Pattern 'Antiforgery|HostFiltering|Host header|400|Exception|Error|Warning' |
  Select-Object -Last 40 | ForEach-Object { $_.Line }
```

Send me that. My best guess now is host filtering — it rejects with a bare 400 and logs only at Debug, which is exactly the silence we're seeing — but the POST may be going out under a host that the GET didn't, and I'd rather see it than keep narrowing by elimination.
