404 at root means the app thinks the site is already set up — so the wizard isn't being served. The tenant state file probably survived, or was rewritten.

```powershell
Get-ChildItem D:\HSBCArchiveData\Runtime\Orchard -Recurse | Select-Object FullName
Get-Content D:\HSBCArchiveData\Runtime\Orchard\Sites\Default\appsettings.json -ErrorAction SilentlyContinue
```

If that file exists and shows `"State": "Running"`, that's it — Orchard is loading a tenant whose database you emptied. Clear it properly, with the service stopped so nothing rewrites it:

```powershell
Stop-Service HSBCArchive
Remove-Item D:\HSBCArchiveData\Runtime\Orchard\Sites -Recurse -Force
Get-ChildItem D:\HSBCArchiveData\Runtime\Orchard
Start-Service HSBCArchive
Start-Sleep 25
(Invoke-WebRequest https://bdw25135475:9443/ -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode
```

The `Get-ChildItem` in the middle should show no `Sites` folder. Then the root should serve the setup wizard again.

If the file says `"State": "Uninitialized"` instead, or the folder is already gone, tell me — then the 404 is coming from somewhere else and I'll want the foreground log again with the request you make.
