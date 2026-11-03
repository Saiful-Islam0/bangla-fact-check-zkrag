My `fixacl.ps1` broke it — that's my error. The `/inheritance:r` with `/T` stripped the inherited permissions from the existing files and the replacement grants didn't land on them properly, so now even **your** administrator account is denied on `tenants.json` and the data-protection key. That's why the site is down.

Recovery — save as `D:\HSBCArchive\resetacl.ps1` and run it:

```powershell
Stop-Service HSBCArchive -ErrorAction SilentlyContinue

# Reclaim ownership so the ACLs can be rewritten at all.
& takeown.exe /F D:\HSBCArchiveData /R /D Y | Out-Null

# Harden once, at the top, and let everything below inherit it.
& icacls.exe D:\HSBCArchiveData /inheritance:r /grant:r `
    "*S-1-5-20:(OI)(CI)M" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" /Q
if ($LASTEXITCODE -ne 0) { throw "icacls failed on the root with exit code $LASTEXITCODE" }

# Drop every explicit ACE below it so children simply inherit the above.
& icacls.exe "D:\HSBCArchiveData\*" /reset /T /C /Q
if ($LASTEXITCODE -ne 0) { throw "icacls reset failed with exit code $LASTEXITCODE" }

icacls D:\HSBCArchiveData
icacls D:\HSBCArchiveData\Runtime\Orchard\tenants.json

Start-Service HSBCArchive
Start-Sleep 25
Get-Service HSBCArchive | Select-Object Status, Name
```

Run with:

```powershell
powershell -ExecutionPolicy Bypass -File D:\HSBCArchive\resetacl.ps1
```

Both `icacls` outputs should show `NT AUTHORITY\NETWORK SERVICE:(M)`, Administrators and SYSTEM — the file's entries marked `(I)` for inherited.

What's different this time: permissions are set **once on the parent** and inherited downward, instead of stamped onto every file individually. That's what I should have done originally — one ACL to reason about, new files get it automatically, and nothing to go wrong per-file.

This keeps the hardening you need (no `BUILTIN\Users` write on archive data) *and* gives `NETWORK SERVICE` the access the ingest requires.

If `takeown` reports failures on some files, tell me — that would mean something else holds them and we'd handle those separately rather than forcing it.
