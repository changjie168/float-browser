# -*- coding: utf-8 -*-
"""生成 Inno Setup 安装脚本 setup.iss。

硬要求：.iss 必须是 **UTF-8 with BOM**，否则中文与 © 会乱码。
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ISS = r"""; 浮窗浏览器 —— Inno Setup 安装脚本（由 installer/make_iss.py 生成，请勿手改）
#define MyAppName      "浮窗浏览器"
#define MyAppNameEn    "FloatBrowser"
#define MyAppVersion   "1.5.0"
#define MyAppPublisher "FloatBrowser"
#define MyAppURL       ""
#define MyAppExeName   "FloatBrowser.exe"
#define MyAppId        "2962B13C-41DE-5CAF-A521-B9BEED29FC84"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion=1.5.0.0
VersionInfoProductName={#MyAppName}
VersionInfoProductTextVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 安装程序
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
SetupIconFile=..\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir=.
OutputBaseFilename=FloatBrowser_Setup_{#MyAppVersion}
; 默认按「当前用户」安装：不弹 UAC、不写系统目录；
; 需要全机安装时右键「以管理员身份运行」，会询问是否切换。
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; 程序为 x64（内嵌 win-x64 的 WebView2Loader），禁止装到 32 位系统
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Files]
; 主程序（单文件版，无需额外 DLL）
Source: "..\build_exe\dist_v15\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; WebView2 运行时引导程序：仅在目标机缺少运行时时才释放并安装（需联网，约 2 MB）
Source: "..\_tools\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; \
    Flags: deleteafterinstall; Check: not WebView2Present()

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 缺 WebView2 运行时时先装它（静默，联网）。必须排在启动主程序之前。
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/install"; \
    StatusMsg: "正在安装 WebView2 运行时（约 2 MB，需要联网）…"; \
    Check: not WebView2Present(); Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; \
    Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
{ 检测 WebView2 Evergreen Runtime 是否已安装。
  四个位置都查：64/32 位视图 × HKLM/HKCU（支持按用户安装的情况）。 }
function WebView2Present(): Boolean;
begin
  Result :=
    RegKeyExists(HKEY_LOCAL_MACHINE,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') or
    RegKeyExists(HKEY_LOCAL_MACHINE,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') or
    RegKeyExists(HKEY_CURRENT_USER,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') or
    RegKeyExists(HKEY_CURRENT_USER,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}');
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not WebView2Present() then
    MsgBox('未检测到 Microsoft Edge WebView2 运行时。' + #13#10 + #13#10 +
           '这是本程序显示网页所必需的组件，安装程序会在下一步自动联网安装（约 2 MB）。' + #13#10 +
           '如果当前电脑无法联网，请先手动下载安装后再运行本程序。',
           mbInformation, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { 卸载后清理开始菜单目录和桌面快捷方式 }
  if CurUninstallStep = usPostUninstall then
  begin
    { 用户数据（书签/缓存）保留在 %LOCALAPPDATA%\FloatBrowser，不随卸载删除 }
  end;
end;
"""

path = os.path.join(HERE, 'setup.iss')
with io.open(path, 'w', encoding='utf-8-sig', newline='\r\n') as f:
    f.write(ISS)

data = open(path, 'rb').read()
print('wrote ->', path)
print('bytes =', len(data))
print('BOM   =', data[:3] == b'\xef\xbb\xbf', '(must be True)')
print('CRLF  =', data.count(b'\r\n'), 'lines')
