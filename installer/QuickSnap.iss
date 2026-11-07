; Inno Setup script: turns dist\QuickSnap into one installer file.
; Build with:  python installer/build_installer.py   (reads the version from app\version.py)
; Output:      installer\output\QuickSnap-Setup-<version>.exe
;
; Per-user install (no administrator rights): %LOCALAPPDATA%\Programs\QuickSnap.
; First install asks where screenshots go and whether to start with Windows, and leaves
; those choices in %APPDATA%\QuickSnap\installer.json for QuickSnap's first run.
; Upgrades keep the user's settings and skip those questions.
; This file must stay UTF-8 *with* BOM (Chinese / Japanese texts below).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "QuickSnap"
#define AppPublisher "Sky Chen"
#define AppExe "QuickSnap.exe"

[Setup]
AppId={{28AA2EB5-F581-4FD7-9FBE-105AEBD95AFC}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
SetupIconFile=..\app\assets\icon.ico
OutputDir=output
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
ShowLanguageDialog=yes
; QuickSnap lives in the tray with no normal window, so the code below asks it to quit itself
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[CustomMessages]
english.SaveDirCaption=Screenshot folder
english.SaveDirDescription=Where should QuickSnap save your screenshots?
english.SaveDirSubCaption=When you click "Save" after taking a screenshot, the picture goes into this folder. You can change it later in QuickSnap's Settings.
english.SaveDirBadDrive=That drive does not exist. Please choose another folder.
english.StartupGroup=Start-up:
english.AutostartTask=Start QuickSnap automatically when I sign in to Windows
chinesesimplified.SaveDirCaption=截图保存位置
chinesesimplified.SaveDirDescription=截图要存到哪里？
chinesesimplified.SaveDirSubCaption=截图后点「保存」，图片会存到这个文件夹。以后可以在 QuickSnap 的设置里修改。
chinesesimplified.SaveDirBadDrive=这个盘不存在，请换一个文件夹。
chinesesimplified.StartupGroup=启动：
chinesesimplified.AutostartTask=登录 Windows 时自动启动 QuickSnap
japanese.SaveDirCaption=保存フォルダー
japanese.SaveDirDescription=スクリーンショットをどこに保存しますか？
japanese.SaveDirSubCaption=キャプチャ後に「保存」を押すと、このフォルダーに保存されます。あとで QuickSnap の設定から変更できます。
japanese.SaveDirBadDrive=そのドライブはありません。別のフォルダーを選んでください。
japanese.StartupGroup=起動:
japanese.AutostartTask=Windows にサインインしたら QuickSnap を自動で起動する

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"; GroupDescription: "{cm:StartupGroup}"; Check: IsFreshInstall
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\QuickSnap\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WM_QUIT_REQUEST = $8002;   { WM_APP + 2, handled in app/hotkey.py }
  SINK_TITLE = 'QuickSnap hotkey sink';
  DRIVE_FIXED = 3;
  RUN_KEY = 'Software\Microsoft\Windows\CurrentVersion\Run';
  APPROVED_KEY = 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run';
  UNINST_KEY = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{28AA2EB5-F581-4FD7-9FBE-105AEBD95AFC}_is1';

var
  SaveDirPage: TInputDirWizardPage;
  FreshInstall: Boolean;

function GetDriveType(lpRootPathName: String): Cardinal;
  external 'GetDriveTypeW@kernel32.dll stdcall';

function IsFreshInstall: Boolean;
begin
  Result := FreshInstall;
end;

{ Same rule as app/config.py default_save_dir(): first local hard drive that is not the
  system drive -> X:\QuickSnap Screenshots; otherwise Pictures\QuickSnap. }
function DefaultSaveDir: String;
var
  i: Integer;
  Letter, SysDrive: String;
begin
  SysDrive := Uppercase(Copy(ExpandConstant('{sd}'), 1, 1));
  for i := Ord('A') to Ord('Z') do
  begin
    Letter := Chr(i);
    if (Letter <> SysDrive) and (GetDriveType(Letter + ':\') = DRIVE_FIXED) then
    begin
      Result := Letter + ':\QuickSnap Screenshots';
      Exit;
    end;
  end;
  Result := ExpandConstant('{userpics}') + '\QuickSnap';
end;

{ Ask a running QuickSnap to quit (it finds the request through its hidden window). }
procedure CloseRunningQuickSnap;
var
  Wnd: HWND;
  Tries: Integer;
begin
  Tries := 0;
  Wnd := FindWindowByWindowName(SINK_TITLE);
  while (Wnd <> 0) and (Tries < 50) do
  begin
    PostMessage(Wnd, WM_QUIT_REQUEST, 0, 0);
    Sleep(100);
    Tries := Tries + 1;
    Wnd := FindWindowByWindowName(SINK_TITLE);
  end;
  if Tries > 0 then
    Sleep(500);  { give the process a moment to release its files }
end;

function InitializeSetup: Boolean;
begin
  FreshInstall := not (RegKeyExists(HKCU, UNINST_KEY) or RegKeyExists(HKLM, UNINST_KEY));
  Result := True;
end;

procedure InitializeWizard;
begin
  SaveDirPage := CreateInputDirPage(wpSelectDir, CustomMessage('SaveDirCaption'),
    CustomMessage('SaveDirDescription'), CustomMessage('SaveDirSubCaption'), False, '');
  SaveDirPage.Add('');
  SaveDirPage.Values[0] := DefaultSaveDir;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = SaveDirPage.ID) and not FreshInstall;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = SaveDirPage.ID) and not DirExists(ExtractFileDrive(SaveDirPage.Values[0]) + '\') then
  begin
    MsgBox(CustomMessage('SaveDirBadDrive'), mbError, MB_OK);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  CloseRunningQuickSnap;
  Result := '';
end;

function JsonEscape(S: String): String;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

function LangCode: String;
begin
  if ActiveLanguage = 'chinesesimplified' then
    Result := 'zh'
  else if ActiveLanguage = 'japanese' then
    Result := 'ja'
  else
    Result := 'en';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lines: TArrayOfString;
  Dir, AutoStart: String;
begin
  if (CurStep = ssPostInstall) and FreshInstall then
  begin
    Dir := SaveDirPage.Values[0];
    ForceDirectories(Dir);
    if WizardIsTaskSelected('autostart') then
    begin
      AutoStart := 'true';
      RegWriteStringValue(HKCU, RUN_KEY, 'QuickSnap', '"' + ExpandConstant('{app}\{#AppExe}') + '" --autostart');
    end
    else
      AutoStart := 'false';
    SetArrayLength(Lines, 1);
    Lines[0] := '{"save_dir": "' + JsonEscape(Dir) + '", "language": "' + LangCode +
                '", "autostart": ' + AutoStart + '}';
    ForceDirectories(ExpandConstant('{userappdata}\QuickSnap'));
    SaveStringsToUTF8File(ExpandConstant('{userappdata}\QuickSnap\installer.json'), Lines, False);
  end;
end;

function InitializeUninstall: Boolean;
begin
  CloseRunningQuickSnap;
  Result := True;
end;

{ Screenshots and settings (%APPDATA%\QuickSnap) are kept; only the auto-start entry goes. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKCU, RUN_KEY, 'QuickSnap');
    RegDeleteValue(HKCU, APPROVED_KEY, 'QuickSnap');
  end;
end;
