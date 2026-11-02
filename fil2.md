Service starts then stops — and I can see the paste got mangled (several of my lines ran together, e.g. `$m = $j.OrchardCore.Default.HSBCArchive.MediaLiteralPath $p -Encoding UTF8`). So the config may be half-written.

First check what's actually in the file:

```powershell
cd D:\HSBCArchive
$j = Get-Content -LiteralPath D:\HSBCArchive\app\appsettings.UAT.json -Raw | ConvertFrom-Json
$j.OrchardCore.Default.HSBCArchive.Media | Format-List UploadsEnabled, ProcessingApproved, Scanner
```

If that errors, the JSON is broken and that alone explains the crash.

Then get the real reason:

```powershell
foreach ($e in (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment) {
    $k, $v = $e -split '=', 2
    Set-Item -Path "Env:$k" -Value $v
}
cd D:\HSBCArchive\app
.\HSBC.Archive.Web.exe
```

Send me the first `Error` or unhandled-exception line. I expect one of:

- **"Media uploads enabled without processing approval and a production-ready scanner"** — `ProcessingApproved` or the `Scanner` block didn't get written.
- **A JSON parse error** — the file is malformed from the mangled paste.
- **A type load error in HSBC.Archive.Media** — the DLL copy didn't land properly.

To rule out the last one:

```powershell
Get-FileHash D:\HSBCArchive\app\HSBC.Archive.Media.dll -Algorithm SHA256 | Select-Object -Expand Hash
```

That must be `69503D550B1AF172E65DDCC3675C653302AFC42D5C43A6CB1B71F28AAFB918DA`.

Paste the multi-line blocks into the PowerShell window one line at a time, or save them as a `.ps1` and run that — the console is clearly merging lines when a whole block arrives at once.
