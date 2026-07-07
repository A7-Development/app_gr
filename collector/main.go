// Strata Collector — agente de coleta de arquivos (Strata / A7).
//
// Roda como servico do Windows no servidor do cliente, vigia as pastas
// definidas na watch_config (que mora no SERVIDOR Strata e chega via /ping)
// e empurra arquivos novos por HTTPS outbound para o File Gateway
// (/api/v1/filedrop/upload). Zero configuracao local alem de URL + token.
//
// Uso:
//
//	strata-collector run            roda em console (debug)
//	strata-collector run -once      executa UM ciclo e sai (smoke test)
//	strata-collector check          testa a conexao (usado pelo instalador)
//	strata-collector install        registra o servico do Windows
//	strata-collector uninstall      remove o servico
//	strata-collector start | stop   controla o servico
//	strata-collector version        imprime a versao
//
// Sem argumentos = execucao como servico (invocado pelo SCM do Windows).
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"time"

	"github.com/kardianos/service"

	"github.com/A7-Development/app_gr/collector/internal/agent"
)

// Version is stamped into every request (X-Agent-Version) and shows up in
// the Strata admin UI via agent_credential.agent_version.
const Version = "0.1.0"

const serviceName = "StrataCollector"

type program struct {
	runner *agent.Runner
	cancel context.CancelFunc
	done   chan struct{}
}

func (p *program) Start(_ service.Service) error {
	ctx, cancel := context.WithCancel(context.Background())
	p.cancel = cancel
	p.done = make(chan struct{})
	go func() {
		defer close(p.done)
		p.runner.Run(ctx)
	}()
	return nil
}

func (p *program) Stop(_ service.Service) error {
	if p.cancel != nil {
		p.cancel()
		<-p.done
	}
	return nil
}

func main() {
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "version", "-version", "--version":
			fmt.Println("strata-collector " + Version)
			return
		case "run":
			runConsole(os.Args[2:])
			return
		case "check":
			runCheck(os.Args[2:])
			return
		case "install", "uninstall", "start", "stop":
			controlService(os.Args[1])
			return
		default:
			fmt.Fprintf(os.Stderr, "comando desconhecido: %s\n", os.Args[1])
			os.Exit(2)
		}
	}
	runAsService()
}

func buildRunner(configPath string, logger *log.Logger) *agent.Runner {
	cfg, path, err := agent.LoadConfig(configPath)
	if err != nil {
		logger.Fatalf("config: %v", err)
	}
	logger.Printf("strata-collector %s | config: %s | servidor: %s", Version, path, cfg.ServerURL)
	client := agent.NewClient(cfg, Version)
	state := agent.LoadState(filepath.Join(agent.DataDir(), "state.json"))
	return agent.NewRunner(cfg, client, state, logger)
}

func runConsole(args []string) {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	once := fs.Bool("once", false, "executa um unico ciclo e sai")
	configPath := fs.String("config", "", "caminho explicito do config.json")
	_ = fs.Parse(args)

	logger := log.New(os.Stdout, "", log.LstdFlags)
	runner := buildRunner(*configPath, logger)
	if *once {
		runner.RunOnce()
		return
	}
	runner.Run(context.Background())
}

// runCheck tests connectivity + credential against the gateway and prints a
// one-line verdict (ASCII-only: the installer wizard reads this output from
// a temp file and shows it to whoever is installing). Exit 0 = ok, 1 = fail.
func runCheck(args []string) {
	fs := flag.NewFlagSet("check", flag.ExitOnError)
	url := fs.String("url", "", "URL do servidor (ex.: https://strata.exemplo.com.br/api/v1)")
	token := fs.String("token", "", "token do agente (strata_agt_...)")
	configPath := fs.String("config", "", "config.json (alternativa a -url/-token)")
	_ = fs.Parse(args)

	var cfg *agent.Config
	var err error
	if *url != "" || *token != "" {
		cfg, err = agent.NewConfig(*url, *token)
	} else {
		cfg, _, err = agent.LoadConfig(*configPath)
	}
	if err != nil {
		fmt.Printf("ERRO: %v\n", err)
		os.Exit(1)
	}

	client := agent.NewClient(cfg, Version)
	client.SetTimeout(15 * time.Second)
	ping, err := client.Ping()
	if err != nil {
		fmt.Printf("ERRO: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("OK: conectado como \"%s\" - %d pasta(s) configurada(s) no servidor.\n",
		ping.AgentName, len(ping.WatchConfig.Watches))
	if len(ping.WatchConfig.Watches) == 0 {
		fmt.Println("Aviso: nenhuma pasta configurada ainda; o agente aguardara a configuracao.")
	}
}

func serviceConfig() *service.Config {
	return &service.Config{
		Name:        serviceName,
		DisplayName: "Strata Collector",
		Description: "Coleta arquivos (CNAB, XML) e envia com seguranca para a plataforma Strata.",
	}
}

func runAsService() {
	logger := log.New(newServiceLogWriter(), "", log.LstdFlags)
	prg := &program{runner: buildRunner("", logger)}
	svc, err := service.New(prg, serviceConfig())
	if err != nil {
		logger.Fatalf("service: %v", err)
	}
	if err := svc.Run(); err != nil {
		logger.Fatalf("service: %v", err)
	}
}

func controlService(action string) {
	svc, err := service.New(&program{}, serviceConfig())
	if err != nil {
		fmt.Fprintf(os.Stderr, "service: %v\n", err)
		os.Exit(1)
	}
	if err := service.Control(svc, action); err != nil {
		fmt.Fprintf(os.Stderr, "%s: %v\n", action, err)
		os.Exit(1)
	}
	fmt.Printf("%s: ok\n", action)
}

// newServiceLogWriter logs to %PROGRAMDATA%\StrataCollector\logs\collector.log
// with a dumb size-based rotation (rename to .old at ~5MB).
func newServiceLogWriter() io.Writer {
	dir := filepath.Join(agent.DataDir(), "logs")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return os.Stderr
	}
	path := filepath.Join(dir, "collector.log")
	if info, err := os.Stat(path); err == nil && info.Size() > 5*1024*1024 {
		_ = os.Remove(path + ".old")
		_ = os.Rename(path, path+".old")
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return os.Stderr
	}
	return f
}
