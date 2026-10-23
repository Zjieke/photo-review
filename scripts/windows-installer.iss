#ifndef ReleaseVersion
  #define ReleaseVersion "0.3.0-preview.2"
#endif
[Setup]
AppId=PhotoReview.Browser
AppName=照片整理 Photo Review
AppVersion={#ReleaseVersion}
VersionInfoVersion=0.3.0.0
AppPublisher=Zjieke
AppPublisherURL=https://github.com/Zjieke/photo-review
DefaultDirName={localappdata}\Programs\Photo Review
DefaultGroupName=照片整理
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Photo-Review-{#ReleaseVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\PhotoReview.exe
CloseApplications=yes
[Files]
Source: "..\dist\Photo Review\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\照片整理"; Filename: "{app}\PhotoReview.exe"
Name: "{autodesktop}\照片整理"; Filename: "{app}\PhotoReview.exe"
[Run]
Filename: "{app}\PhotoReview.exe"; Description: "打开照片整理"; Flags: nowait postinstall skipifsilent
; No UninstallDelete entry: user photos, models and cached labels stay outside {app}.
