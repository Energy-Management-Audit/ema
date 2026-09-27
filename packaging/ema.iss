#ifndef AppVersion
  #error AppVersion must be supplied with /DAppVersion
#endif

[Setup]
AppId={{8B61BCAC-747D-4267-9E45-AF46B07DBE09}
AppName=Ema
AppVersion={#AppVersion}
AppPublisher=Energy Management & Audit SRL
DefaultDirName={autopf}\Ema
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\build\installer
OutputBaseFilename=Ema-Setup-{#AppVersion}
SetupIconFile=ema.ico
UninstallDisplayIcon={app}\Ema.exe
AppMutex=Ema.Desktop
CloseApplications=yes
WizardStyle=modern

[Languages]
Name: "ro"; MessagesFile: "Romanian.isl"

[Tasks]
Name: "desktopicon"; Description: "Creează o pictogramă pe desktop"; GroupDescription: "Pictograme suplimentare:"; Flags: checkedonce

[Files]
Source: "..\build\dist\Ema\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Ema"; Filename: "{app}\Ema.exe"
Name: "{autodesktop}\Ema"; Filename: "{app}\Ema.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Ema.exe"; Description: "Porneşte Ema"; Flags: nowait postinstall skipifsilent

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\Ema\webview"
Type: filesandordirs; Name: "{localappdata}\Ema\preview"

[Code]
function WebView2Installed(): Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := RegQueryStringValue(HKCU, Key, 'pv', Version);
  if not Result then
    Result := RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
  Result := Result and (Version <> '') and (Version <> '0.0.0.0');
end;

function InitializeSetup(): Boolean;
begin
  Result := WebView2Installed();
  if not Result then
    MsgBox('Ema are nevoie de Microsoft Edge WebView2 Runtime. Instalează-l de la https://developer.microsoft.com/microsoft-edge/webview2/ şi porneşte Ema din nou.', mbError, MB_OK);
end;
