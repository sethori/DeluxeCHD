; Inno Setup script for the Windows installer.
; Build (from the repo root, after pyinstaller + make_icons):
;   iscc /DAppVersion=2.0.0 packaging\windows\DeluxeCHD.iss
; Output: dist\DeluxeCHD-Setup-x64.exe  (this exact name is what the in-app updater downloads)

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C3F1E4A-2B7D-4C59-9E1A-5D6F7A8B9C01}
AppName=DeluxeCHD
AppVersion={#AppVersion}
AppVerName=DeluxeCHD {#AppVersion}
AppPublisher=sethori
AppPublisherURL=https://github.com/sethori/DeluxeCHD
AppSupportURL=https://github.com/sethori/DeluxeCHD/issues
AppUpdatesURL=https://github.com/sethori/DeluxeCHD/releases
DefaultDirName={autopf}\DeluxeCHD
DisableProgramGroupPage=yes
; Per-user install by default, so the in-app updater can upgrade without a UAC prompt
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=DeluxeCHD-Setup-x64
SetupIconFile=..\..\build\icons\DeluxeCHD.ico
UninstallDisplayIcon={app}\DeluxeCHD.exe
LicenseFile=..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Remove the previous version's bundled libraries so upgrades never mix old and new files
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\..\dist\DeluxeCHD\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DeluxeCHD"; Filename: "{app}\DeluxeCHD.exe"
Name: "{autodesktop}\DeluxeCHD"; Filename: "{app}\DeluxeCHD.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DeluxeCHD.exe"; Description: "{cm:LaunchProgram,DeluxeCHD}"; Flags: nowait postinstall skipifsilent
; Silent self-update from inside the app passes /RELAUNCH=1
Filename: "{app}\DeluxeCHD.exe"; Flags: nowait runasoriginaluser; Check: ShouldRelaunch

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;
