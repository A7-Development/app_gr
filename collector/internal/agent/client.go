package agent

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"time"
)

// Client talks to the Strata File Gateway. Auth is the opaque agent token;
// every request also reports the collector version (heartbeat observability).
type Client struct {
	baseURL string
	token   string
	version string
	http    *http.Client
}

func NewClient(cfg *Config, version string) *Client {
	return &Client{
		baseURL: cfg.ServerURL,
		token:   cfg.Token,
		version: version,
		// Generous timeout: batches can carry a daily zip over a slow uplink.
		http: &http.Client{Timeout: 10 * time.Minute},
	}
}

// SetTimeout overrides the HTTP timeout (the `check` command uses a short
// one so a wrong URL fails fast inside the installer wizard).
func (c *Client) SetTimeout(d time.Duration) { c.http.Timeout = d }

// Watch is one folder-to-label rule from the server-side watch_config.
type Watch struct {
	Path        string `json:"path"`
	Glob        string `json:"glob"`
	SourceLabel string `json:"source_label"`
	// Container hints the SERVER-side consumer (e.g. "zip" = unpack there).
	// The collector ignores it on purpose: files always go up as-is.
	Container string `json:"container,omitempty"`
}

type WatchConfig struct {
	ScanIntervalMinutes int     `json:"scan_interval_minutes"`
	Watches             []Watch `json:"watches"`
}

type PingResponse struct {
	AgentName          string      `json:"agent_name"`
	WatchConfig        WatchConfig `json:"watch_config"`
	ServerTime         string      `json:"server_time"`
	MaxFileBytes       int64       `json:"max_file_bytes"`
	MaxFilesPerRequest int         `json:"max_files_per_request"`
}

type FileReceipt struct {
	NomeArquivo string `json:"nome_arquivo"`
	Status      string `json:"status"` // received | duplicate | rejected
	Sha256      string `json:"sha256"`
	Motivo      string `json:"motivo"`
}

type UploadResponse struct {
	SourceLabel string        `json:"source_label"`
	Received    int           `json:"received"`
	Duplicates  int           `json:"duplicates"`
	Rejected    int           `json:"rejected"`
	Results     []FileReceipt `json:"results"`
}

// AuthError means the credential is invalid or revoked (HTTP 401) — the
// loop keeps running but logs loudly; fixing it requires a new token.
type AuthError struct{ Detail string }

func (e *AuthError) Error() string { return "credencial rejeitada pelo servidor: " + e.Detail }

func (c *Client) do(req *http.Request) (*http.Response, error) {
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("X-Agent-Version", c.version)
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode == http.StatusUnauthorized {
		detail := readDetail(resp)
		resp.Body.Close()
		return nil, &AuthError{Detail: detail}
	}
	return resp, nil
}

// Ping fetches the collection policy and marks the heartbeat server-side.
func (c *Client) Ping() (*PingResponse, error) {
	req, err := http.NewRequest(http.MethodGet, c.baseURL+"/filedrop/ping", nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("ping: HTTP %d: %s", resp.StatusCode, readDetail(resp))
	}
	out := &PingResponse{}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return nil, fmt.Errorf("ping: resposta invalida: %w", err)
	}
	return out, nil
}

// UploadFile is one file of a batch, already read into memory.
type UploadFile struct {
	Name string
	Body []byte
}

// Upload sends one batch of files under a single source_label.
func (c *Client) Upload(sourceLabel string, files []UploadFile) (*UploadResponse, error) {
	body := &bytes.Buffer{}
	w := multipart.NewWriter(body)
	if err := w.WriteField("source_label", sourceLabel); err != nil {
		return nil, err
	}
	for _, f := range files {
		part, err := w.CreateFormFile("files", f.Name)
		if err != nil {
			return nil, err
		}
		if _, err := part.Write(f.Body); err != nil {
			return nil, err
		}
	}
	if err := w.Close(); err != nil {
		return nil, err
	}

	req, err := http.NewRequest(http.MethodPost, c.baseURL+"/filedrop/upload", body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", w.FormDataContentType())
	resp, err := c.do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("upload %s: HTTP %d: %s", sourceLabel, resp.StatusCode, readDetail(resp))
	}
	out := &UploadResponse{}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return nil, fmt.Errorf("upload %s: resposta invalida: %w", sourceLabel, err)
	}
	return out, nil
}

func readDetail(resp *http.Response) string {
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	var body struct {
		Detail string `json:"detail"`
	}
	if json.Unmarshal(raw, &body) == nil && body.Detail != "" {
		return body.Detail
	}
	return string(raw)
}
