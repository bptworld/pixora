#define AppName "Pixora"
#ifndef MyAppVersion
#define MyAppVersion "0.0.0"
#endif
#ifndef PackageDir
#define PackageDir "..\releases\Pixora-windows-v" + MyAppVersion
#endif
#ifndef OutputDir
#define OutputDir "..\releases"
#endif

[Setup]
AppId={{9F7A7D3A-EB65-4D49-8A5A-54D597B2F7A6}
AppName={#AppName}
AppVersion={#MyAppVersion}
AppPublisher=Pixora
DefaultDirName={localappdata}\Programs\Pixora
DefaultGroupName=Pixora
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=PixoraSetup-v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\Pixora.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "launch"; Description: "Launch Pixora after install"; GroupDescription: "After install:"; Flags: checkedonce

[Files]
Source: "{#PackageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{localappdata}\Pixora\data"
Name: "{localappdata}\Pixora\addons"

[Icons]
Name: "{group}\Pixora"; Filename: "{app}\Pixora.exe"
Name: "{group}\Uninstall Pixora"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Pixora"; Filename: "{app}\Pixora.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Pixora.exe"; Description: "Launch Pixora"; Flags: nowait postinstall skipifsilent; Tasks: launch

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
