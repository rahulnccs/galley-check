; Windows installer, built by Inno Setup on the GitHub runner.
#define AppName "Galley"
#define AppVersion "0.5.1"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\Galley
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\Galley.exe
OutputDir=..\dist
OutputBaseFilename=Galley-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Files]
Source: "..\dist\Galley\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Galley.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Galley.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Run]
Filename: "{app}\Galley.exe"; Description: "Open Galley"; Flags: nowait postinstall skipifsilent
