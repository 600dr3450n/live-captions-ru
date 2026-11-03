; Inno Setup script for Live Captions RU.
; Build the app first: python tools\build.py
; Then compile this file with Inno Setup 6 (iscc installer\LiveCaptionsRU.iss).

#define AppName "Live Captions RU"
#define AppVersion "1.0.0"
#define AppExe "LiveCaptionsRU.exe"

[Setup]
AppId={{8E24B0F5-3C41-4F0E-9A57-6C2D5B7E91A4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=600D R3450N
AppPublisherURL=https://github.com/600dr3450n
DefaultDirName={autopf}\LiveCaptionsRU
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Без этой строки Inno показывает страницу приветствия, и тогда крупная
; картинка мастера видна не только на финальной странице.
DisableWelcomePage=no
; The bundled Qt 6 build does not start on anything older than Windows 10 1809.
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist-installer
OutputBaseFilename=LiveCaptionsRU-{#AppVersion}-setup
VersionInfoVersion={#AppVersion}
Compression=lzma2/max
SolidCompression=yes
; Branding: the icon of setup.exe and of the uninstaller, plus the images of the
; wizard, all taken from app\icon.ico. Sizes follow the Inno Setup 6.7 help: the
; large wizard image keeps a 164:314 aspect (202x386 at 100% DPI), the small one
; is square, above 58x58, and has a transparent background so the badge does not
; sit in a black box in the upper right corner.
SetupIconFile=..\app\icon.ico
WizardImageFile=assets\wizard.png
WizardSmallImageFile=assets\wizard-small.png
WizardStyle=classic
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=LICENSE

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"
Name: "autostart"; Description: "Запускать при входе в систему"; GroupDescription: "Дополнительно:"

[InstallDelete]
; Leftovers of an older build must be removed: a stale module next to the exe is
; imported by Python before anything else and breaks the new version silently.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\*.py"
Type: files; Name: "{app}\*.pyc"

[Files]
Source: "..\dist\LiveCaptionsRU\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; Settings survive an uninstall on purpose: the box position and the look are the user's
; work. The log does not: after a reinstall it has to start empty, the same promise the
; app makes on a version change.
Type: files; Name: "{localappdata}\LiveCaptionsRU\app.log"
Type: files; Name: "{localappdata}\LiveCaptionsRU\app.log.*"

[Code]
function InitializeSetup(): Boolean;
var
  Version: TWindowsVersion;
begin
  Result := True;
  GetWindowsVersionEx(Version);
  if (Version.Major < 10) or ((Version.Major = 10) and (Version.Build < 19041)) then
    MsgBox('Субтитры будут видны на скриншотах и при демонстрации экрана: скрывать их умеет только Windows 10 версии 2004 (сборка 19041) и новее.' + #13#10 + #13#10 +
           'Само распознавание при этом работает.', mbInformation, MB_OK);
end;
