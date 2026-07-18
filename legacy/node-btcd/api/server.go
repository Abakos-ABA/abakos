// Package api serves a minimal read-only HTTP API for the T0 explorer wireframe.
package api

import (
	"encoding/hex"
	"encoding/json"
	"net/http"
	"time"

	"github.com/rexmarlon/abakos/node/chain"
)

// Explorer is the read-only chain surface used by the HTTP API.
type Explorer interface {
	ComputeStats() chain.Stats
	Blocks() []*chain.Block
}

// Server exposes chain stats over HTTP.
type Server struct {
	Chain Explorer
}

// NewServer returns an API server for the given chain view.
func NewServer(c Explorer) *Server {
	return &Server{Chain: c}
}

// ListenAndServe starts the HTTP API on addr.
func (s *Server) ListenAndServe(addr string) error {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/stats", s.handleStats)
	mux.HandleFunc("/api/v1/blocks", s.handleBlocks)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	srv := &http.Server{Addr: addr, Handler: cors(mux), ReadHeaderTimeout: 5 * time.Second}
	return srv.ListenAndServe()
}

func (s *Server) handleStats(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, s.Chain.ComputeStats())
}

func (s *Server) handleBlocks(w http.ResponseWriter, _ *http.Request) {
	type row struct {
		Height      uint64  `json:"height"`
		Hash        string  `json:"hash"`
		UsefulPct   float64 `json:"useful_pct"`
		RewardABA   float64 `json:"reward_aba"`
		Timestamp   string  `json:"timestamp"`
		WorkUnits   uint64  `json:"work_units"`
	}
	var rows []row
	for _, b := range s.Chain.Blocks() {
		info := chain.RewardInfo(b)
		h := b.Hash()
		rows = append(rows, row{
			Height:    b.Height,
			Hash:      hex.EncodeToString(h[:]),
			UsefulPct: info.UsefulRatio * 100,
			RewardABA: info.RewardABA,
			Timestamp: b.Header.Timestamp.UTC().Format(time.RFC3339),
		})
	}
	if rows == nil {
		rows = []row{}
	}
	writeJSON(w, map[string]any{"blocks": rows})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	_ = json.NewEncoder(w).Encode(v)
}

func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
