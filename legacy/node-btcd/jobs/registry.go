// Package jobs provides the T0 job-commitment stub used to enforce useful_ratio.
// Full marketplace escrow lands in marketplace/; until then, useful_ratio > 0
// requires a registered, funded job whose ID is committed in ProofCommitment.
package jobs

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"sync"
	"time"
)

// Job is a minimal funded escrow stub (T0).
type Job struct {
	ID        [32]byte
	Funded    bool
	ExpiresAt time.Time
	Label     string
}

// Registry is an in-memory job store for simnet / consensus checks.
type Registry struct {
	mu   sync.RWMutex
	jobs map[[32]byte]Job
}

// Global is the process-wide registry used by consensus validation.
var Global = NewRegistry()

// NewRegistry creates an empty job registry.
func NewRegistry() *Registry {
	return &Registry{jobs: make(map[[32]byte]Job)}
}

// Reset clears all jobs (tests).
func (r *Registry) Reset() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.jobs = make(map[[32]byte]Job)
}

// Register adds or replaces a job.
func (r *Registry) Register(j Job) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.jobs[j.ID] = j
}

// Get returns a job by ID.
func (r *Registry) Get(id [32]byte) (Job, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	j, ok := r.jobs[id]
	return j, ok
}

// DemoJobID returns a deterministic job ID for simnet demos (label-scoped).
func DemoJobID(label string) [32]byte {
	h := sha256.New()
	h.Write([]byte("abakos-t0-job:"))
	h.Write([]byte(label))
	var out [32]byte
	copy(out[:], h.Sum(nil))
	return out
}

// RegisterDemoFunded registers a funded demo job that expires in 24h.
func (r *Registry) RegisterDemoFunded(label string) [32]byte {
	id := DemoJobID(label)
	r.Register(Job{
		ID:        id,
		Funded:    true,
		ExpiresAt: time.Now().Add(24 * time.Hour),
		Label:     label,
	})
	return id
}

// ValidateCommitment enforces the T0 economic binding rule:
//   - useful_bps == 0  → ProofCommitment must be zero (empty mining)
//   - useful_bps > 0   → ProofCommitment must reference a funded, non-expired job
func ValidateCommitment(usefulBps uint16, commitment [32]byte, now time.Time, r *Registry) error {
	if usefulBps > 10000 {
		return fmt.Errorf("jobs: useful_bps out of range")
	}
	zero := [32]byte{}
	if usefulBps == 0 {
		if commitment != zero {
			return fmt.Errorf("jobs: empty mining must not set job commitment")
		}
		return nil
	}
	if commitment == zero {
		return fmt.Errorf("jobs: useful_ratio > 0 requires job commitment")
	}
	if r == nil {
		r = Global
	}
	j, ok := r.Get(commitment)
	if !ok {
		return fmt.Errorf("jobs: unknown job commitment %x", commitment[:8])
	}
	if !j.Funded {
		return fmt.Errorf("jobs: job %x not funded", commitment[:8])
	}
	if !j.ExpiresAt.IsZero() && now.After(j.ExpiresAt) {
		return fmt.Errorf("jobs: job %x expired", commitment[:8])
	}
	return nil
}

// CommitmentFromUint64 builds a deterministic 32-byte ID (tests).
func CommitmentFromUint64(n uint64) [32]byte {
	var b [8]byte
	binary.BigEndian.PutUint64(b[:], n)
	return sha256.Sum256(append([]byte("abakos-job-n:"), b[:]...))
}
