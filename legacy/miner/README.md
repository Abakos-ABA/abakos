# miner/: Miner client + inference plugin

Takes paid jobs from the marketplace, runs the GEMM workload, produces the AI
output + PoUW/ZK proof, and submits blocks. Ships a vLLM/SGLang plugin so
existing inference providers can mine on the same watt-hour.

## Status
Plan only. No code yet.

## Scope
- Multi-vendor (NVIDIA + AMD); consumer→datacenter; CPU/Apple for light tasks.
- 1-click installer for solo miners; Docker image for neoclouds.
- vLLM/SGLang plugin (drop-in) for real-time + batch inference jobs.
