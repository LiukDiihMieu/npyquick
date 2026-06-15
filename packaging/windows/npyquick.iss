; Inno Setup script for the npyquick Windows installer.
; Compile with the Inno Setup compiler, passing the version:
;     ISCC /DMyAppVersion=0.1.1 packaging\windows\npyquick.iss
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
#define IconPath SourcePath + "npyquick.ico"

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

[Files]
; The PyInstaller onedir tree (npyquick.exe + _internal\...).
Source: "..\..\dist\npyquick\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; Shortcuts inherit the icon embedded in the .exe by PyInstaller.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
