// Command abkd is the Abakos full node.
//
// T0 simnet:
//   abkd --simnet --datadir ./data/seed --listen :18555 --mine --http :13080
//   abkd --simnet --datadir ./data/follower --connect 127.0.0.1:18555
package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/rexmarlon/abakos/node/api"
	"github.com/rexmarlon/abakos/node/chain"
	"github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/fork"
	"github.com/rexmarlon/abakos/node/jobs"
	"github.com/rexmarlon/abakos/node/params"
	"github.com/rexmarlon/abakos/node/p2p"
	"github.com/rexmarlon/abakos/node/pouw"
	"github.com/rexmarlon/abakos/node/simnet"
)

const version = "0.0.5-dev"

func main() {
	simnetFlag := flag.Bool("simnet", false, "use local simnet")
	mine := flag.Bool("mine", false, "mine blocks (seed node)")
	blocks := flag.Int("blocks", 0, "stop after N blocks mined (0 = run until interrupted)")
	usefulBps := flag.Uint("useful-bps", 0, "useful_ratio basis points [0,10000]; >0 requires funded job (auto demo job in simnet)")
	verifierName := flag.String("verifier", "gemm", "pouw verifier: gemm | sha256")
	p2pMode := flag.String("p2p", "simple", "P2P backend: simple | btcd")
	listen := flag.String("listen", "", "TCP P2P listen (e.g. :18555)")
	connect := flag.String("connect", "", "comma-separated peer addresses")
	datadir := flag.String("datadir", "", "persist chain to directory")
	httpAddr := flag.String("http", "", "explorer API listen (e.g. :13080)")
	showParams := flag.Bool("params", true, "print economic parameters")
	flag.Parse()

	if !*simnetFlag {
		runInfo(*showParams)
		return
	}
	if *usefulBps > 10000 {
		fatal("--useful-bps must be <= 10000")
	}
	if *usefulBps > 0 {
		id := jobs.Global.RegisterDemoFunded("simnet-paid")
		fmt.Printf("job commitment registered: %x… (useful-bps=%d)\n", id[:8], *usefulBps)
	}

	v, vname := newVerifier(*verifierName)
	fork.SetVerifier(v)
	chain.SetSimNetVerifier(v)
	peers := splitCSV(*connect)

	if *p2pMode == "btcd" {
		runBtcdSimnet(v, vname, *datadir, *listen, peers, *mine, *blocks, uint16(*usefulBps), *httpAddr, *showParams)
		return
	}

	fmt.Printf("abkd %s: %s · verifier=%s\n\n", version, chaincfg.SimNetName, vname)
	if g := chaincfg.TestNetGenesis(); *showParams {
		fmt.Printf("testnet genesis (draft): %s · %s\n\n", g.ChainID, g.Timestamp.Format(time.RFC3339))
	}

	c := chain.NewNamed(v, vname, chaincfg.SimNetEasyBits)
	if *datadir != "" {
		if snap, err := chain.LoadSnapshot(*datadir); err == nil {
			if err := c.Restore(snap); err != nil {
				fatal("restore chain: %v", err)
			}
			fmt.Printf("restored %d blocks from %s\n", c.Len(), *datadir)
		} else if !errors.Is(err, os.ErrNotExist) {
			fatal("load chain: %v", err)
		}
	}

	node := simnet.NewNode(c, *listen, peers)
	save := func() {
		if *datadir == "" {
			return
		}
		if err := c.Save(*datadir); err != nil {
			fmt.Fprintf(os.Stderr, "save chain: %v\n", err)
		}
	}
	node.OnBlock(func(b *chain.Block) {
		logBlock(b, v)
		save()
	})

	if err := node.Run(); err != nil {
		fatal("simnet: %v", err)
	}

	if *httpAddr != "" {
		go func() {
			srv := api.NewServer(c)
			fmt.Printf("explorer API http://127.0.0.1%s/api/v1/stats\n", *httpAddr)
			if err := srv.ListenAndServe(*httpAddr); err != nil {
				fmt.Fprintf(os.Stderr, "http: %v\n", err)
			}
		}()
	}

	isFollower := *connect != "" && !*mine && *listen == ""
	if c.Len() == 0 && !isFollower {
		fmt.Println("mining genesis...")
		gen, err := c.InitGenesis()
		if err != nil {
			fatal("genesis: %v", err)
		}
		node.PublishBlock(gen)
		save()
	} else if isFollower && c.Len() == 0 {
		fmt.Println("following peer, waiting for blocks...")
	}

	if *mine {
		go runMiner(node, c, *blocks, uint16(*usefulBps), save)
	}

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig
	fmt.Println("\nshutting down...")
	save()
	node.Stop()
}

func runMiner(node *simnet.Node, c *chain.Chain, maxBlocks int, usefulBps uint16, save func()) {
	time.Sleep(500 * time.Millisecond)
	for {
		if maxBlocks > 0 && c.Len() >= maxBlocks {
			return
		}
		b, err := c.MineNext(usefulBps)
		if err != nil {
			fmt.Fprintf(os.Stderr, "mine failed: %v\n", err)
			return
		}
		node.PublishBlock(b)
		save()
		time.Sleep(300 * time.Millisecond)
	}
}

func runInfo(showParams bool) {
	fmt.Printf("abkd %s: Abakos full node (T0)\n\n", version)
	if showParams {
		fmt.Print(params.Summary())
		fmt.Println()
	}
	fmt.Println("Seed:  abkd --simnet --datadir ./data/seed --listen :18555 --mine --http :13080")
	fmt.Println("Follow: abkd --simnet --datadir ./data/follower --connect 127.0.0.1:18555")
	fmt.Println("btcd:  abkd --simnet --p2p btcd --datadir ./data/seed --listen :18555 --mine --http :13080")
}

func runBtcdSimnet(v pouw.WorkVerifier, vname, datadir, listen string, peers []string, mine bool, maxBlocks int, usefulBps uint16, httpAddr string, showParams bool) {
	fmt.Printf("abkd %s: %s · verifier=%s · p2p=btcd/netsync\n\n", version, chaincfg.SimNetName, vname)
	if g := chaincfg.TestNetGenesis(); showParams {
		fmt.Printf("testnet genesis (draft): %s · %s\n\n", g.ChainID, g.Timestamp.Format(time.RFC3339))
	}

	srv, err := p2p.NewServer(p2p.Config{
		DataDir:   datadir,
		Listen:    listen,
		Connect:   peers,
		Mine:      mine,
		MaxBlocks: maxBlocks,
		UsefulBps: usefulBps,
		Verifier:  v,
		OnBlock: func(height int32, hash string) {
			fmt.Printf("block %3d  hash=%s…  pouw=OK  (btcd)\n", height, hash[:16])
		},
	})
	if err != nil {
		fatal("p2p: %v", err)
	}
	srv.Start()
	defer srv.Stop()

	if httpAddr != "" {
		view := chain.NewBtcdView(srv.Chain(), vname)
		go func() {
			apiSrv := api.NewServer(view)
			fmt.Printf("explorer API http://127.0.0.1%s/api/v1/stats\n", httpAddr)
			if err := apiSrv.ListenAndServe(httpAddr); err != nil {
				fmt.Fprintf(os.Stderr, "http: %v\n", err)
			}
		}()
	}

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig
	fmt.Println("\nshutting down...")
}

func newVerifier(name string) (pouw.WorkVerifier, string) {
	switch strings.ToLower(name) {
	case "sha256", "stub":
		return pouw.SHA256StubVerifier{}, "sha256"
	case "gemm", "pouw", "cpu":
		return pouw.CPUGEMMVerifier{}, "gemm"
	default:
		fatal("unknown --verifier %q (gemm | sha256)", name)
		return nil, ""
	}
}

func splitCSV(s string) []string {
	if s == "" {
		return nil
	}
	var out []string
	for _, p := range strings.Split(s, ",") {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func logBlock(b *chain.Block, verifier pouw.WorkVerifier) {
	info := chain.RewardInfo(b)
	status := "OK"
	if err := verifier.Verify(&b.Header, b.Proof); err != nil {
		status = err.Error()
	}
	fmt.Printf("block %3d  hash=%s…  pouw=%s  useful=%.0f%%  reward=%.4f ABA  burn=%.4f ABA\n",
		b.Height, b.HashString(), status,
		info.UsefulRatio*100, info.RewardABA, info.BurnedABA)
}

func fatal(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "abkd: "+format+"\n", args...)
	os.Exit(1)
}
