Built and documented; full verification re-running now. Here's what you'll do on the server once it's green.

**The config you'll use** — no scanner, explicit waiver:

```json
"Scanner": { "ScanningWaived": true }
```

I did it as a waiver rather than deleting the check, for three reasons: the deployment still refuses uploads if someone forgets to make the decision, it logs a warning (event 2122) at every start so the choice is visible in the audit trail rather than invisible in a diff, and it's one line to reverse if a scanner is ever required. It's also rejected if combined with a scanner command, so the two can't silently disagree.

You'll copy one DLL (`HSBC.Archive.Media.dll`, ~98 KB — not the whole package), add three settings, and restart:

```powershell
Stop-Service HSBCArchive
Copy-Item D:\HSBCArchive\app\HSBC.Archive.Media.dll D:\HSBCArchive\app\HSBC.Archive.Media.dll.bak
# copy the new DLL over D:\HSBCArchive\app\HSBC.Archive.Media.dll
$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$m = $j.OrchardCore.Default.HSBCArchive.Media
$m | Add-Member -NotePropertyName Scanner -NotePropertyValue ([pscustomobject]@{ ScanningWaived = $true }) -Force
$m.ProcessingApproved = $true
$m.UploadsEnabled = $true
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8
Start-Service HSBCArchive
```

All three settings are needed together — `UploadsEnabled` alone still fails startup validation, which is the trap from earlier.

I'll give you the exact DLL path and its checksum when the gate finishes.
