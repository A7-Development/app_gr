package agent

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"log"
	"os"
	"path/filepath"
	"sort"
	"time"
)

// Runner is the collector's main loop: ping -> scan watches -> upload new
// stable files -> persist state; sleep the server-mandated interval; repeat.
type Runner struct {
	cfg    *Config
	client *Client
	state  *StateStore
	log    *log.Logger
}

func NewRunner(cfg *Config, client *Client, state *StateStore, logger *log.Logger) *Runner {
	return &Runner{cfg: cfg, client: client, state: state, log: logger}
}

const defaultIntervalMinutes = 5

// Run loops until ctx is cancelled. Errors never kill the loop — the next
// cycle retries; the interval is the backoff.
func (r *Runner) Run(ctx context.Context) {
	for {
		interval := r.RunOnce()
		select {
		case <-ctx.Done():
			return
		case <-time.After(interval):
		}
	}
}

// RunOnce executes a single cycle and returns how long to wait before the
// next one (from the server's watch_config; default on any failure).
func (r *Runner) RunOnce() time.Duration {
	interval := defaultIntervalMinutes * time.Minute

	ping, err := r.client.Ping()
	if err != nil {
		if _, isAuth := err.(*AuthError); isAuth {
			r.log.Printf("ERRO CRITICO: %v — verifique o token no config.json", err)
		} else {
			r.log.Printf("ping falhou (nova tentativa no proximo ciclo): %v", err)
		}
		return interval
	}
	if m := ping.WatchConfig.ScanIntervalMinutes; m > 0 {
		interval = time.Duration(m) * time.Minute
	}
	if len(ping.WatchConfig.Watches) == 0 {
		r.log.Printf("watch_config vazia no servidor — nada a coletar")
		return interval
	}

	for _, watch := range ping.WatchConfig.Watches {
		r.processWatch(watch, ping)
	}
	if err := r.state.Save(); err != nil {
		r.log.Printf("falha ao salvar state.json: %v", err)
	}
	return interval
}

func (r *Runner) processWatch(watch Watch, ping *PingResponse) {
	candidates := r.scan(watch, ping.MaxFileBytes)
	if len(candidates) == 0 {
		return
	}
	r.log.Printf("[%s] %d arquivo(s) novo(s) em %s", watch.SourceLabel, len(candidates), watch.Path)

	maxFiles := ping.MaxFilesPerRequest
	if maxFiles <= 0 {
		maxFiles = 50
	}
	for start := 0; start < len(candidates); {
		batch, next := nextBatch(candidates, start, maxFiles, ping.MaxFileBytes)
		r.uploadBatch(watch.SourceLabel, batch)
		start = next
	}
}

type candidate struct {
	path string
	info os.FileInfo
	sha  string
	body []byte
}

// scan lists files in the watch folder (top level, non-recursive) matching
// the glob, old enough to be stable, not yet uploaded in this exact version.
func (r *Runner) scan(watch Watch, maxFileBytes int64) []candidate {
	entries, err := os.ReadDir(watch.Path)
	if err != nil {
		r.log.Printf("[%s] pasta inacessivel %s: %v", watch.SourceLabel, watch.Path, err)
		return nil
	}
	glob := watch.Glob
	if glob == "" {
		glob = "*"
	}
	minAge := time.Duration(r.cfg.MinAgeSeconds) * time.Second
	now := time.Now()

	var out []candidate
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		if ok, _ := filepath.Match(glob, entry.Name()); !ok {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		path := filepath.Join(watch.Path, entry.Name())
		if info.Size() == 0 {
			continue // vazio = provavelmente ainda sendo criado; servidor rejeitaria
		}
		if maxFileBytes > 0 && info.Size() > maxFileBytes {
			r.rememberRejected(path, info, "excede max_file_bytes do servidor")
			continue
		}
		if now.Sub(info.ModTime()) < minAge {
			continue // ainda quente — pode estar sendo escrito
		}
		if prev, ok := r.state.Get(path); ok &&
			prev.Size == info.Size() && prev.ModTime.Equal(info.ModTime()) {
			continue // esta versao exata ja foi tratada (uploaded ou rejected)
		}

		body, err := os.ReadFile(path)
		if err != nil {
			r.log.Printf("[%s] leitura falhou %s: %v", watch.SourceLabel, path, err)
			continue
		}
		digest := sha256.Sum256(body)
		sha := hex.EncodeToString(digest[:])
		if prev, ok := r.state.Get(path); ok && prev.Sha256 == sha && prev.Status == "uploaded" {
			// Conteudo identico (touch/copy sem mudanca): so refresca o marcador.
			r.state.Put(path, FileState{
				Size: info.Size(), ModTime: info.ModTime(), Sha256: sha,
				Status: "uploaded", UploadedAt: prev.UploadedAt,
			})
			continue
		}
		out = append(out, candidate{path: path, info: info, sha: sha, body: body})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].path < out[j].path })
	return out
}

// nextBatch slices candidates respecting max files per request and keeping
// the batch payload under the server's per-file cap (safe multipart size).
func nextBatch(all []candidate, start, maxFiles int, maxBytes int64) ([]candidate, int) {
	var total int64
	end := start
	for end < len(all) && end-start < maxFiles {
		size := int64(len(all[end].body))
		if end > start && maxBytes > 0 && total+size > maxBytes {
			break
		}
		total += size
		end++
	}
	return all[start:end], end
}

func (r *Runner) uploadBatch(sourceLabel string, batch []candidate) {
	files := make([]UploadFile, len(batch))
	for i, c := range batch {
		files[i] = UploadFile{Name: filepath.Base(c.path), Body: c.body}
	}
	resp, err := r.client.Upload(sourceLabel, files)
	if err != nil {
		r.log.Printf("[%s] upload falhou (retry no proximo ciclo): %v", sourceLabel, err)
		return
	}
	r.log.Printf("[%s] batch: %d recebidos, %d duplicados, %d rejeitados",
		sourceLabel, resp.Received, resp.Duplicates, resp.Rejected)

	// Casa receipt por nome (unico dentro do batch — mesma pasta).
	byName := make(map[string]FileReceipt, len(resp.Results))
	for _, receipt := range resp.Results {
		byName[receipt.NomeArquivo] = receipt
	}
	now := time.Now()
	for _, c := range batch {
		receipt, ok := byName[filepath.Base(c.path)]
		if !ok {
			r.log.Printf("[%s] sem receipt para %s — retry no proximo ciclo", sourceLabel, c.path)
			continue
		}
		switch receipt.Status {
		case "received", "duplicate":
			r.state.Put(c.path, FileState{
				Size: c.info.Size(), ModTime: c.info.ModTime(), Sha256: c.sha,
				Status: "uploaded", UploadedAt: now,
			})
		case "rejected":
			r.log.Printf("[%s] REJEITADO %s: %s", sourceLabel, receipt.NomeArquivo, receipt.Motivo)
			r.rememberRejectedCandidate(c, receipt.Motivo)
		}
	}
}

func (r *Runner) rememberRejected(path string, info os.FileInfo, motivo string) {
	r.state.Put(path, FileState{
		Size: info.Size(), ModTime: info.ModTime(),
		Status: "rejected", Motivo: motivo, UploadedAt: time.Now(),
	})
}

func (r *Runner) rememberRejectedCandidate(c candidate, motivo string) {
	r.state.Put(c.path, FileState{
		Size: c.info.Size(), ModTime: c.info.ModTime(), Sha256: c.sha,
		Status: "rejected", Motivo: motivo, UploadedAt: time.Now(),
	})
}
