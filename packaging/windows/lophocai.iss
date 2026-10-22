; Bộ cài Windows (Inno Setup 6). Chạy sau khi đã có dist\LopHocAI từ PyInstaller:
;   iscc /DAppVersion=1.0.0 packaging\windows\lophocai.iss
; Kết quả: dist\LopHocAI-Setup-<phiên bản>.exe

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8F3C2B71-5D4E-4A8B-9C1F-6E2D7A9B0C31}
AppName=Lớp học AI
AppVersion={#AppVersion}
AppPublisher=tranvanhuy-hichan
AppPublisherURL=https://github.com/tranvanhuy-hichan/ai-class
DefaultDirName={autopf}\LopHocAI
DefaultGroupName=Lớp học AI
UninstallDisplayIcon={app}\LopHocAI.exe
SetupIconFile=..\icon.ico
OutputDir=..\..\dist
OutputBaseFilename=LopHocAI-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài màn hình Desktop"; GroupDescription: "Biểu tượng:"

[Files]
Source: "..\..\dist\LopHocAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Lớp học AI"; Filename: "{app}\LopHocAI.exe"
Name: "{group}\Gỡ cài đặt Lớp học AI"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Lớp học AI"; Filename: "{app}\LopHocAI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LopHocAI.exe"; Description: "Mở Lớp học AI ngay"; Flags: nowait postinstall skipifsilent
