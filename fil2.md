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





385/385 passing, format and audit clean. Uploads are ready to enable.

## The file to copy

```
/private/tmp/claude-501/-Users-saiful-Documents-HSBC/51324287-e87e-4df8-a3b8-e6933bbb8f16/scratchpad/HSBC.Archive.Media.dll
```

96 KB, SHA-256 `69503d550b1af172e65ddcc3675c653302afc42d5c43a6cb1b71f28aafb918da`. Only this module changed — nothing else in the 120 MB package needs moving.

Verify after transfer, on the server:

```powershell
Get-FileHash <path to the copied dll> -Algorithm SHA256 | Select-Object -Expand Hash
```

## Apply it

```powershell
Stop-Service HSBCArchive
Copy-Item D:\HSBCArchive\app\HSBC.Archive.Media.dll D:\HSBCArchive\app\HSBC.Archive.Media.dll.bak -Force
Copy-Item <new dll> D:\HSBCArchive\app\HSBC.Archive.Media.dll -Force

$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$m = $j.OrchardCore.Default.HSBCArchive.Media
$m | Add-Member -NotePropertyName Scanner -NotePropertyValue ([pscustomobject]@{ ScanningWaived = $true }) -Force
$m.ProcessingApproved = $true
$m.UploadsEnabled = $true
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8

Start-Service HSBCArchive
Start-Sleep 25
Get-Service HSBCArchive
```

All three settings must go together — `UploadsEnabled` on its own still fails startup validation. If the service doesn't come back, restore the `.bak` DLL and restart; nothing else was touched.

Then reload the media page. **Save media** should be active, and the "uploads are disabled by deployment policy" banner gone.

Two more flags once uploads work, if your review needs them — both default off and neither affects uploading, only what gets *served*:

- `DocumentDisplayApproved: true` — serve PDFs in the viewer
- `VideoDisplayApproved: true` — serve MP4s

Images are served as soon as `ProcessingApproved` is on.

---

**What I didn't verify:** the waiver and the scanner adapter have never run on Windows — 385 tests pass on macOS, including the waiver path, but image/PDF/video processing on the real server is still unproven, so expect the first upload of each type to be the actual test. If a 250 MB video upload fails, tell me whether it failed at upload or at processing; those are different problems.

**On the record for the handover:** media uploads are now accepted **unscanned**. The archive logs event 2122 at every start saying so. That is a security control you chose to waive for an internal UAT, and it should be re-examined before this holds real content long-term — the exposure isn't outsiders, it's an infected file from a staff machine becoming permanent storage that others download. The hook is in place; it's one config line to turn on a real scanner later.
