#define MyAppName "TerraSatch Edge"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "TerraSatch"
#define MyAppExeName "TerraSatchEdge.exe"

[Setup]
AppId={{D2B4DE64-C048-44C0-B681-54E6518F5B7A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TerraSatch\Edge
DefaultGroupName=TerraSatch
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=TerraSatch-Edge-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Edge\{#MyAppExeName}

[Dirs]
Name: "{commonappdata}\TerraSatch\Edge"; Permissions: admins-full system-full users-modify
Name: "{commonappdata}\TerraSatch\Edge\state"; Permissions: admins-full system-full users-modify
Name: "{commonappdata}\TerraSatch\Edge\state\logs"; Permissions: admins-full system-full users-modify

[Files]
Source: "..\..\dist\TerraSatchEdge\*"; DestDir: "{app}\Edge"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\windows\vendor\TerraSatchEdgeService.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\windows\TerraSatchEdgeService.xml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\windows\TerraSatchEdgeSetup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\windows\TerraSatchEdgeConsole.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\TerraSatch Edge Status"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeConsole.ps1"" -Command status"
Name: "{group}\TerraSatch Edge Diagnostics"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeConsole.ps1"" -Command doctor"
Name: "{group}\TerraSatch Edge Hardware Scan"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeConsole.ps1"" -Command scan"
Name: "{group}\TerraSatch Edge Setup"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeSetup.ps1"""
Name: "{commondesktop}\TerraSatch Edge"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeConsole.ps1"" -Command status"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\TerraSatchEdgeService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing TerraSatch Edge service..."
Filename: "{app}\TerraSatchEdgeService.exe"; Parameters: "start"; Flags: runhidden waituntilterminated; StatusMsg: "Starting TerraSatch Edge service..."
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeSetup.ps1"""; Description: "Pair and configure TerraSatch Edge"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\TerraSatchEdgeService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopTerraSatchEdge"
Filename: "{app}\TerraSatchEdgeService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveTerraSatchEdge"
