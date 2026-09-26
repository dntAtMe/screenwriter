; Inno Setup script for Screenwriter. Built by the release workflow:
;   iscc /DAppVersion=0.1.0 /DSourceDir=...\dist\Screenwriter /DOutputDir=...\out /DIconFile=...\icon.ico installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C1E3B2A-5F0D-4E2B-9A61-7D3C2B9E4F10}
AppName=Screenwriter
AppVersion={#AppVersion}
AppVerName=Screenwriter {#AppVersion}
AppPublisher=dntAtMe
AppPublisherURL=https://github.com/dntAtMe/screenwriter
AppSupportURL=https://github.com/dntAtMe/screenwriter/issues
DefaultDirName={autopf}\Screenwriter
DefaultGroupName=Screenwriter
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\Screenwriter.exe
OutputDir={#OutputDir}
OutputBaseFilename=Screenwriter-{#AppVersion}-windows-x64-setup
SetupIconFile={#IconFile}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; per-user install by default, no admin rights needed
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Screenwriter"; Filename: "{app}\Screenwriter.exe"
Name: "{autodesktop}\Screenwriter"; Filename: "{app}\Screenwriter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Screenwriter.exe"; Description: "{cm:LaunchProgram,Screenwriter}"; Flags: nowait postinstall skipifsilent
