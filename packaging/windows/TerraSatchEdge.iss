#define MyAppName "TerraSatch Edge"
#ifndef MyAppVersion
  #define MyAppVersion "0.2.2"
#endif
#define MyAppPublisher "TerraSatch"
#define MyAppExeName "TerraSatchEdge.exe"
#define MyIconFile "assets\TerraSatchEdge.ico"

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
SetupIconFile={#MyIconFile}
UninstallDisplayIcon={app}\TerraSatchEdge.ico
CloseApplications=yes
RestartApplications=no

[Dirs]
Name: "{commonappdata}\TerraSatch\Edge"; Permissions: admins-full system-full users-modify
Name: "{commonappdata}\TerraSatch\Edge\state"; Permissions: admins-full system-full users-modify
Name: "{commonappdata}\TerraSatch\Edge\state\logs"; Permissions: admins-full system-full users-modify

[Files]
Source: "..\..\dist\TerraSatchEdge\*"; DestDir: "{app}\Edge"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\windows\vendor\TerraSatchEdgeService.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\windows\TerraSatchEdgeService.xml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\windows\TerraSatchEdgeServiceSetup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\windows\TerraSatchEdgeSetup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\windows\TerraSatchEdgeConsole.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyIconFile}"; DestDir: "{app}"; DestName: "TerraSatchEdge.ico"; Flags: ignoreversion

[Icons]
Name: "{group}\TerraSatch Edge Status"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeConsole.ps1"" -Command status"; IconFilename: "{app}\TerraSatchEdge.ico"
Name: "{group}\TerraSatch Edge Diagnostics"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeConsole.ps1"" -Command doctor"; IconFilename: "{app}\TerraSatchEdge.ico"
Name: "{group}\TerraSatch Edge Hardware Scan"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeConsole.ps1"" -Command scan"; IconFilename: "{app}\TerraSatchEdge.ico"
Name: "{group}\TerraSatch Edge Setup"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeSetup.ps1"""; IconFilename: "{app}\TerraSatchEdge.ico"
Name: "{commondesktop}\TerraSatch Edge"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeConsole.ps1"" -Command status"; IconFilename: "{app}\TerraSatchEdge.ico"

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeServiceSetup.ps1"""; Flags: runhidden waituntilterminated; StatusMsg: "Installing or updating TerraSatch Edge service..."
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\TerraSatchEdgeSetup.ps1"""; Description: "Verify or pair TerraSatch Edge"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\TerraSatchEdgeService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopTerraSatchEdge"
Filename: "{app}\TerraSatchEdgeService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveTerraSatchEdge"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  WrapperPath: String;
  EdgeExePath: String;
begin
  Result := '';
  NeedsRestart := False;

  { Stop the currently installed service before [Files] attempts to replace
    TerraSatchEdge.exe. The post-copy service setup script will refresh and
    restart the service using the newly installed files. }
  WrapperPath := ExpandConstant('{app}\TerraSatchEdgeService.exe');
  if FileExists(WrapperPath) then
  begin
    Log('Stopping existing TerraSatch Edge service before upgrade.');
    Exec(WrapperPath, 'stop', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end
  else
  begin
    { Fallback for an older/partial installation where the wrapper path is
      missing but the Windows service registration still exists. }
    Exec(ExpandConstant('{sys}\sc.exe'), 'stop TerraSatchEdge', '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode);
  end;

  Sleep(1000);

  { Also close any interactive status/setup process using the same executable.
    This prevents an open console from retaining a file lock during upgrade. }
  EdgeExePath := ExpandConstant('{app}\Edge\TerraSatchEdge.exe');
  if FileExists(EdgeExePath) then
  begin
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM TerraSatchEdge.exe', '',
      SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(500);
  end;
end;
