# Spec · Conversation & Session Continuity Across Providers

Status: Design v0.1 (workstream B, extends Doc 04/05/16 and spec-marketplace.md). Answers one question: in a marketplace where every job can go to a different provider, how does a multi-turn conversation (Abakos Chat, or a multi-turn Developer API session) not lose context when turn 2 lands on a completely different GPU than turn 1?

## 1. Why this needs its own answer

A single inference call is already a solved problem: it's one funded job, matched to one provider, proven, settled (Doc 04, spec-marketplace.md). A **conversation** is a sequence of such calls that share context. Nothing in the marketplace model guarantees the same provider serves turn 2 as served turn 1, and it shouldn't: forcing that would mean picking one provider for the life of a conversation, a single point of failure and a step back from "any qualified provider can serve any job."

The wrong instinct is to make some provider "remember" the conversation. The right instinct, and the one this spec commits to, is: **no provider is ever relied upon to remember anything.** Continuity is a property of the request, not of any one machine's local state.

## 2. Design principles

1. **Canonical history lives with the caller, not with any provider.** The Abakos Chat frontend (or the Developer API caller: an IDE plugin, an app backend) is the source of truth for a thread's messages. This is not a new idea; it's exactly how OpenAI's `/v1/chat/completions` already works, and Abakos' Developer API is OpenAI-compatible by design (Doc 16), so this already works for API callers with zero protocol changes. Abakos Chat's own frontend does the equivalent under the hood.
2. **Any provider can serve any turn.** A new provider receiving a turn gets handed the context it needs (Layer 1) and nothing else is assumed about what it "already knows."
3. **Continuity is provable, not just trusted.** Consistent with the rest of PoFUW (spec-reward-split-impl.md, spec-pouw-integration.md): what a provider claims to have used as context is committed and checkable, the same way job inputs already are for any other funded job.
4. **Context doesn't grow forever.** Long threads get compacted, and compaction is itself an ordinary provable job, not a hidden side-channel outside the reward-split accounting.
5. **Session affinity, if used, is a performance hint, never a correctness dependency.** Routing consecutive turns to the same provider (for KV-cache reuse and lower latency) is allowed and encouraged where it helps, but the system must produce a correct next turn even if that provider is gone by the next message.

## 3. Data model

Extends the existing `Job` structure (spec-marketplace.md §9) with two fields:

```
Job {
  job_id, buyer, model_id,
  input_commitment: bytes32,     // now covers (new_message + context_ref), see §4
  job_type: enum{BATCH, REALTIME, TRAIN},
  thread_id: bytes32?,           // groups turns of one conversation, null for one-off jobs
  parent_job_id: bytes32?,       // previous turn in this thread, null for the first turn
  payment_currency: enum{STABLE, ABA},
  payment_escrow: uint,
  deadline: timestamp,
  status: enum,
  assigned_miner: address?
}
```

`thread_id` and `parent_job_id` are bookkeeping, not trust anchors. Verification never has to "trust" that a `parent_job_id` is legitimate; it only has to check that `input_commitment` for the current turn hashes to context the buyer actually supplied (§4). A thread is just a chain of otherwise-ordinary jobs.

## 4. What actually gets committed and verified

For a chat-turn job, `input_commitment` is a hash over:

```
context_ref  = hash(compacted_summary ∥ last_N_raw_turns)   // see §5
turn_input   = hash(context_ref ∥ new_user_message)
input_commitment = turn_input
```

The buyer's client computes `context_ref` locally (it already has the full thread) and sends both the new message and the context the provider needs to reconstruct `context_ref` (either inline, or as a reference the buyer's own account/gateway can serve, see §7 for the Abakos Chat case). The provider's proof binds its output to `input_commitment`, exactly like any other job (spec-marketplace.md §5, §9). A provider cannot silently drop context to save compute: doing so changes `context_ref` and the commitment no longer matches, so the proof fails verification like any other tampered input.

This makes conversation continuity **portable by construction**: whichever provider receives the committed context can serve the turn identically, because correctness depends on the content of the commitment, not on which machine computed the previous turn.

## 5. Compaction (bounding context growth)

Once a thread's raw history crosses a size threshold (model-context-dependent), older turns are summarized into `compacted_summary`, and only the summary plus the most recent `N` raw turns are carried forward as context. Summarization is **itself an ordinary funded job**: it has an input (the turns being compacted), an output (the summary), and is proven and settled the same way as any other job, so it is accounted for in `useful_ratio` like everything else instead of being an invisible, unpriced side-channel. Buyers can choose `N` and the trigger threshold; the marketplace ships a sane default.

## 6. Sticky routing (optional performance path)

To reuse a provider's KV-cache and cut latency on active conversations, the marketplace **may** prefer routing consecutive turns of the same `thread_id` to the same provider, as long as that provider stays online and responsive, similar in spirit to the hybrid real-time path already used for latency-critical Abakos Chat traffic (Doc 05). This is purely an optimization:

- If the sticky provider is unavailable, slow, or the buyer switches devices, the next turn is served by *any* qualified provider using §4's committed context. There is no conversation loss, at worst a one-time cache-miss cost for that turn (recomputing attention over the resent context instead of reusing a cache).
- Stickiness is never advertised or sold as a guarantee. Any UI or docs describing it must label it "best-effort," consistent with how the hybrid real-time path is already labeled elsewhere on the site.

## 7. Where the "resend context" burden actually sits

Resending growing context every turn is a real cost, but it is not a new problem Abakos invented, and it does not have to sit on the end user:

- **Developer API callers** already resend the messages array themselves; this is standard OpenAI-client behavior, unchanged by Abakos.
- **Abakos Chat** end users never see this. The Chat gateway holds the buyer's thread (encrypted, buyer-owned, exportable/deletable on request) and assembles `context_ref` on their behalf before dispatching each turn to the marketplace. The end user experience is a normal chat UI; the statelessness lives one layer down, in the gateway, not in any GPU provider.

## 8. Privacy property (a side effect worth stating plainly)

Because no provider is ever relied upon to remember a conversation, no single GPU owner accumulates a durable copy of a buyer's full thread just by having served one turn of it. A provider only ever sees the specific context handed to it for the turn(s) it actually processes. Rotating providers is a privacy property of this design, not only a resilience one, and directly answers the natural worry that decentralized inference means "a random GPU owner has my whole chat history."

## 9. What this does not solve yet (honest gaps)

- **Context reference transport for very large threads**: for the API, sending a large `compacted_summary` inline on every request is wasteful; a content-addressed reference (buyer-hosted or gateway-hosted, provider fetches by hash) is the likely production design, not specified here yet.
- **Multi-modal context** (images, files) is out of scope of this draft; the commitment scheme generalizes, but hashing/verification cost for large binary context needs its own pass.
- **Cross-device thread sync** for Abakos Chat (same account, different device mid-conversation) is a product feature, not a protocol one; it falls out naturally once the gateway owns the canonical thread (§7) but isn't built.
- This entire spec is **design, not shipped code**. Batch jobs (Phase 2) ship before real-time/chat jobs (Phase 3–4, Doc 07); session continuity as described here is needed starting when real-time, multi-turn jobs exist, not before.

## 10. Summary

| Question | Answer |
|---|---|
| Where does conversation memory live? | With the caller (Chat gateway or API client), never inside a provider. |
| What if turn 2 goes to a different provider than turn 1? | No problem: the new provider gets the same committed context; nothing was lost. |
| How is correctness enforced, not just trusted? | The turn's job commitment hashes the actual context used; the proof binds output to that hash. |
| What about very long conversations? | Periodic compaction, itself a normal provable job, keeps resent context bounded. |
| Can we still get low latency for long chats? | Optional sticky routing to the same provider for cache reuse, a hint, not a dependency. |
| What if the sticky provider disappears? | Next turn reroutes to any other provider using the committed context; no data loss. |
| Privacy? | No single provider accumulates a full conversation just by serving one turn of it. |
