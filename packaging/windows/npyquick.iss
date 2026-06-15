; Inno Setup script for the npyquick Windows installer.
; Compile with the Inno Setup compiler, passing the version:
;     ISCC /DMyAppVersion=0.1.2 packaging\windows\npyquick.iss
; packaging\windows\build.ps1 reads the version from the installed package and
; passes it automatically. The payload is the PyInstaller onedir output in
; dist\npyquick\, so run PyInstaller before compiling this script.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "npyquick"
#define MyAppPublisher "LiukDiihMieu"
#define MyAppURL "https://github.com/LiukDiihMieu/npyquick"
#define MyAppExeName "npyquick.exe"
#define IconPath AddBackslash(SourcePath) + "npyquick.ico"

[Setup]
; A fixed AppId ties upgrades/uninstall to the same app across versions.
AppId={{E895C2DB-D59E-43C8-A61C-ACDE838D932C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
; Per-user install — no administrator rights required.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Refresh the shell's file associations after install AND uninstall (official
; SHCNE_ASSOCCHANGED mechanism), so the .npy/.npz association applies without
; a re-login.
ChangesAssociations=yes
; Show the GPL on a license page during setup.
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=npyquick-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
#if FileExists(IconPath)
SetupIconFile={#IconPath}
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
; Opt-in (default off): never change file associations unless the user asks.
Name: "associate"; Description: "Associate .npy and .npz files with {#MyAppName}"; Flags: unchecked

[Files]
; The PyInstaller onedir tree (npyquick.exe + _internal\...).
Source: "..\..\dist\npyquick\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Ship the GPL text alongside the installed app.
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
; Shortcuts inherit the icon embedded in the .exe by PyInstaller.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; File association, only when the "associate" task is checked. HKCU-only
; (per-user, no admin, cannot affect other users or the system). Our own
; ProgIDs are removed wholesale on uninstall (uninsdeletekey); for the
; extension keys we delete only the value we wrote (uninsdeletevalue), never
; the whole .npy/.npz key, so any other app's entries there survive.
Root: HKCU; Subkey: "Software\Classes\npyquick.npy"; ValueType: string; ValueName: ""; ValueData: "NumPy array"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\npyquick.npy\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\npyquick.npy\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\npyquick.npz"; ValueType: string; ValueName: ""; ValueData: "NumPy compressed archive"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\npyquick.npz\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\npyquick.npz\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.npy"; ValueType: string; ValueName: ""; ValueData: "npyquick.npy"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.npz"; ValueType: string; ValueName: ""; ValueData: "npyquick.npz"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.npy\OpenWithProgids"; ValueType: string; ValueName: "npyquick.npy"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.npz\OpenWithProgids"; ValueType: string; ValueName: "npyquick.npz"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
