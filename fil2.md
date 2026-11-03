That's it, and the `icacls` output shows exactly why:

```
D:\HSBCArchiveData\Drop  BUILTIN\Administrators:(F)
                         NT AUTHORITY\SYSTEM:(OI)(CI)(F)
                         BUILTIN\Administrators:(OI)(CI)(F)
                         BDW25135475\rmsff01:(OI)(CI)(F)
```

**No `NETWORK SERVICE` entry at all.** My `patch.ps1` removed inheritance and then its grant didn't apply — and I piped the result to `Out-Null` without checking the exit code, so it failed silently. My mistake; the same script checked exit codes everywhere else.

It also explains why `Media` and `Runtime` work: look at their `(I)` flags — they're inherited from the drive root, including `BUILTIN\Users:(AD)(WD)`, and `NETWORK SERVICE` is a member of `Users`. Those folders lost their hardening when the teardown deleted `D:\HSBCArchiveData` and the app recreated them.

Save as `D:\HSBCArchive\fixacl.ps1` and run it:

```powershell
$svc = '*S-1-5-20'          # NT AUTHORITY\NETWORK SERVICE
$adm = '*S-1-5-32-544'      # BUILTIN\Administrators
$sys = '*S-1-5-18'          # NT AUTHORITY\SYSTEM

Stop-Service HSBCArchive

foreach ($path in 'D:\HSBCArchiveData\Runtime', 'D:\HSBCArchiveData\Media', 'D:\HSBCArchiveData\Drop') {
    & icacls.exe $path /inheritance:r /grant:r "${svc}:(OI)(CI)M" "${adm}:(OI)(CI)F" "${sys}:(OI)(CI)F" /T /Q
    if ($LASTEXITCODE -ne 0) { throw "icacls failed on $path with exit code $LASTEXITCODE" }
    Write-Host "Secured $path" -ForegroundColor Green
}

Start-Service HSBCArchive
Start-Sleep 20
Get-Service HSBCArchive | Select-Object Status, Name
icacls D:\HSBCArchiveData\Drop
```

I'm using well-known SIDs rather than names — `*S-1-5-20` can't fail on account-name resolution, which is the likely reason the original grant didn't stick. `/T` applies to the photo already sitting in the folder, and this time a failure throws instead of being swallowed.

The last line should now show `NT AUTHORITY\NETWORK SERVICE:(OI)(CI)(M)`.

Then check the service is back on the right identity before testing:

```powershell
(Get-CimInstance Win32_Service -Filter "Name='HSBCArchive'").StartName
```

Must read `NT AUTHORITY\NETWORK SERVICE`, not `LocalSystem`. Your revert command looked like it succeeded, but confirm — leaving it on LocalSystem is the one outcome here worth avoiding.

Then try the ingest again.

Worth knowing: this also re-hardens `Runtime` and `Media`, which currently allow **any local user** to write to them via `BUILTIN\Users`. That's wider than intended for archive storage and media, and it's been that way since the teardown — so this fixes a real exposure as well as your ingest.
