package jobs_test

import (
	"testing"
	"time"

	"github.com/rexmarlon/abakos/node/jobs"
)

func TestValidateCommitment_EmptyMining(t *testing.T) {
	r := jobs.NewRegistry()
	var zero [32]byte
	if err := jobs.ValidateCommitment(0, zero, time.Now(), r); err != nil {
		t.Fatal(err)
	}
	id := r.RegisterDemoFunded("x")
	if err := jobs.ValidateCommitment(0, id, time.Now(), r); err == nil {
		t.Fatal("empty mining must reject non-zero commitment")
	}
}

func TestValidateCommitment_UsefulRequiresFundedJob(t *testing.T) {
	r := jobs.NewRegistry()
	var zero [32]byte
	if err := jobs.ValidateCommitment(5000, zero, time.Now(), r); err == nil {
		t.Fatal("expected error for missing commitment")
	}
	id := jobs.DemoJobID("paid")
	r.Register(jobs.Job{ID: id, Funded: false, ExpiresAt: time.Now().Add(time.Hour)})
	if err := jobs.ValidateCommitment(5000, id, time.Now(), r); err == nil {
		t.Fatal("expected error for unfunded job")
	}
	r.Register(jobs.Job{ID: id, Funded: true, ExpiresAt: time.Now().Add(-time.Hour)})
	if err := jobs.ValidateCommitment(5000, id, time.Now(), r); err == nil {
		t.Fatal("expected error for expired job")
	}
	r.Register(jobs.Job{ID: id, Funded: true, ExpiresAt: time.Now().Add(time.Hour)})
	if err := jobs.ValidateCommitment(5000, id, time.Now(), r); err != nil {
		t.Fatal(err)
	}
}
