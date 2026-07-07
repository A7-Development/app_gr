; Strata Collector -- instalador Windows (Inno Setup 6)
;
; Compilar (na maquina de build, com Inno Setup 6 instalado):
;   1. go build -ldflags="-s -w" -o strata-collector.exe .   (na pasta collector/)
;   2. ISCC installer\strata-collector.iss
;   -> gera installer\Output\StrataCollectorSetup-<versao>.exe
;
; O wizard pede apenas URL do servidor + token do agente; todo o resto da
; politica (pastas vigiadas, globs, labels, intervalo) mora no servidor
; Strata (watch_config da credencial) e chega ao agente via /ping.

#define AppName "Strata Collector"
#define AppVersion "0.1.0"
#define AppPublisher "Strata / A7"
#define ServiceExe "strata-collector.exe"

[Setup]
AppId={{7E9A2B54-3C1D-4F8A-9B6E-52D0C4A7F310}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Strata Collector
DisableProgramGroupPage=yes
OutputBaseFilename=StrataCollectorSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
; Servico do Windows exige elevacao
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName={#AppName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
; AfterInstall garante o config.json gravado DURANTE a copia de arquivos —
; antes do [Run] registrar/iniciar o servico. (Incidente do piloto A7:
; gravar no ssPostInstall deixava o servico subir sem config e morrer.)
Source: "..\{#ServiceExe}"; DestDir: "{app}"; Flags: ignoreversion; AfterInstall: WriteConfig

[Dirs]
Name: "{commonappdata}\StrataCollector"
Name: "{commonappdata}\StrataCollector\logs"

[Code]
var
  ConfigPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ConfigPage := CreateInputQueryPage(wpSelectDir,
    'Conexao com o Strata',
    'Credenciais de acesso a plataforma',
    'Informe os dados fornecidos pela equipe Strata. As pastas monitoradas ' +
    'sao configuradas remotamente na plataforma - nada mais e necessario ' +
    'nesta maquina.');
  ConfigPage.Add('URL do servidor (ex.: https://strata.suaempresa.com.br/api/v1):', False);
  ConfigPage.Add('Token do agente (strata_agt_...):', False);
end;

// Testa a conexao chamando o proprio binario ("strata-collector check") com
// a URL + token digitados. O exe e extraido para a pasta temporaria (ainda
// nao ha nada instalado neste ponto do wizard); a saida vai para um arquivo
// temporario que e lido e mostrado a quem instala.
function TestConnection(const Url, Token: string; var Verdict: string): Boolean;
var
  ExePath, OutPath, Params: string;
  ResultCode: Integer;
  Output: AnsiString;
begin
  ExtractTemporaryFile('{#ServiceExe}');
  ExePath := ExpandConstant('{tmp}\{#ServiceExe}');
  OutPath := ExpandConstant('{tmp}\strata-check.txt');
  Params := '/C ""' + ExePath + '" check -url "' + Url + '" -token "' + Token +
    '" > "' + OutPath + '" 2>&1"';
  if not Exec(ExpandConstant('{cmd}'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Verdict := 'Nao foi possivel executar o teste de conexao.';
    Result := False;
    exit;
  end;
  if LoadStringFromFile(OutPath, Output) then
    Verdict := Trim(String(Output))
  else
    Verdict := '(sem detalhes)';
  Result := (ResultCode = 0);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Url, Token, Verdict: string;
begin
  Result := True;
  if CurPageID = ConfigPage.ID then
  begin
    Url := Trim(ConfigPage.Values[0]);
    Token := Trim(ConfigPage.Values[1]);
    if (Pos('http://', Url) <> 1) and (Pos('https://', Url) <> 1) then
    begin
      MsgBox('A URL do servidor deve comecar com http:// ou https://', mbError, MB_OK);
      Result := False;
      exit;
    end;
    if Pos('strata_agt_', Token) <> 1 then
    begin
      MsgBox('O token do agente deve comecar com "strata_agt_".', mbError, MB_OK);
      Result := False;
      exit;
    end;

    WizardForm.NextButton.Enabled := False;
    WizardForm.StatusLabel.Caption := 'Testando conexao com o servidor Strata...';
    try
      if TestConnection(Url, Token, Verdict) then
        MsgBox('Conexao com o Strata verificada com sucesso!' + #13#10#13#10 + Verdict,
          mbInformation, MB_OK)
      else
        Result := MsgBox('O teste de conexao FALHOU:' + #13#10#13#10 +
          Verdict + #13#10#13#10 +
          'Deseja instalar mesmo assim? O agente continuara ' +
          'tentando conectar automaticamente apos a instalacao.',
          mbConfirmation, MB_YESNO) = IDYES;
    finally
      WizardForm.StatusLabel.Caption := '';
      WizardForm.NextButton.Enabled := True;
    end;
  end;
end;

function JsonEscape(const S: string): string;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

procedure WriteConfig;
var
  ConfigFile, Content: string;
begin
  ForceDirectories(ExpandConstant('{commonappdata}\StrataCollector'));
  ConfigFile := ExpandConstant('{commonappdata}\StrataCollector\config.json');
  Content :=
    '{' + #13#10 +
    '  "server_url": "' + JsonEscape(Trim(ConfigPage.Values[0])) + '",' + #13#10 +
    '  "token": "' + JsonEscape(Trim(ConfigPage.Values[1])) + '"' + #13#10 +
    '}' + #13#10;
  if not SaveStringToFile(ConfigFile, Content, False) then
    MsgBox('ATENCAO: falha ao gravar ' + ConfigFile + #13#10 +
      'O servico aguardara a configuracao (re-tenta a cada 60s); ' +
      'crie o arquivo manualmente se necessario.', mbError, MB_OK);
end;

[Run]
; Registra e sobe o servico ao final da instalacao
Filename: "{app}\{#ServiceExe}"; Parameters: "install"; Flags: runhidden; StatusMsg: "Registrando servico do Windows..."
Filename: "{app}\{#ServiceExe}"; Parameters: "start"; Flags: runhidden; StatusMsg: "Iniciando o Strata Collector..."

[UninstallRun]
Filename: "{app}\{#ServiceExe}"; Parameters: "stop"; Flags: runhidden; RunOnceId: "StopService"
Filename: "{app}\{#ServiceExe}"; Parameters: "uninstall"; Flags: runhidden; RunOnceId: "UninstallService"

[UninstallDelete]
; Logs e state sao operacionais; config.json fica (reinstalacao reaproveita).
Type: filesandordirs; Name: "{commonappdata}\StrataCollector\logs"
Type: files; Name: "{commonappdata}\StrataCollector\state.json"
