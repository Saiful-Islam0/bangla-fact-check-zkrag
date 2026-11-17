Analyzed build-uat-package.sh:L1-44
Analyzed RELEASE-NOTES.md:L1-100
Ran list release artifacts directory
Created check_css_history.py
Ran inspect user messages in Claude sessions
Created check_nov7.py
Ran inspect Nov 7 CSS edits in Claude session
Created dump_pre_nov7.py
Ran read pre-Nov 7 CSS from Claude session
Created dump_home_css.py
Ran extract original premium home.css from Claude session
Analyzed output.txt:L45-210
Edited home.css
Edited home.css
Edited components.css
Ran build Release and publish win-x64 hotfix DLLs · Exited with code 1

I found the exact root cause of the missing CSS/animations as well (an earlier Nov 7 session had overwritten `home.css` and `components.css` with a "flat editorial pass" that removed `--archive-grad`, the hero drifting glow, the breathing radial rings, and the red gradient hover on Explore tiles and page intros).

I have:
1. Updated `HSBC.Archive.Admin` (`ArchiveWindowsProfile.cs`) to query Active Directory (`UserPrincipal.FindByIdentity`) for the employee's full display name (cached for 30 minutes) alongside their User ID (`sAMAccountName`).
2. Updated `HSBC.Archive.Theme` (`Layout.cshtml`, `archive.js`, `components.css`, `home.css`, `bn.po`, and bumped resource version to `0.13.0`) so that:
   - The navbar shows a clean circular **profile icon button** that opens a popover card on click with **Name**, **User ID**, and (for Admins/Super Admins) the **Open the admin panel** button.
   - The navbar search is a compact **search icon button** that smoothly expands into the search bar when clicked (or when `/` is pressed) and collapses on close/Escape.
   - All of the missing animations, hero drifting glow, breathing rings, and red gradient hover effects are restored.

I am compiling and publishing the updated `win-x64` DLLs right now—I will share the exact DLL paths and drop-in instructions as soon as the build task completes in a few seconds.

Analyzed task-158.log:L1-34
Ran publish win-x64 hotfix DLLs · Exited with code 1
Ran stage updated DLLs and localization into artifacts/hotfix-dlls
Ran verify embedded resources in hotfix DLLs
Ran check wwwroot structure in published IIS artifact
Ran find PO localization files in published IIS artifact
Ran find all PO files in release artifact
Analyzed HSBC.Archive.Web.csproj:L1-26
Analyzed HSBC.Archive.Theme.csproj:L1-9
Analyzed Directory.Build.props:L1-8
Analyzed Directory.Build.props:L1-15
Ran publish win-x64 0.19.0-uat.1 DLLs for IIS drop-in

The updated `win-x64` (`0.19.0-uat.1`) DLLs are built and ready in [`artifacts/hotfix-dlls/`](file:///Users/saiful/Documents/HSBC/artifacts/hotfix-dlls):

### 1. Files to Copy to the Server
Only **two DLLs** (plus the Bangla `.po` file if you use Bangla on the frontend) changed:
1. **[HSBC.Archive.Theme.dll](file:///Users/saiful/Documents/HSBC/artifacts/hotfix-dlls/HSBC.Archive.Theme.dll)** (`138 KB`) — contains:
   - The circular **profile icon button** in the navbar that opens a popover card on click showing **Name**, **User ID**, and (for Admins/Super Admins) the **Open the admin panel** button.
   - The compact **search icon button** in the navbar that expands into the search bar when clicked (or when `/` is pressed) and collapses on close/Escape.
   - All of the restored **animations & CSS** (`--archive-grad`, hero drifting red glow, breathing radial rings, red gradient hover on Explore tiles, gradient stacked page-intro banners, and radial footer/dark-band washes), with cache-busted resource version `0.13.0`.
2. **[HSBC.Archive.Admin.dll](file:///Users/saiful/Documents/HSBC/artifacts/hotfix-dlls/HSBC.Archive.Admin.dll)** (`1.4 MB`) — contains the updated [ArchiveWindowsProfile.cs](file:///Users/saiful/Documents/HSBC/src/Modules/HSBC.Archive.Admin/Security/Ad/ArchiveWindowsProfile.cs) that queries Active Directory (`UserPrincipal.FindByIdentity`) for the employee's full display name (cached for 30 minutes) alongside their Employee/User ID (`sAMAccountName`).
3. *(Optional, for Bangla labels)* **[HSBC.Archive.Theme.po](file:///Users/saiful/Documents/HSBC/artifacts/hotfix-dlls/Localization/bn/HSBC.Archive.Theme.po)** → goes into `<app>\Localization\bn\HSBC.Archive.Theme.po`.

---

### 2. How to Replace Them on the IIS Server

Because the `app` folder is locked to Read/Execute for the pool identity and `w3wp.exe` holds the DLLs while running, run this in an **elevated PowerShell** session on the server after copying the two DLLs onto the server (for example into `C:\Temp\hotfix`):

```powershell
Import-Module WebAdministration
$app = (Get-Website -Name HSBCArchive).physicalPath

# 1. Stop the app pool so w3wp.exe releases the DLLs
Stop-WebAppPool -Name HSBCArchive

# 2. Copy the two updated DLLs into the IIS app directory
Copy-Item "C:\Temp\hotfix\HSBC.Archive.Theme.dll" -Destination "$app\HSBC.Archive.Theme.dll" -Force
Copy-Item "C:\Temp\hotfix\HSBC.Archive.Admin.dll" -Destination "$app\HSBC.Archive.Admin.dll" -Force

# 3. Ensure the pool identity and IIS_IUSRS have Read/Execute on the replaced files
icacls "$app\HSBC.Archive.Theme.dll" /grant "IIS AppPool\HSBCArchive:RX" "BUILTIN\IIS_IUSRS:RX"
icacls "$app\HSBC.Archive.Admin.dll" /grant "IIS AppPool\HSBCArchive:RX" "BUILTIN\IIS_IUSRS:RX"

# 4. Start the app pool back up
Start-WebAppPool -Name HSBCArchive
```

Reload the page in your browser (`Ctrl+F5`) and you'll immediately see the restored animations/gradients, the compact expandable search icon, and the clickable AD profile icon with the details popover.
