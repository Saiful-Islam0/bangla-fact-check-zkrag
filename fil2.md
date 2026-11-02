My error — the DLL was built as version 0.18.0 and so demanded `HSBC.Archive.Core 0.18.0.0`, which isn't on the server. Your config was fine all along (`UploadsEnabled: True`, `ProcessingApproved: True`, `ScanningWaived: True`).

Rebuilt against 0.17.0, matching your installed package:

```
/private/tmp/claude-501/-Users-saiful-Documents-HSBC/51324287-e87e-4df8-a3b8-e6933bbb8f16/scratchpad/HSBC.Archive.Media.dll
```

SHA-256 `97d8f5a80ab33f8da1e23f18f174a505368132e15f39b35078f0b699d7d4465a`

Copy it over and start the service — the config needs no further changes:

```powershell
Stop-Service HSBCArchive -ErrorAction SilentlyContinue
Copy-Item <new dll> D:\HSBCArchive\app\HSBC.Archive.Media.dll -Force
Get-FileHash D:\HSBCArchive\app\HSBC.Archive.Media.dll -Algorithm SHA256 | Select-Object -Expand Hash
Start-Service HSBCArchive
Start-Sleep 25
Get-Service HSBCArchive
```

The hash should read `97D8F5A80AB33F8DA1E23F18F174A505368132E15F39B35078F0B699D7D4465A`, and the service should stay `Running`.

If it stops again, run the foreground command as before — but the previous error was purely the version mismatch, so I expect it to come up this time.
