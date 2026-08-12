; Inno Setup script for Image Toolkit — signed, single-file, per-user installer
; with Desktop + Start Menu shortcuts and a clean uninstaller. Compiled in CI.
; Expects packaging\staging\: ImageToolkit.exe, README.md, LICENSE, quickopen-root.crt.

#define AppName "Image Toolkit"
#define AppVersion "1.0.0"
#define AppPublisher "QuickOpen (quickopen.ai)"
#define AppURL "https://quickopen.ai/projects/image-toolkit"

[Setup]
AppId={{2A9F7C13-6D48-4E5B-8C71-9B0E2F3A4D51}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={autopf}\ImageToolkit
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\ImageToolkit.exe
OutputDir=dist
OutputBaseFilename=ImageToolkit-Setup
SetupIconFile=..\image-toolkit.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile=branding\wizard-large.bmp
WizardSmallImageFile=branding\wizard-small.bmp
AppCopyright=Apache-2.0. 100%% AI-built, published on QuickOpen (quickopen.ai).
VersionInfoCompany=QuickOpen
VersionInfoProductName=Image Toolkit
VersionInfoVersion=1.0.0.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=Image Toolkit is a 100%% AI-built, open-source offline image editor, published on QuickOpen (quickopen.ai).%n%nThis will install it on your computer.
BeveledLabel=QuickOpen · quickopen.ai

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "trustca"; Description: "Trust the QuickOpen Root CA (lets Windows verify QuickOpen signatures)"; GroupDescription: "Security:"; Flags: unchecked

[Files]
Source: "staging\ImageToolkit.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\quickopen-root.crt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "staging\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme skipifsourcedoesntexist
Source: "staging\LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\Image Toolkit"; Filename: "{app}\ImageToolkit.exe"; IconFilename: "{app}\ImageToolkit.exe"
Name: "{group}\Uninstall Image Toolkit"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Image Toolkit"; Filename: "{app}\ImageToolkit.exe"; IconFilename: "{app}\ImageToolkit.exe"; Tasks: desktopicon

[Run]
Filename: "certutil.exe"; Parameters: "-addstore -user Root ""{app}\quickopen-root.crt"""; Tasks: trustca; Flags: runhidden; StatusMsg: "Trusting the QuickOpen Root CA..."
Filename: "{app}\ImageToolkit.exe"; Description: "Launch Image Toolkit now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\ImageToolkit"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    if MsgBox('Also remove the QuickOpen Root CA from your Trusted Root store?' + #13#10 +
              'Choose No if you use other QuickOpen apps that rely on it.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      Exec('certutil.exe', '-delstore -user Root "QuickOpen Root CA"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
