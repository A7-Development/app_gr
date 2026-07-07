package agent

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// FileState remembers what the collector already dealt with, keyed by
// absolute path. It is an optimization + local audit trail — the server-side
// sha256 dedup is the real safety net, so losing this file is harmless
// (worst case: re-uploads come back as "duplicate").
type FileState struct {
	Size       int64     `json:"size"`
	ModTime    time.Time `json:"mod_time"`
	Sha256     string    `json:"sha256"`
	Status     string    `json:"status"` // uploaded | rejected
	Motivo     string    `json:"motivo,omitempty"`
	UploadedAt time.Time `json:"uploaded_at"`
}

type StateStore struct {
	path    string
	mu      sync.Mutex
	entries map[string]FileState
}

func LoadState(path string) *StateStore {
	s := &StateStore{path: path, entries: map[string]FileState{}}
	raw, err := os.ReadFile(path)
	if err == nil {
		// Corrupt state is discarded, not fatal (server dedup covers us).
		_ = json.Unmarshal(raw, &s.entries)
	}
	return s
}

func (s *StateStore) Get(path string) (FileState, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	e, ok := s.entries[path]
	return e, ok
}

func (s *StateStore) Put(path string, e FileState) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.entries[path] = e
}

// Save persists atomically (write tmp + rename).
func (s *StateStore) Save() error {
	s.mu.Lock()
	raw, err := json.MarshalIndent(s.entries, "", "  ")
	s.mu.Unlock()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(s.path), 0o755); err != nil {
		return err
	}
	tmp := s.path + ".tmp"
	if err := os.WriteFile(tmp, raw, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, s.path)
}
