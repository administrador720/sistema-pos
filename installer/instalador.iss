; Inno Setup (https://jrsoftware.org/isinfo.php): empaqueta la carpeta generada por PyInstaller en un instalador .exe
;   iscc installer\instalador.iss        →  dist\Instalador-POS-Supermercado-1.0.0.exe
#define Nombre "POS Supermercado"
#define Version "1.0.0"
#define Exe "POSSupermercado.exe"

[Setup]
AppId={{6C1A0E55-2B7B-4C5B-9C3E-5D9F3E0B7A11}
AppName={#Nombre}
AppVersion={#Version}
AppPublisher=Supermercado
DefaultDirName={autopf}\POSSupermercado
DefaultGroupName={#Nombre}
OutputDir=..\dist
OutputBaseFilename=Instalador-POS-Supermercado-{#Version}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayIcon={app}\{#Exe}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "icono"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\POSSupermercado\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
; La base de datos y los respaldos viven aquí y NO se borran al desinstalar. Los cajeros (usuarios normales) deben poder escribir.
Name: "{commonappdata}\POSSupermercado"; Permissions: users-modify

[Icons]
Name: "{group}\{#Nombre}"; Filename: "{app}\{#Exe}"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\{#Exe}"; Tasks: icono

[Run]
Filename: "{app}\{#Exe}"; Description: "Abrir {#Nombre}"; Flags: nowait postinstall skipifsilent

[Code]
// La ventana usa Microsoft Edge WebView2 (viene con Windows 10/11 actualizados).
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
