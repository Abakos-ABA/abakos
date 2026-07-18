# 05 · Abakos Chat: "ChatGPT for everyone"

The consumer app is the **largest demand lever** and the difference between "another mining coin" and "a real product people use."

## Idea

A simple ChatGPT-like web/mobile app where **ordinary people** (without crypto/AI knowledge) use AI, paid with balance backed by ABA. Every chat request is served by the Abakos compute network → real, paid demand flows directly into the protocol.

## Why this matters strategically

- **Demand instead of speculation:** Pearl/Gonka have almost only miners and speculators. Abakos Chat brings *paying end users*.
- **Closes the loop Pearl only claims:** chat usage = paid inference = `useful_ratio` rises = more useful compute on-chain.
- **Mainstream onboarding:** crypto invisible in the background. Users pay with card or balance; ABA is the internal billing unit.

## UX principles

- **Crypto invisible:** login with email/Google. Wallet automatically in background (account abstraction / custodial-light for beginners).
- **Simple payment model:**
  - free quota (from ecosystem pool) → low entry barrier.
  - packages: e.g. "1,000 messages = X" via card **or** ABA (ABA = discount).
- **Fast & familiar:** streaming responses, chat history, simple model selection (e.g. "Fast" / "Smart").

## Technical integration

```
User → Abakos Chat (web/mobile)
        → gateway (auth, billing, rate-limit)
        → compute marketplace (real-time inference job, escrow)
        → auto-matched to an active, eligible miner (vLLM/SGLang, model from registry)
        → response streams back
```

- **No accept step.** A chat message can't wait for a miner to notice and claim a job; the matching engine assigns the cheapest active, sufficiently-reputed miner serving the requested model, sub-second, every time. See spec-marketplace.md §6a.
- Initially possibly **hybrid**: latency-critical requests via reliable partner GPUs, later fully decentralized when network latency is stable.
- Models: open weights (Llama, Gemma, Qwen, Mistral) in registry; "Abakos-certified" checkpoints.
- **Multi-turn continuity across rotating providers:** a conversation's messages can span multiple jobs, each matched to a different miner. The gateway holds the canonical thread and assembles the committed context per turn; no miner is relied upon to remember a conversation. Full design: [`docs/spec-session-continuity.md`](spec-session-continuity.md).

## Monetization

- Margin on raw inference cost (chat price > network cost).
- Subscription model (monthly) + pay-as-you-go.
- ABA payment with discount → real token demand, because the user has to acquire ABA to get the discount. Underneath, the marketplace job for that message settles in ABA too, so the provider serving it is paid ABA instead of stablecoin for that job (see Doc 04). Abakos Chat's own gateway can smooth this for providers by defaulting to stablecoin settlement and only passing through ABA-funded jobs to providers who've opted in.

## Risks / considerations

- **Latency** of decentralized inference vs. centralized providers → hybrid initially.
- **Moderation/abuse** (illegal content) → filters, terms of use.
- **Quality** of open models vs. GPT/Claude → clear expectation ("cheap & good enough").
- **Cost control:** free quota must not drain ecosystem pool → limits.

## MVP scope (first version)

1. Web app, email login, 1 open model.
2. Free quota + simple payment package.
3. Backend calls inference (initially via partner GPU, parallel marketplace integration).
4. Later: mobile app, ABA payment, multiple models, subscription.
