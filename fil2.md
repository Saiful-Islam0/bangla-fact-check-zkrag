Neither, exactly. You can't add source files on the server — there's no source tree and no SDK there, and the Razor views are compiled **into** the module DLLs (there's no separate views assembly). So a `.cshtml` dropped on the server would be ignored.

But you don't need a full redeploy either. Same as the media fix: I build here, you copy the changed DLLs and restart. For this feature that's two files:

- `HSBC.Archive.Admin.dll` — the screen, the controller, the thumbnail endpoint
- `HSBC.Archive.Media.dll` — the ingest service and the drop-folder settings

Plus three lines added to `appsettings.UAT.json` and a folder you create. Maybe two minutes of downtime.

**One thing I need first**, because it bit us last time — confirm the installed version so I build the DLLs to bind against it:

```powershell
(Get-Item D:\HSBCArchive\app\HSBC.Archive.Core.dll).VersionInfo |
  Select-Object FileVersion, ProductVersion
Get-Content D:\HSBCArchive\release-manifest.txt -ErrorAction SilentlyContinue | Select-String -Pattern 'Version|Hosting'
```

My notes say `0.17.0-uat.1` for the self-contained service, but they also claim you've moved to IIS, which you haven't — so I'd rather read it off the server than trust them.

Send me that and I'll build it: thumbnails, pick-and-choose (not automatic), title from filename, ingested files moved to `_done`, 50 per run, optional event attachment for the batch.
