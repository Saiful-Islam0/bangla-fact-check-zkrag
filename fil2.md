You're right, and that was my error — I told you to look for `StorageRoot` in the IIS environment variables, but the installer only puts the **connection string** there. The paths go in `appsettings.UAT.json`. I'd only checked where the connection string went before telling you.

So: the file you found is the right place. Two things to establish.

## 1. What is it currently set to?

Find the app folder, then read the value:

```powershell
Import-Module WebAdministration
$app = (Get-Website -Name HSBCArchive).physicalPath
$app
(Get-Content "$app\appsettings.UAT.json" -Raw | ConvertFrom-Json).OrchardCore.Default.HSBCArchive.Media.StorageRoot
```

Or just open `appsettings.UAT.json` in Notepad and look — it's a small file.

## 2. Where are the images actually?

This is the one that matters. Run exactly this:

```powershell
Get-ChildItem "D:\HSBCArchiveData\Media" -Recurse -Directory |
  Select-Object FullName, @{n='Files';e={ (Get-ChildItem $_.FullName -File -ErrorAction SilentlyContinue | Measure-Object).Count }}
```

Or simply open `D:\HSBCArchiveData\Media` in File Explorer and look at the folder structure.

## What the answer means

- Images in **`D:\HSBCArchiveData\Media\Default\<subfolders>`** → set `StorageRoot` to **`D:\HSBCArchiveData\Media`**
- Images in **`D:\HSBCArchiveData\Media\Default\Default\...`** → set it to **`D:\HSBCArchiveData\Media\Default`**

The rule is simply: **`StorageRoot` is the folder whose child is named `Default`** — because the app appends `Default` itself.

My earlier scan command probably returned nothing because it searched all of `D:\` and hit permission errors, or the images aren't where I assumed. The two commands above only look where we know things are.

Paste what either one prints and I'll tell you the exact value to set. Then it's: edit the file, `icacls` for the pool identity on the real folder, `Restart-WebAppPool -Name HSBCArchive`.
