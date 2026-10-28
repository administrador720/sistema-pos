; Inno Setup 6 (https://jrsoftware.org/isinfo.php): empaqueta la carpeta de PyInstaller en un instalador .exe
;   iscc /DVersion=1.1.0 installer\instalador.iss   →   dist\Instalador-POS-Supermercado-1.1.0.exe
; Antes: python scripts\hacer_icono.py (crea installer\icono.ico) y pyinstaller installer\pos.spec
#ifndef Version
  #define Version "1.1.0"
#endif
#define Nombre "POS Supermercado"
#define Exe "POSSupermercado.exe"

[Setup]
AppId={{6C1A0E55-2B7B-4C5B-9C3E-5D9F3E0B7A11}
AppName={#Nombre}
AppVersion={#Version}
AppVerName={#Nombre} {#Version}
AppPublisher=POS Supermercado
AppPublisherURL=https://github.com/administrador720/sistema-pos
AppSupportURL=https://github.com/administrador720/sistema-pos/issues
VersionInfoVersion={#Version}
DefaultDirName={autopf}\POSSupermercado
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Instalador-POS-Supermercado-{#Version}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nombre}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
WizardStyle=modern
ShowLanguageDialog=no
LanguageDetectionMethod=none
; Si el programa está abierto (al actualizar), el instalador lo cierra con el Administrador de reinicio de Windows y se
; vuelve a abrir al terminar (/RELANZAR=1). No se usa AppMutex: en una instalación silenciosa cancelaría la actualización.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "icono"; Description: "Crear un ícono en el escritorio"; GroupDescription: "Accesos directos:"

[InstallDelete]
; Una actualización no deja archivos de la versión anterior (PyInstaller guarda sus librerías en _internal)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\POSSupermercado\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
#ifexist "MicrosoftEdgeWebview2Setup.exe"
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not WebView2Instalado
#endif

[Dirs]
; La base de datos y los respaldos viven aquí y NO se borran al desinstalar. Todos los usuarios de Windows (los cajeros) deben poder escribir.
Name: "{commonappdata}\POSSupermercado"; Permissions: users-modify; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#Nombre}"; Filename: "{app}\{#Exe}"; Comment: "Punto de venta"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\{#Exe}"; Comment: "Punto de venta"; Tasks: icono

[Run]
#ifexist "MicrosoftEdgeWebview2Setup.exe"
; La ventana del programa necesita Microsoft Edge WebView2 (ya viene en Windows 10/11 actualizados; si falta, se instala)
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalando el componente de ventana (WebView2)..."; Flags: waituntilterminated; Check: not WebView2Instalado
#endif
; runasoriginaluser: el programa NO debe quedar corriendo como administrador (crearía archivos que los cajeros no podrían modificar)
Filename: "{app}\{#Exe}"; Description: "Abrir {#Nombre}"; Flags: nowait postinstall runasoriginaluser; Check: DebeAbrir

[Code]
const
  GuidWebView2 = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Instalado(): Boolean;
var
  v: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + GuidWebView2, 'pv', v) then
    Result := (v <> '') and (v <> '0.0.0.0');
  if (not Result) and RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + GuidWebView2, 'pv', v) then
    Result := (v <> '') and (v <> '0.0.0.0');
end;

// Instalación normal: se ofrece abrir el programa. Instalación silenciosa: solo si lo pide una actualización (/RELANZAR=1).
function DebeAbrir(): Boolean;
begin
  Result := (not WizardSilent) or (ExpandConstant('{param:RELANZAR|0}') = '1');
end;
