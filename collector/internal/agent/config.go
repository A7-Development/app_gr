// Package agent implements the Strata Collector: a dumb forwarder that
// watches client folders (policy comes from the server via /ping) and pushes
// new files to the Strata File Gateway (/api/v1/filedrop/*) over outbound
// HTTPS. It never opens containers (zips go up as-is — the server unpacks)
// and never decides policy locally.
package agent

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Config is the only thing that lives on the client machine: where the
// Strata server is and which credential to present. Everything else
// (folders to watch, globs, labels, intervals, limits) comes from /ping.
type Config struct {
	// Base URL of the Strata API, e.g. "https://gr.example.com/api/v1".
	ServerURL string `json:"server_url"`
	// Opaque agent token ("strata_agt_..."), shown once at credential creation.
	Token string `json:"token"`
	// Minimum age (seconds) of a file before it is considered stable enough
	// to upload. Guards against uploading a CNAB still being written.
	MinAgeSeconds int `json:"min_age_seconds,omitempty"`
}

const defaultMinAgeSeconds = 60

// NewConfig builds a validated Config from explicit values (used by the
// `check` command, where URL/token come from flags instead of config.json).
func NewConfig(serverURL, token string) (*Config, error) {
	cfg := &Config{ServerURL: serverURL, Token: token}
	if err := cfg.validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

// DataDir is where the collector keeps its own state and logs
// (%PROGRAMDATA%\StrataCollector on Windows).
func DataDir() string {
	base := os.Getenv("PROGRAMDATA")
	if base == "" {
		base = `C:\ProgramData`
	}
	return filepath.Join(base, "StrataCollector")
}

// LoadConfig reads config.json from, in order: the explicit path (if given),
// the executable's directory, then DataDir(). The installer writes it to
// DataDir() so upgrades never touch it.
func LoadConfig(explicit string) (*Config, string, error) {
	var candidates []string
	if explicit != "" {
		candidates = []string{explicit}
	} else {
		if exe, err := os.Executable(); err == nil {
			candidates = append(candidates, filepath.Join(filepath.Dir(exe), "config.json"))
		}
		candidates = append(candidates, filepath.Join(DataDir(), "config.json"))
	}

	for _, path := range candidates {
		raw, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		cfg := &Config{}
		if err := json.Unmarshal(raw, cfg); err != nil {
			return nil, path, fmt.Errorf("config invalido em %s: %w", path, err)
		}
		if err := cfg.validate(); err != nil {
			return nil, path, err
		}
		return cfg, path, nil
	}
	return nil, "", fmt.Errorf(
		"config.json nao encontrado (procurado em: %s)", strings.Join(candidates, "; "))
}

func (c *Config) validate() error {
	if !strings.HasPrefix(c.ServerURL, "http://") && !strings.HasPrefix(c.ServerURL, "https://") {
		return fmt.Errorf("server_url deve comecar com http(s)://: %q", c.ServerURL)
	}
	if strings.TrimSpace(c.Token) == "" {
		return fmt.Errorf("token vazio no config.json")
	}
	if c.MinAgeSeconds <= 0 {
		c.MinAgeSeconds = defaultMinAgeSeconds
	}
	c.ServerURL = strings.TrimRight(c.ServerURL, "/")
	return nil
}
