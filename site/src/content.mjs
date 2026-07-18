export const release = {
  phase: "Phase 0",
  label: "ARCHITECTURE PIVOT",
  summary:
    "Forked-Akash PoS chain with an EVM and a Provider Agent for full hardware utilization: Console deploys plus idle GPU/CPU mining into ABA. A public sandbox test network is live (wallet, explorer, ABA/USDT DEX, EVM chain 9721, Provider Agent dashboard, faucet, zero-fee transactions); mainnet follows after an audit and external validator onboarding.",
  updated: "2026-07-17",
};

// Nav/footer render identically on every host (including the console/chat/
// status subdomains), so every link here must be a full absolute URL -- a
// relative "/docs/" rendered on console.abakos.ai would otherwise point at
// console.abakos.ai/docs/, which doesn't exist.
export const navGroups = [
  {
    label: "Products",
    links: [
      ["Console", "https://console.abakos.ai/"],
      ["Chat", "https://chat.abakos.ai/"],
      ["API", "https://abakos.ai/developers/"],
      ["Wallet", "https://abakos.ai/wallet/"],
    ],
  },
  {
    label: "Network",
    links: [
      ["Protocol", "https://abakos.ai/network/"],
      ["Providers", "https://abakos.ai/providers/"],
      ["Status", "https://status.abakos.ai/"],
      ["Explorer", "https://abakos.ai/explorer/"],
      ["DEX", "https://abakos.ai/dex/"],
      ["Provider Dashboard", "https://abakos.ai/dashboard/"],
    ],
  },
  {
    label: "Resources",
    links: [
      ["Docs", "https://abakos.ai/docs/"],
      ["Investors", "https://abakos.ai/investors/"],
      ["Contact", "https://abakos.ai/contact/"],
    ],
  },
];

export const phases = [
  [
    "Phase 0",
    "Architecture pivot",
    "Forked-Akash PoS design, Provider Agent spec, ABA wallet settlement (no fiat credits yet). Earlier PoUW research is archived, not the live product claim.",
    "development",
  ],
  [
    "Phase 1",
    "Public sandbox testnet (live)",
    "Live: public sandbox chain with an EVM (id 9721), wallet, explorer, ABA/USDT DEX, faucet, Provider Agent + Dashboard, and zero-fee transactions. Single-operator for now; decentralization comes with mainnet.",
    "live",
  ],
  [
    "Phase 2",
    "Console + buyback",
    "Abakos Console with templates, base bundles (CPU+RAM+disk[+GPU]), optional persistent storage and IP leases, ABA escrow, and idle GPU/CPU mining converted into ABA.",
    "planned",
  ],
  [
    "Phase 3",
    "Developer API (batch)",
    "OpenAI-compatible embeddings and completions create visible Console jobs settled in ABA.",
    "planned",
  ],
  [
    "Phase 4",
    "Abakos Chat + API streaming",
    "Consumer demand and streaming API share one real-time job path. Chat adds a product markup for UX and support.",
    "planned",
  ],
  [
    "Launch",
    "Audit and mainnet",
    "External audit, liquidity seeding (~$0.002 / 10B ABA target), and production network. Fiat to ABA onramp (card buy that market-buys ABA) is post-launch, not MVP.",
    "planned",
  ],
];

const faq = (items) => `
  <div class="faq">
    ${items
      .map(
        ([q, a]) => `<details><summary>${q}</summary><p>${a}</p></details>`,
      )
      .join("")}
  </div>`;

const steps = (items) => `
  <div class="steps">
    ${items
      .map(
        ([n, title, text]) => `
          <div class="step">
            <span class="step-index">${n}</span>
            <div><h3>${title}</h3><p>${text}</p></div>
          </div>`,
      )
      .join("")}
  </div>`;

const statusCard = (label, title, text, tone = "planned") => `
  <article class="surface-card">
    <span class="status-badge status-${tone}">${label}</span>
    <h3>${title}</h3>
    <p>${text}</p>
  </article>`;

export const home = {
  title: "Abakos: Maximize what your hardware earns",
  description:
    "Abakos keeps your hardware earning: deploy CPU, RAM, GPU and storage through the Console, or idle-mine GPU and CPU into ABA when nobody is renting.",
  body: `
    <header class="home-hero">
      <canvas id="grid" aria-hidden="true"></canvas>
      <div class="wrap hero-grid">
        <div>
          <div class="hero-status"><span class="status-dot"></span>Phase 0 architecture pivot · Provider Agent and PoS fork in development</div>
          <h1>Hardware that<br><span class="accent-gradient">stays fully used.</span></h1>
          <p class="hero-copy">The goal is maximum income from every machine. Deploy CPU, RAM, GPU and storage through the Console when there is demand. When GPU or CPU would sit idle, the Provider Agent mines the most profitable coin and auto-converts the proceeds into ABA. No empty hours. No minting ABA as a fake subsidy. Buyers pay from an ABA wallet at launch.</p>
          <div class="actions">
            <a class="btn btn-fill" href="https://console.abakos.ai/">Rent compute →</a>
            <a class="btn btn-line" href="/providers/">Maximize your hardware →</a>
          </div>
          <p class="fineprint">Console, Provider Dashboard, Chat and API are in development. See <a href="https://status.abakos.ai/">delivery status</a> for what is live today.</p>
        </div>
        <div class="hero-console" aria-label="Abakos utilization preview">
          <div class="console-head"><span>AGENT · HOST-07</span><span class="status-badge status-development">TARGET UX</span></div>
          <div class="console-row"><span>CPU · RAM · Disk</span><b>rented · Console</b></div>
          <div class="console-row"><span>GPU</span><b class="accent">idle → mining</b></div>
          <div class="console-row"><span>Escrow / payout</span><b>ABA wallet</b></div>
          <div class="console-row"><span>Utilization</span><b class="accent">~100%</b></div>
          <div class="reward-bar"><span style="width:92%"></span></div>
          <div class="console-foot"><span>Rent first · mine when free</span><span>max income</span></div>
        </div>
      </div>
    </header>

    <section class="flow-strip" aria-label="How Abakos keeps hardware earning">
      <div class="wrap flow-grid">
        <span>01 · List hardware</span><i>→</i><span>02 · Rent via Console</span><i>→</i><span>03 · Else mine GPU/CPU</span><i>→</i><span>04 · Earn ABA</span>
      </div>
    </section>

    <section>
      <div class="wrap narrow">
        <div class="notice"><b>New here? The one-minute version.</b><p>Most rental networks leave GPUs and CPUs idle between jobs. Abakos is built so your hardware stays busy: customers deploy CPU, RAM, GPU and storage through the Console, with payment locked in ABA escrow. If GPU or CPU capacity is free, the Provider Agent mines the most profitable coin, auto-converts the proceeds into ABA, and pays you. Storage and RAM earn when rented; they have no mining fallback. Nothing is paid by printing ABA for empty work.</p></div>
      </div>
    </section>

    <section id="paths">
      <div class="wrap">
        <div class="section-label">Choose your path</div>
        <h2>One network. Four ways in.</h2>
        <div class="path-grid">
          <a class="path-card" href="https://console.abakos.ai/"><span>RENT COMPUTE</span><h3>Console: deploy bundles and add-ons</h3><p>Templates and a visual deploy flow priced as CPU+RAM+disk[+GPU]. Optional persistent storage and IP lease. Pay from an ABA wallet.</p><b>Console →</b></a>
          <a class="path-card" href="/developers/"><span>BUILD</span><h3>Change one base URL</h3><p>An OpenAI-compatible API that turns requests into verifiable compute jobs paid in ABA.</p><b>Developer API →</b></a>
          <a class="path-card" href="/providers/"><span>PROVIDE</span><h3>Max income from your box</h3><p>List CPU, RAM, GPU and storage. Rent when demanded; idle-mine GPU/CPU into ABA. Track it in the Provider Dashboard.</p><b>Provider network →</b></a>
          <a class="path-card" href="https://chat.abakos.ai/"><span>USE</span><h3>AI without crypto friction</h3><p>A consumer chat product designed to create real network demand on the same rails.</p><b>Abakos Chat →</b></a>
        </div>
      </div>
    </section>

    <section>
      <div class="wrap split">
        <div>
          <div class="section-label">The mechanism</div>
          <h2>Always utilized. Maximum income.</h2>
          <p class="lede">Demand fills the machine first. Idle GPU and CPU do not sit dark: they mine the most profitable coin, then auto-convert into ABA. Storage and RAM earn on rental only. Chain security uses separate validator staking, not provider inflation.</p>
        </div>
        <div class="economics-panel">
          <div><span>Console rental (CPU, RAM, GPU, storage)</span><b class="accent">ABA</b><small>buyer pays; 3% protocol fee</small></div>
          <div><span>Idle GPU / CPU mining</span><b>88%</b><small>mine best coin → auto-convert to ABA → host</small></div>
          <p>Same machine, same hour: rent what customers want, mine what would otherwise be idle. Mining proceeds are always auto-converted to ABA, with a 12% protocol cut (88% to the host; 4% stakers, 4% treasury, 4% burn). Storage has no mining path; it earns when rented.</p>
        </div>
      </div>
    </section>

    <section>
      <div class="wrap">
        <div class="section-label">The product</div>
        <h2>The Akash product suite, rebuilt for full utilization.</h2>
        <p class="lede">Abakos takes the products Akash proved and runs them on its own chain: the Console for deploys, an OpenAI-compatible API for developers, and Abakos Chat for everyone. They are front doors onto the same job, escrow and ABA wallet rails. The Provider Agent Dashboard is where utilization and earnings show up. Full breakdown: <a href="/network/#how-it-fits-together">how the products fit together</a>.</p>
        <div class="product-system">
          ${statusCard("Phase 2 PLANNED", "Console", "Visual deploy and templates, base bundles, and add-ons (GPU, persistent storage, IP lease) with ABA escrow.")}
          ${statusCard("Phase 3 PLANNED", "Developer API", "OpenAI-shaped batch requests first; streaming lands with Chat at Phase 4.")}
          ${statusCard("Phase 4 PLANNED", "Abakos Chat", "Consumer demand on the same rails, with a product markup for UX and support.")}
          ${statusCard("SANDBOX LIVE", "Provider Agent Dashboard", "Live on the sandbox: rentals first, idle GPU/CPU mining into ABA, 88/4/4/4 split (host / stakers / treasury / burn) paid on-chain. See abakos.ai/dashboard/.")}
          ${statusCard("SANDBOX LIVE", "Explorer", "Live on the sandbox: blocks, validators, supply, and EVM/DEX stats. See abakos.ai/explorer/.")}
        </div>
      </div>
    </section>

    <section>
      <div class="wrap">
        <div class="section-label">Proof, not promises</div>
        <h2>What we are building toward.</h2>
        <div class="proof-grid">
          <div><b>PoS</b><span>Akash-based fork</span></div>
          <div><b>Full use</b><span>rent or mine</span></div>
          <div><b>ABA wallet</b><span>no fiat MVP</span></div>
          <div><b>10B</b><span>fixed genesis supply</span></div>
        </div>
        <p class="source-note">Current status: the public sandbox test network is live (wallet, explorer, ABA/USDT DEX, EVM chain 9721, Provider Agent dashboard, faucet, zero-fee transactions), single-operator for now. Mainnet (external validators, audit, token with real value) and the Console/API/Chat products are not live yet.</p>
      </div>
    </section>

    <section>
      <div class="wrap">
        <div class="section-label">Positioning</div>
        <h2>Same compute rails. Different utilization story.</h2>
        <div class="comparison-grid">
          <div><span>Akash</span><p>Mature Console, Chat, AkashML and Homenode. Idle capacity earns only while it serves inference; otherwise it sits.</p></div>
          <div><span>Vast.ai / io.net</span><p>Easy hourly rental, but idle GPU/CPU hours are usually wasted.</p></div>
          <div><span>Traditional cloud</span><p>Fixed pricing, centralized supply, no path for you to monetize your own hardware.</p></div>
          <div class="featured"><span>Abakos</span><p>The same product suite on our own chain, plus a Provider Agent that mines every idle CPU/GPU hour into ABA. Full utilization, ABA wallet first.</p></div>
        </div>
      </div>
    </section>

    <section>
      <div class="wrap">
        <div class="section-label">Delivery sequence</div>
        <h2>Architecture first. Products follow proof.</h2>
        <div data-roadmap></div>
      </div>
    </section>

    <section>
      <div class="wrap split">
        <div>
          <div class="section-label">Investor proof</div>
          <h2>A measurable infrastructure thesis.</h2>
          <p class="lede">The proof point is not a token narrative alone. A public sandbox test network is already live &mdash; wallet, explorer, ABA/USDT DEX and the Provider Agent buyback are visible on-chain. Mainnet (audit + external validators) is next.</p>
          <div class="actions"><a class="btn btn-line" href="/investors/">Investor overview</a><a class="btn btn-line" href="/network/">Protocol details</a></div>
        </div>
        <div class="milestone-list">
          <div><span>01</span><p><b>Full utilization:</b> rent CPU/RAM/GPU/storage, or mine idle GPU/CPU.</p></div>
          <div><span>02</span><p><b>ABA demand:</b> buyers fund jobs from an ABA wallet.</p></div>
          <div><span>03</span><p><b>No provider mint:</b> pay comes from rentals or converted mining, not inflation.</p></div>
        </div>
      </div>
    </section>

    <section>
      <div class="wrap narrow">
        <div class="section-label">Questions</div>
        <h2>Understand the model.</h2>
        ${faq([
          ["What does \"maximum income\" mean in practice?", "The Provider Agent tries to keep every rentable resource earning. CPU, RAM, GPU and storage can be rented via the Console. If GPU or CPU capacity would sit idle, the Agent mines the most profitable coin, auto-converts the proceeds into ABA (12% protocol cut split 4% stakers / 4% treasury / 4% burn; 88% to the host), and pays the host. Storage and RAM have no mining fallback; they earn when rented."],
          ["How do providers earn if there is no mining subsidy?", "From real paths only. A customer pays ABA for a rental or job, or idle GPU/CPU mining is converted into ABA. Validators and stakers earn from protocol fees and the staker share of the mining and Chat cuts; ABA has zero inflation. Compute hosts are not paid by minting ABA for work."],
          ["What is escrow, in plain terms?", "Escrow is ABA set aside and locked before work starts. The buyer's payment sits untouched until the provider proves delivery, then it is released. That protects both sides: the buyer is not billed for nothing, and the provider is not working on a promise."],
          ["Is the network live?", "Yes - a public sandbox test network is live: wallet, explorer, ABA/USDT DEX (EVM chain 9721), faucet, Provider Agent dashboard and zero-fee transactions, all publicly reachable. ABA on the sandbox has no value. It runs single-operator for now; mainnet adds an external audit, outside validators and a token with real value. We can move from the sandbox straight to mainnet once those are in place."],
          ["How do I rent compute?", "The Console is designed like a modern deploy console: one-click templates or a visual deploy flow, always as resource bundles (vCPU+RAM+disk, optional GPU), paid from an ABA wallet. Optional add-ons include persistent storage and a dedicated IP lease. It is not live yet. See console.abakos.ai for the target design and status.abakos.ai for current status."],
          ["Is everything included in the container price?", "No. The base price covers the CPU+RAM+ephemeral-disk slice (and GPU if you attach one). Persistent storage and IP leases are optional add-ons with their own ABA line items, the same model Akash uses. Default hostnames and exposed ports ride with the base lease."],
          ["Can I supply compute in bulk?", "Yes. The Provider page has a partner track for data centers and GPU cloud operators who want to list capacity at scale. Hosts use the Provider Agent Dashboard."],
          ["Can I buy compute in bulk, as an offtake partner?", "Yes. The Console page has an enterprise track for buyers who want committed monthly volume and a dedicated integration instead of the self-serve listing UI."],
          ["Why ABA wallet only at the start?", "Simplicity. Every paid job creates real ABA demand, and we skip Stripe/credits complexity in the MVP. Fiat to ABA (a card purchase that market-buys ABA, similar in spirit to Akash's credit model) is a post-launch product decision, not \"fiat never.\""],
        ])}
      </div>
    </section>
  `,
};

export const pages = {
  console: {
    title: "Abakos Console",
    description: "Deploy through the Abakos Console: resource bundles plus optional add-ons (GPU, persistent storage, IP lease), settled in ABA.",
    eyebrow: "Product · Planned",
    h1: "The Console. Deploy bundles, add-ons, ABA wallet.",
    lede: "The same deploy experience Akash proved, on our own chain. You never rent \"just a GPU.\" Every deployment is a machine slice: CPU + RAM + disk, optional GPU. On top of that you can pay for add-ons such as persistent storage and a dedicated IP lease. ABA from your wallet sits in escrow. No fiat credits in the MVP.",
    status: ["Phase 2 PLANNED", "planned"],
    primary: ["Join the list", "#waitlist"],
    secondary: ["List your hardware", "/providers/"],
    body: `
      <section><div class="wrap">
        <div class="section-label">Three ways to deploy</div>
        <h2>Templates, programmatic jobs, or a volume deal.</h2>
        <p class="lede">All three run through the same Console rails and the same ABA escrow. The <a href="/developers/">Developer API</a> is not a separate system with its own pricing; it is the programmatic front door: every API call becomes one of the job types below.</p>
        <div class="product-system">
          <div class="surface-card">
            <span class="status-badge status-planned">ON-DEMAND</span>
            <h3>Templates and visual deploy</h3>
            <p>One-click templates (for example Hello World, an agent, an LLM chat) or a visual deploy flow. Every offer is a bundle: vCPU + RAM + disk, optional GPU, one ABA price for the base slice. Add persistent storage or an IP lease when you need them.</p>
          </div>
          <div class="surface-card">
            <span class="status-badge status-planned">FUNDED JOB</span>
            <h3>Batch jobs</h3>
            <p>Describe the job and a deadline, lock ABA in escrow, and it is automatically matched to the cheapest qualified provider available. No waiting for someone to notice and accept it. This is what runs behind the Developer API and Abakos Chat.</p>
          </div>
          <div class="surface-card">
            <span class="status-badge status-planned">OFFTAKE</span>
            <h3>Enterprise volume deal</h3>
            <p>Committed monthly volume at negotiated rates and a dedicated integration, instead of clicking through templates, for buyers who already run recurring inference or training load. Settlement still lands in ABA at the start.</p>
          </div>
        </div>
        <div class="notice"><b>How matching actually works</b><p>Providers do not browse a queue and accept jobs. They list bundle capacity and price once, then stay online. The Console automatically assigns each job to the cheapest active, sufficiently-reliable provider available the instant it is funded. For rentals you can still browse and pick a specific listing yourself; auto-match is just the fast default.</p></div>
        <div class="notice"><b>ABA wallet only at start</b><p>Buyers fund jobs, rentals and add-ons from an ABA wallet. That is deliberate MVP simplicity, not \"fiat never.\" A later fiat to ABA onramp can follow once product and compliance are ready. Protocol fee on Console settlement is 3% (1% staker, 1% burn, 1% treasury).</p></div>
      </div></section>
      <section id="what-you-pay-for"><div class="wrap">
        <div class="section-label">What you pay for</div>
        <h2>Base slice vs optional add-ons.</h2>
        <p class="lede">Not everything is \"free inside the container.\" The Console sells a base resource bundle, then priced extras providers can offer. Same model Akash uses for compute leases, persistent volumes and IP leases.</p>
        <div class="tablewrap">
          <table>
            <thead><tr><th>Product</th><th>Required?</th><th>What you get</th><th>Billed how</th></tr></thead>
            <tbody>
              <tr><td>Base bundle</td><td>Yes</td><td>CPU + RAM + ephemeral disk (container slice)</td><td>ABA / hr or / mo</td></tr>
              <tr><td>GPU</td><td>Optional</td><td>One or more GPUs attached to that same slice</td><td>Usually the expensive line item</td></tr>
              <tr><td>Persistent storage</td><td>Optional</td><td>Volume that survives restarts (HDD / SSD / NVMe class)</td><td>Extra ABA; provider-local for the lease</td></tr>
              <tr><td>IP lease</td><td>Optional</td><td>Dedicated public IPv4 for the lease duration</td><td>Extra ABA (static IP / custom domain)</td></tr>
              <tr><td>Default hostname / ports</td><td>Included</td><td>Access via provider hostname and exposed ports</td><td>In the base compute price</td></tr>
            </tbody>
          </table>
        </div>
        <p class="source-note">Illustrative product catalog. Exact pricing is set by providers. Persistent storage does not replace a global object store; it is lease-scoped on the chosen provider.</p>
        <div class="product-system">
          ${statusCard("IN BASE", "Container + ephemeral disk", "Runs your image. Data can be lost when the lease ends or the container is rebuilt.")}
          ${statusCard("ADD-ON", "Persistent storage", "For databases and model weights that must survive restarts on the same provider.")}
          ${statusCard("ADD-ON", "IP lease", "Static IPv4 when a shared hostname is not enough (custom domains, direct IP, UDP/TCP).")}
          ${statusCard("ADD-ON", "GPU", "Attached to the same CPU/RAM/disk slice. Never sold as a naked card.")}
        </div>
      </div></section>
      <section id="enterprise"><div class="wrap split">
        <div>
          <div class="section-label">Enterprise &amp; offtake partners</div>
          <h2>Buy in bulk without the deploy UI.</h2>
          <p class="lede">Self-serve deploy fits ad-hoc demand. Recurring, high-volume buyers need reserved capacity and a price that reflects commitment. A direct integration, not a shopping cart.</p>
        </div>
        <div class="surface-card">
          <span class="status-badge status-planned">Phase 2 PLANNED</span>
          <h3>Two integration paths</h3>
          <p><b>Reserved capacity:</b> a longer-term lease against the same escrow rails, at a negotiated rate, matched to specific providers or partners.</p>
          <p><b>Direct API offtake:</b> your systems call a dedicated Abakos endpoint automatically; volume settles on the same chain without a human clicking through the Console.</p>
          <div class="actions"><a class="btn btn-fill" href="mailto:info@abakos.ai?subject=Abakos%20enterprise%20offtake">Talk to us about volume</a></div>
        </div>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">Target templates and bundles</div>
        <h2>What deploying will look like.</h2>
        <div class="tablewrap">
          <table>
            <thead><tr><th>Template / listing</th><th>Base bundle</th><th>Add-ons</th><th>Price</th></tr></thead>
            <tbody>
              <tr><td>Hello World (Next.js)</td><td>0.5 vCPU · 512MiB RAM · 512MiB disk</td><td>none</td><td>target: ABA/mo</td></tr>
              <tr><td>LLM Chat (open weights)</td><td>12 vCPU · 32GiB RAM · 160GiB</td><td>1 GPU · persistent disk</td><td>target: ABA/hr</td></tr>
              <tr><td>Public API node</td><td>2 vCPU · 4GiB RAM · 20GiB</td><td>IP lease · persistent disk</td><td>target: ABA/mo</td></tr>
            </tbody>
          </table>
        </div>
        <p class="source-note">Illustrative target design only. No listings, prices or providers are live. Specs always ship as bundles; GPU, persistent storage and IP are optional priced lines.</p>
      </div></section>
      <section><div class="wrap"><div class="section-label">Batch job lifecycle</div><h2>Fund. Verify. Settle.</h2>${steps([
        ["01", "Create", "Pick an AI model and describe exactly what you want done, and by when."],
        ["02", "Fund", "Your ABA is locked in escrow. A job with no money behind it never starts."],
        ["03", "Match", "The Console automatically assigns it to the cheapest active, qualified provider, instantly."],
        ["04", "Prove", "The provider delivers the result plus cryptographic proof that the work actually happened."],
        ["05", "Settle", "ABA payment and the 3% protocol fee become publicly visible."],
      ])}</div></section>
      <section><div class="wrap"><div class="section-label">Supported workloads</div><h2>Ship workload by workload.</h2><p class="lede">Renting a raw GPU for arbitrary code is easy; proving delivery for every workload is not. Abakos ships verification and product coverage workload-by-workload, starting with batch inference and standard rentals.</p><div class="product-system">
        ${statusCard("Phase 2 PLANNED", "Embeddings", "Large batches with clear inputs, outputs and deterministic accounting.")}
        ${statusCard("Phase 2 PLANNED", "Classification", "Structured outputs suitable for verification and retries.")}
        ${statusCard("LATER", "Streaming / arbitrary rental", "Real-time inference and broader rental sessions expand as proof and product coverage grow.")}
      </div></div></section>
      <section><div class="wrap split"><div><div class="section-label">Escrow, in plain terms</div><h2>Your ABA is locked until delivery.</h2><p class="lede">Escrow means your ABA is locked and set aside the moment you rent or fund a job, not sent to the provider yet. It only gets released once the finished work is checked. A real, paid, locked payment is what starts work.</p></div><div class="surface-card"><span class="status-badge status-development">IN DEVELOPMENT</span><h3>What is not live</h3><p>The actual on-chain escrow, per-minute billing, the listing matcher, model registry and settlement are specified but not built yet.</p></div></div></section>
      <section><div class="wrap"><div class="notice"><b>Running a data center or GPU cloud that needs more capacity?</b><p>Data centers, GPU cloud resellers and enterprises with recurring inference or training load can buy in volume through the <a href="#enterprise">enterprise offtake track</a> above. Have spare GPUs to sell instead? See the <a href="https://abakos.ai/providers/">supply-side partner track</a>.</p></div></div></section>
    `,
    segment: "buyer",
  },
  developers: {
    title: "Developer API",
    description: "OpenAI-compatible AI compute routed into the Abakos Console and settled in ABA.",
    eyebrow: "Product · Planned",
    h1: "One base URL. Visible compute.",
    lede: "The same idea as a managed inference API like AkashML, on our own chain: keep familiar OpenAI request shapes and open-weight models, but expose the job and ABA settlement behind each completion. The API is not a separate product from the Console; it is the programmatic way into it.",
    status: ["Phase 3 PLANNED", "planned"],
    primary: ["Join the list", "#waitlist"],
    secondary: ["Open the Console", "https://console.abakos.ai/"],
    body: `
      <section><div class="wrap split"><div><div class="section-label">Quickstart preview</div><h2>Designed for existing tools.</h2><pre class="codeblock"><code>from openai import OpenAI

client = OpenAI(
  base_url="https://api.abakos.ai/v1",
  api_key="abk_..."
)

response = client.embeddings.create(
  model="qwen-embed",
  input=batch
)</code></pre><p class="source-note">Preview only. API keys and models are not issued yet. Billing is planned in ABA.</p></div><div>${steps([
        ["01", "Request", "Use an OpenAI-compatible endpoint."],
        ["02", "Job", "The gateway creates a funded Console job in ABA."],
        ["03", "Auto-match", "The cheapest active, qualified provider is assigned automatically."],
        ["04", "Compute", "The assigned provider processes and proves the work."],
        ["05", "Trace", "The response includes a job reference visible in the explorer."],
      ])}</div></div></section>
      <section><div class="wrap"><div class="section-label">Open models, pay-per-token intent</div><h2>Familiar shapes, open weights.</h2><p class="lede">Like AkashML, the API serves open-weight models (Llama, Qwen, DeepSeek and similar) behind OpenAI-compatible endpoints. Closed frontier models are never falsely claimed. Pricing is metered per request and settled in ABA rather than a fiat balance.</p><div class="product-system">
        ${statusCard("Phase 3 PLANNED", "Embeddings", "The first API workload after Console settlement works.")}
        ${statusCard("Phase 3 PLANNED", "Batch completions", "Open-model completions with asynchronous job tracking.")}
        ${statusCard("Phase 4 PLANNED", "Streaming chat", "Ships together with Abakos Chat, not earlier: both need the same real-time job path.")}
      </div></div></section>
      <section><div class="wrap"><div class="notice"><b>Multi-turn requests, across different providers</b><p>Nothing changes on your side: send the full <code>messages</code> array each call, exactly like any other OpenAI-compatible provider. Underneath, each call can be matched to a different GPU provider without losing context, because the job commits to the exact context used instead of relying on any one provider to remember it. Full design in the technical docs (<code>spec-session-continuity.md</code>). Planned, not live yet.</p></div></div></section>
    `,
    segment: "developer",
  },
  chat: {
    title: "Abakos Chat",
    description: "A simple consumer product designed to create real compute demand on ABA rails.",
    eyebrow: "Product · Planned",
    h1: "AI chat backed by real work.",
    lede: "Abakos Chat is the consumer demand engine, the same idea as Akash Chat: open models, a familiar interface, no login required and no crypto knowledge needed. Underneath, every conversation draws on the same Console rails used by developers, with ABA settlement.",
    status: ["Phase 4 PLANNED", "planned"],
    primary: ["Join the list", "#waitlist"],
    secondary: ["Open the Console", "https://console.abakos.ai/"],
    body: `
      <section><div class="wrap split"><div><div class="section-label">User experience</div><h2>Simple surface. ABA rails underneath.</h2><p class="lede">A familiar chat UI: switch models mid-conversation, toggle a privacy mode, no account required to try it. Console sessions, ABA escrow and settlement underneath. Open models only, no false claims about GPT or Claude availability. Card billing for Chat users is a later layer; MVP settlement stays ABA.</p></div><div class="chat-preview"><div class="chat-line user">Summarize this research folder.</div><div class="chat-line assistant">Matched to an active provider on the Console as a funded job, automatically, traceable across Console and Explorer once live.</div><div class="chat-meta">Illustrative preview · not a live conversation</div></div></div></section>
      <section><div class="wrap"><div class="section-label">Role in the network</div><h2>Demand is protocol infrastructure.</h2><div class="product-system">
        ${statusCard("Phase 4 PLANNED", "Consumer demand", "Turn everyday requests into paid compute volume on the Console.")}
        ${statusCard("Phase 4 PLANNED", "Open models", "Llama, Qwen, DeepSeek and other deployable open weights.")}
        ${statusCard("Phase 4 PLANNED", "Product markup", "+12% product markup split 4% stakers / 4% treasury / 4% burn; provider net matches the Console, then the usual 3% protocol fee applies.")}
      </div></div></section>
      <section><div class="wrap"><div class="notice"><b>Why there's no "waiting for a provider"</b><p>Every message is auto-matched to the cheapest active, sufficiently-reliable provider serving the model you picked, the instant it is sent. Providers do not browse and accept chat messages; they list capacity once and stay active. That is the only way a live chat product works on a marketplace at all.</p></div></div></section>
      <section><div class="wrap"><div class="notice"><b>Doesn't a different GPU each message break the conversation?</b><p>No, by design. Abakos Chat keeps your conversation on our side, not inside any one provider's machine, so any qualified provider can serve any message without losing context. Full design in the technical docs (<code>spec-session-continuity.md</code>). Planned, not live yet.</p></div></div></section>
    `,
    segment: "chat",
  },
  providers: {
    title: "Compute Providers",
    description: "Maximize hardware income: rent CPU, RAM, GPU and storage via the Console, or idle-mine GPU and CPU into ABA.",
    eyebrow: "Supply · Agent + Dashboard in development",
    h1: "Maximum income. Hardware always busy.",
    lede: "The Provider Agent is built for full utilization, the same idea as running an Akash provider or a Homenode, but any idle hour keeps earning. Rent CPU, RAM, GPU and storage through the Console when buyers show up. When GPU or CPU would sit idle, mine the most profitable coin and auto-convert it into ABA. No ABA is minted as a compute subsidy. Buyers pay with ABA wallets at the start.",
    status: ["IN DEVELOPMENT", "development"],
    primary: ["Join the list", "#waitlist"],
    secondary: ["Apply as a partner", "mailto:info@abakos.ai?subject=Abakos%20compute%20partner"],
    body: `
      <section><div class="wrap">
        <div class="section-label">Full utilization</div>
        <h2>Rent first. Mine what would be idle.</h2>
        <p class="lede">Every rentable resource should earn. Demand fills the machine through the Console. Idle GPU and CPU do not go dark. Storage and RAM earn on rental only.</p>
        <div class="product-system">
          <div class="surface-card">
            <span class="status-badge status-planned">PATH 1 · CONSOLE</span>
            <h3>Rent slices and add-ons</h3>
            <p>Buyers pay ABA for the base bundle (CPU+RAM+ephemeral disk), optional GPU, optional persistent storage, and optional IP lease. Price set by your listing or the market. Settlement takes a 3% protocol fee (1% staker, 1% burn, 1% treasury).</p>
          </div>
          <div class="surface-card">
            <span class="status-badge status-planned">PATH 2 · IDLE</span>
            <h3>Mine GPU and CPU → ABA</h3>
            <p>When no paid job needs that GPU or CPU, the Agent mines the most profitable coin, auto-converts the proceeds, and pays you in ABA. Protocol cut is 12% (88% reaches you as ABA; 4% stakers, 4% treasury, 4% burn). Conversion is automatic so hosts always earn the network asset.</p>
          </div>
        </div>
        <div class="economics-panel">
          <div><span>Console rental + add-ons</span><b class="accent">ABA</b><small>bundle · GPU · disk · IP</small></div>
          <div><span>Idle mining path</span><b>88%</b><small>GPU · CPU only</small></div>
          <p><b>Worked example (illustrative, not a promise):</b> an idle GPU mines $10 of the most profitable coin before conversion. After the 12% cut, about $8.80 is auto-converted to ABA for the host. A paid rental can stack base compute plus persistent storage and an IP lease as separate ABA lines, then the 3% Console fee applies. Exact amounts depend on hardware and market rates.</p>
        </div>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">What each resource does</div>
        <h2>Base slice, priced add-ons, idle mining.</h2>
        <p class="lede">Listings expose vCPU + RAM + disk together, with GPU optional. Buyers can also request persistent volumes and IP leases. You price those lines in the Provider Dashboard. Idle GPU/CPU still mine into ABA when free.</p>
        <div class="product-system">
          ${statusCard("Phase 2 PLANNED", "GPU", "Rent attached to a bundle. Idle mining into ABA when free.")}
          ${statusCard("Phase 2 PLANNED", "CPU + RAM", "Core of every slice. CPU can idle-mine; RAM earns on rental only.")}
          ${statusCard("Phase 2 PLANNED", "Ephemeral disk", "Included in the base lease. Not a separate SKU.")}
          ${statusCard("Phase 2 PLANNED", "Persistent storage", "Optional add-on (HDD/SSD/NVMe class). Earns only when rented.")}
          ${statusCard("Phase 2 PLANNED", "IP lease", "Optional dedicated IPv4 add-on. Extra ABA income when buyers need static IPs.")}
          ${statusCard("LATER", "VPS / dedicated", "KVM/cgroups later; GPU MIG on datacenter cards where available.")}
        </div>
      </div></section>
      <section><div class="wrap split">
        <div>
          <div class="section-label">Fixed supply, zero inflation</div>
          <h2>Income from utilization, not from minting.</h2>
          <p class="lede">Many DePIN designs mint tokens to subsidize hosts. Abakos does not. Provider ABA comes from Console rentals or from mining proceeds auto-converted into ABA. ABA has zero inflation: validators and stakers are paid from protocol fees and the staker share of the mining and Chat cuts.</p>
        </div>
        <div class="surface-card">
          <span class="status-badge status-development">DESIGN TARGET</span>
          <h3>Why this matters</h3>
          <p>If hosts were paid by minting ABA for idle hardware, supply would grow whether or not anyone bought compute. Rentals and buyback keep earnings tied to external value while the Agent keeps utilization high.</p>
        </div>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">Provider comparison</div>
        <h2>The same machine hour, paid differently elsewhere.</h2>
        <div class="comparison-grid">
          <div><span>Vast.ai / Akash</span><p>You get paid for the rental. Idle GPU/CPU hours are mostly waste unless they happen to be serving inference.</p></div>
          <div><span>Homenode</span><p>Monetizes idle consumer GPUs, but only when they serve AI inference demand.</p></div>
          <div><span>Generic PoW mining</span><p>Block rewards mint on a schedule whether or not anyone rented useful capacity.</p></div>
          <div class="featured"><span>Abakos</span><p>Rent CPU, RAM, GPU and storage when demanded; idle-mine GPU/CPU into ABA any time. Agent + Dashboard maximize income.</p></div>
        </div>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">Two ways to provide</div>
        <h2>From a single card to a full data center.</h2>
        <div class="product-system">
          ${statusCard("Phase 1 PLANNED", "Independent host", "Install the Provider Agent, open the Provider Dashboard, list one bundle or a small rack, keep control.")}
          ${statusCard("Phase 2 PLANNED", "Compute partner", "Data centers and GPU cloud operators bring many machines at once, with uptime terms and a dedicated technical contact.")}
        </div>
      </div></section>
      <section><div class="wrap"><div class="section-label">Provider path</div><h2>From Agent install to full utilization.</h2>${steps([
        ["Phase 1", "Install Agent + Dashboard", "Run the Provider Agent, connect to the public test network, register hardware, and open the Provider Dashboard."],
        ["Phase 2", "List bundles + add-ons", "Set CPU, RAM, disk, optional GPU, optional persistent storage and IP lease prices. The Console matches rentals automatically when you are the cheapest qualified option."],
        ["Phase 2", "Idle mine", "When GPU or CPU would sit free, the Agent mines the most profitable coin and auto-converts it into ABA."],
        ["Launch", "Operate", "Track utilization, rentals, mining buyback, uptime and reputation in the Provider Dashboard."],
      ])}</div></section>
      <section><div class="wrap"><div class="notice"><b>No job-hunting required</b><p>Once your listing is active, you do not do anything to "get" a job. The matching engine picks the cheapest active, sufficiently-reliable listing for each incoming job automatically. Go inactive any time and routing stops until you are back.</p></div></div></section>
      <section><div class="wrap"><div class="notice"><b>Bringing 50+ GPUs or a data center?</b><p>Compute partners get a dedicated integration contact, minimum-capacity terms and priority placement. Skip the waitlist and <a href="mailto:info@abakos.ai?subject=Abakos%20compute%20partner">email us directly</a> with your available hardware. The waitlist below is for individual hosts listing a machine or two.</p></div></div></section>
    `,
    segment: "provider",
  },
  network: {
    title: "Abakos Network",
    description: "PoS compute chain built for full hardware utilization: Console rentals plus idle GPU/CPU mining into ABA.",
    eyebrow: "Protocol · Phase 0 architecture",
    h1: "PoS rails. Full utilization. ABA settlement.",
    lede: "Abakos forks the open Akash marketplace stack onto its own PoS chain so ABA can capture value. The Provider Agent keeps hardware busy: rent CPU, RAM, GPU and storage via the Console, or idle-mine GPU and CPU into ABA. Buyers pay with ABA wallets at the start. Earlier PoUW research is archived.",
    status: ["Phase 0 PIVOT", "development"],
    primary: ["Read the technical docs", "/docs/"],
    secondary: ["View delivery status", "https://status.abakos.ai/"],
    body: `
      <section><div class="wrap narrow"><div class="notice"><b>Simple version, before the technical detail</b><p>"Consensus" means every validator agrees on what happened and in what order. Abakos uses Proof of Stake for that. Separately, the Provider Agent maximizes income: rent resources through the Console when buyers exist; mine the most profitable coin on idle GPU and CPU and auto-convert it into ABA when they do not. Storage and RAM earn on rental only. Chain security inflation pays validators, not compute hosts. MVP payments are wallet ABA only.</p></div></div></section>
      <section><div class="wrap"><div class="section-label">Architecture path</div><h2>From utilization to settlement.</h2>${steps([
        ["01", "Hold ABA", "Buyers fund rentals and jobs from an ABA wallet. Fiat to ABA onramp is post-launch, not MVP."],
        ["02", "Console demand", "ABA is locked in escrow against a base bundle (CPU+RAM+disk[+GPU]) and any add-ons (persistent storage, IP lease)."],
        ["03", "Agent fills the hour", "Serve the rental or job; if GPU/CPU would sit idle, mine the most profitable coin and auto-convert to ABA instead."],
        ["04", "Settlement", "ABA pays the host for compute and add-ons; protocol fee and burn rules apply on settlement."],
      ])}</div></section>
      <section><div class="wrap split"><div><div class="section-label">Own chain, not a tenant app</div><h2>Why fork instead of deploying on live Akash.</h2><p class="lede">Running as an app on someone else's chain would not give ABA native fee capture, genesis allocation, or validator economics. Abakos forks the open Akash stack (Cosmos SDK + CometBFT, Apache-2.0) onto its own network so ABA is the settlement and staking asset.</p></div><div class="surface-card"><span class="status-badge status-development">IN DESIGN</span><h3>Current honesty</h3><p>The public sandbox (chain, EVM, wallet, explorer, ABA/USDT DEX, faucet, Provider Agent buyback + dashboard, zero-fee) is live. Not yet live: external validators (decentralization), on-chain escrow modules, and the Console. Litepaper and whitepaper on this site match the PoS / Agent thesis; older numbered research notes in the repo are historical.</p></div></div></section>
      <section id="how-it-fits-together"><div class="wrap">
        <div class="section-label">How the products fit together</div>
        <h2>One backend. Products in, Agent out, one window.</h2>
        <p class="lede">There is one underlying system: the PoS chain plus job, escrow and ABA wallet rails. The Console, Developer API, Abakos Chat and Enterprise offtake create demand that fills hardware. The Provider Agent Dashboard keeps supply utilized (rent or mine). Explorer is the public window.</p>
        <div class="tablewrap">
          <table>
            <thead><tr><th>Surface</th><th>Money flow</th><th>Needs the real-time path</th><th>Phase</th></tr></thead>
            <tbody>
              <tr><td>Console (templates + bundles + add-ons)</td><td>In, ABA wallet</td><td>Only for live sessions</td><td>Phase 2</td></tr>
              <tr><td>Console, batch jobs</td><td>In, ABA wallet</td><td>No</td><td>Phase 2</td></tr>
              <tr><td>Enterprise offtake</td><td>In, ABA wallet</td><td>No</td><td>Phase 2, same rails</td></tr>
              <tr><td>Developer API, batch</td><td>In, ABA wallet</td><td>No</td><td>Phase 3</td></tr>
              <tr><td>Developer API, streaming</td><td>In, ABA wallet</td><td>Yes</td><td>Phase 4, with Chat</td></tr>
              <tr><td>Abakos Chat</td><td>In, ABA (+ product markup)</td><td>Yes</td><td>Phase 4</td></tr>
              <tr><td>Provider Agent Dashboard</td><td>Out, ABA to hosts (job or buyback)</td><td>N/A</td><td>Phase 1</td></tr>
              <tr><td>Explorer</td><td>None, public proof only</td><td>N/A</td><td>Public at Phase 1</td></tr>
              <tr><td>Fiat to ABA onramp</td><td>Card → market-buy ABA → escrow</td><td>N/A</td><td>Post-launch, not MVP</td></tr>
            </tbody>
          </table>
        </div>
        <p class="source-note">This is the one table to check for "what can I expect, and from when." Every other page's status badges roll up to this.</p>
      </div></section>
      <section><div class="wrap"><div class="section-label">Token utility</div><h2>What ABA is for.</h2><div class="product-system">
        ${statusCard("MVP", "Pay", "Buyers fund base bundles and add-ons (GPU, persistent storage, IP lease) from an ABA wallet.")}
        ${statusCard("MVP", "Receive", "Hosts earn ABA from rentals, add-ons, or idle GPU/CPU mining converted into ABA.")}
        ${statusCard("DESIGN", "Stake", "Validators stake ABA to secure the PoS chain.")}
        ${statusCard("LATER", "Fiat onramp", "Card purchase market-buys ABA for escrow. Not in the MVP.")}
      </div></div></section>
      <section><div class="wrap"><div class="notice"><b>Why batch API and Enterprise come before Chat, not after</b><p>Developer API batch endpoints and Enterprise offtake reuse the same batch/escrow infrastructure the Console already needs for Phase 2. Chat and streaming need a low-latency real-time job path, which is why they land together at Phase 4.</p></div></div></section>
    `,
  },
  docs: {
    title: "Documentation",
    description: "Technical and product documentation for Abakos.",
    eyebrow: "Resources",
    h1: "Understand the protocol.",
    lede: "Start with the product model, then go deeper into consensus, economics, the Console and delivery status.",
    status: ["CURRENT", "live"],
    primary: ["Read the litepaper", "/litepaper/"],
    secondary: ["Read the whitepaper", "/whitepaper/"],
    body: `
      <section><div class="wrap"><div class="notice"><b>Docs match the current thesis</b><p>Litepaper and whitepaper describe the PoS / Provider Agent / ABA wallet / full-utilization model. Older numbered research notes under the repo may still mention PoUW; treat the website papers and Network / Providers / Investors pages as canonical for the product.</p></div></div></section>
      <section><div class="wrap"><div class="docs-grid">
        <a href="/litepaper/"><span>8 MIN</span><h3>Litepaper</h3><p>Short overview: utilization, the Console, ABA wallet, tokenomics.</p></a>
        <a href="/whitepaper/"><span>DRAFT v0.2</span><h3>Whitepaper</h3><p>Architecture, add-ons, fees, roadmap and risks.</p></a>
        <a href="/network/"><span>PROTOCOL</span><h3>Network overview</h3><p>PoS fork, Agent economics and ABA settlement.</p></a>
        <a href="https://status.abakos.ai/"><span>STATUS</span><h3>Delivery status</h3><p>What is live on the public sandbox, what ships next and the mainnet readiness gates.</p></a>
        <a href="/developers/"><span>PLANNED</span><h3>API preview</h3><p>Request shapes and integration path, not a live API.</p></a>
        <a href="https://console.abakos.ai/"><span>Phase 2 PLANNED</span><h3>Console</h3><p>Templates, base bundles, persistent storage and IP lease add-ons.</p></a>
      </div></div></section>
    `,
  },
  status: {
    title: "Project Status",
    description: "Canonical delivery status for every Abakos product surface, including the mainnet readiness gate: one page, nowhere else.",
    eyebrow: "Status · Updated 17 July 2026",
    h1: "One source of truth.",
    lede: "Everything about what is live on the public sandbox, what is in design, and what mainnet still needs, on this one page. This is the only status page; it lives at status.abakos.ai.",
    status: ["Phase 0 PIVOT", "development"],
    primary: ["Join the list", "#waitlist"],
    secondary: ["Read the docs", "https://abakos.ai/docs/"],
    body: `
      <section><div class="wrap"><div class="section-label">Surfaces</div><h2>Availability by product.</h2><div class="checklist">
        <div><b>Website and waitlist</b><span>LIVE</span></div>
        <div><b>Public sandbox chain + EVM (id 9721), zero-fee</b><span>SANDBOX LIVE</span></div>
        <div><b>Wallet, explorer, ABA/USDT DEX, faucet</b><span>SANDBOX LIVE</span></div>
        <div><b>Provider Agent + Dashboard (buyback)</b><span>SANDBOX LIVE</span></div>
        <div><b>Console: bundles, add-ons, ABA escrow</b><span>Phase 2 PLANNED</span></div>
        <div><b>Developer API</b><span>Phase 3 PLANNED</span></div>
        <div><b>Abakos Chat</b><span>Phase 4 PLANNED</span></div>
        <div><b>Fiat to ABA onramp (card → market-buy ABA)</b><span>POST-LAUNCH</span></div>
      </div><p class="source-note">Machine-readable status: <a href="https://status.abakos.ai/manifest.json">status.abakos.ai/manifest.json</a>. MVP settlement is ABA wallet only.</p></div></section>
      <section><div class="wrap"><div class="section-label">Mainnet readiness gate</div><h2>What mainnet still needs.</h2><p class="lede">The public sandbox already proves the stack end-to-end and is independently reachable. These are the remaining gates before a value-bearing mainnet.</p><div class="checklist">
        <div><b>Public sandbox chain + endpoints (rpc/rest/evm-rpc)</b><span>LIVE</span></div>
        <div><b>Faucet + public explorer</b><span>LIVE</span></div>
        <div><b>Provider Agent + buyback</b><span>LIVE</span></div>
        <div><b>Security audit (EVM + precompiles + DEX)</b><span>Required for mainnet</span></div>
        <div><b>External validators (decentralization)</b><span>Required for mainnet</span></div>
      </div></div></section>
      <section><div class="wrap"><div class="section-label">Sequence</div><h2>Current delivery roadmap.</h2><div data-roadmap></div></div></section>
      <section><div class="wrap"><div class="notice"><b>Public RPC and test tokens are live; fiat credits are not.</b><p>The public sandbox endpoints (rpc / rest / evm-rpc) and faucet test tokens are reachable now. ABA on the sandbox has no value. Fiat credits are intentionally out of MVP scope.</p></div></div></section>
    `,
    segment: "general",
  },
  investors: {
    title: "Investors",
    description: "Abakos thesis: PoS compute, Provider Agent, fixed 10B ABA supply, fees and compute vouchers.",
    eyebrow: "Investor overview · Pre-seed",
    h1: "Compute that pays for itself. An investment thesis you can check against milestones.",
    lede: "Abakos is building a PoS compute network for maximum hardware income: buyers deploy CPU, RAM, GPU and storage via the Console in ABA; idle GPU/CPU mines the most profitable coin and auto-converts into ABA. ABA is not minted as a compute subsidy. Claims below are design targets or named milestones, not live production facts.",
    status: ["PRE-TESTNET", "development"],
    primary: ["Get in touch", "mailto:info@abakos.ai?subject=Abakos%20pre-seed"],
    secondary: ["Read the litepaper", "/litepaper/"],
    body: `
      <section><div class="wrap">
        <div class="section-label">At a glance</div>
        <h2>What you'd actually be committing to.</h2>
        <div class="checklist">
          <div><b>Preferred instrument</b><span>Compute vouchers / grants / strategic capital against a fixed 10B ABA genesis, not a public token sale.</span></div>
          <div><b>Supply</b><span>10B ABA fixed at genesis. No mining emission bucket for providers.</span></div>
          <div><b>Illustrative DEX start</b><span>~$0.002 per ABA (~$20M FDV), with meaningful USDT pool depth rather than dumping the full liquidity bucket.</span></div>
          <div><b>Target raise</b><span>$1.5M pre-seed shaped. Staged option from a smaller first close.</span></div>
        </div>
        <p class="source-note">That's the five-line version. Everything below is the detail behind it, on this page, so you don't have to email us just to get the basics.</p>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">Why now</div>
        <h2>Compute is structurally scarce. Supply is structurally centralized.</h2>
        <p class="lede">AI infrastructure spend keeps climbing while a handful of hyperscalers still control most data-center GPU capacity. That gap is why decentralized compute exists at all. The figures below are third-party category estimates, shown to size the space, not Abakos forecasts.</p>
        <div class="proof-grid">
          <div><b>$700B+</b><span>Projected annual AI infrastructure spend by 2030 (McKinsey estimate)</span></div>
          <div><b>$8.9B → $22.5B</b><span>Decentralized compute market, 2026 to 2030, third-party industry estimate</span></div>
          <div><b>~65%</b><span>Share of data-center GPU capacity held by the top three hyperscalers (SemiAnalysis)</span></div>
          <div><b>Idle waste</b><span>Most rental networks leave GPU/CPU idle hours unmonetized</span></div>
        </div>
        <p class="source-note">Third-party market estimates, not Abakos-specific projections. Cited only to show the category is real.</p>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">The moat</div>
        <h2>The combination, not one feature.</h2>
        <p class="lede">Akash proved the whole product suite: a Console, Chat, a managed inference API (AkashML) and idle consumer-GPU monetization (Homenode). Abakos runs that suite on its own chain and adds a Provider Agent that keeps hardware fully utilized: Console rentals for CPU, RAM, GPU and storage, plus idle GPU/CPU mining auto-converted into ABA, with ABA wallet demand at MVP and Chat/API as demand engines. Fiat to ABA comes later.</p>
        <div class="product-system">
          ${statusCard("DESIGN", "Full utilization", "Rent via Console when demanded; idle-mine GPU/CPU into ABA. No provider inflation.")}
          ${statusCard("Phase 2 PLANNED", "Console + ABA wallet", "Templates and bundles; every paid deploy creates ABA demand. No Stripe in MVP.")}
          ${statusCard("Phase 3-4 PLANNED", "Demand engine", "Developer API and Chat feed work into the same network.")}
        </div>
        <div class="comparison-grid">
          <div><span>Akash</span><p>Full product suite and mature rails. Idle capacity earns only while serving inference; the token is often behind fiat credits.</p></div>
          <div><span>io.net / Vast.ai</span><p>Real rental demand today, but idle GPU/CPU hours are usually wasted.</p></div>
          <div><span>Generic DePIN mining</span><p>Mints tokens to hosts on a schedule, decoupled from real compute demand.</p></div>
          <div class="featured"><span>Abakos</span><p>Own PoS chain, max-income Agent, Console bundles, ABA wallet MVP, idle GPU/CPU mining into ABA, Chat/API demand.</p></div>
        </div>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">Business model</div>
        <h2>Fees on real volume. Not provider minting.</h2>
        <p class="lede">Protocol revenue comes from settlement fees and the Chat product markup. Provider pay comes from buyers or from mining proceeds auto-converted into ABA. There is no inflation: validators and stakers are paid from protocol fees and the staker share of the mining and Chat cuts.</p>
        <div class="tablewrap">
          <table>
            <thead><tr><th>Flow</th><th>Rate</th><th>Split / note</th></tr></thead>
            <tbody>
              <tr><td>Console / API / CPU / Storage settlement</td><td>3%</td><td>1% stakers + 1% burn + 1% treasury</td></tr>
              <tr><td>Idle mining buyback cut</td><td>10%</td><td>90% to host as ABA; 5% stakers + 5% treasury</td></tr>
              <tr><td>Abakos Chat product markup</td><td>+10%</td><td>4% stakers + 3% treasury + 3% burn; provider net matches the Console, then 3% fee</td></tr>
              <tr><td>Inflation</td><td>0%</td><td>Fixed 10B supply; stakers paid from fees + cut shares, not minting</td></tr>
            </tbody>
          </table>
        </div>
        <p class="source-note">Illustrative design targets. Exact parameters will be locked with legal and audit review before mainnet.</p>
        <div class="tablewrap">
          <table>
            <thead><tr><th>Illustrative unit economics, 1 GPU-month</th><th>Assumption</th><th>Gross</th><th>Protocol take</th></tr></thead>
            <tbody>
              <tr><td>Rented hours</td><td>~$0.50/hr, 55% of 730h</td><td>~$200</td><td>3% = ~$6.00</td></tr>
              <tr><td>Idle hours mined to ABA</td><td>~$0.15/hr equiv, 45% of 730h</td><td>~$49</td><td>10% = ~$4.90</td></tr>
              <tr><td>Host keeps</td><td>after fees, both paths</td><td>~$238</td><td></td></tr>
            </tbody>
          </table>
        </div>
        <p class="source-note">Illustrative only, stated assumptions, not a forecast. The point: idle hours are not zero income because the Agent mines and converts them to ABA. Protocol revenue scales with active GPUs and utilization, plus the Chat markup on top.</p>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">Token &amp; genesis</div>
        <h2>10B ABA. Fixed supply. Honest buckets.</h2>
        <p class="lede">There is no mining emission allocation for providers. Liquidity is market infrastructure, not team take. Team tokens vest. DEX start target is about $0.002 (~$20M FDV), with enough USDT depth to trade without dumping the entire liquidity bucket at once.</p>
        <div class="tablewrap">
          <table>
            <thead><tr><th>Allocation bucket</th><th>Share</th><th>Tokens (of 10B)</th><th>Vesting / note</th></tr></thead>
            <tbody>
              <tr><td>Liquidity</td><td>32%</td><td>3.2B</td><td>DEX/CEX market infrastructure; staged seeding</td></tr>
              <tr><td>Treasury</td><td>18%</td><td>1.8B</td><td>Operations, audits, runway</td></tr>
              <tr><td>Ecosystem</td><td>15%</td><td>1.5B</td><td>Grants, integrations, compute vouchers</td></tr>
              <tr><td>Reserve</td><td>15%</td><td>1.5B</td><td>Contingency / strategic</td></tr>
              <tr><td>Team</td><td>12%</td><td>1.2B</td><td>1-year cliff, 3-year linear</td></tr>
              <tr><td>Community</td><td>8%</td><td>800M</td><td>Incentives, education, early users</td></tr>
            </tbody>
          </table>
        </div>
        <p class="source-note">Draft allocation, not final. Legal review before any signed instrument. Older 2.1B / mining-emission tables on archived docs are obsolete.</p>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">The ask</div>
        <h2>$1.5M shaped pre-seed. Runway to public testnet and audit.</h2>
        <div class="economics-panel">
          <div><span>Target raise</span><b>$1.5M</b><small>Pre-seed. Staged option: smaller first close</small></div>
          <div><span>Preferred path</span><b class="accent">Vouchers</b><small>Compute credits / grants over a public SAFT sale narrative</small></div>
          <p>Exact legal instrument is finalized with counsel. The product preference is clear: fund delivery against compute value and a fixed-supply token, not a public speculative sale.</p>
        </div>
        <div class="tablewrap">
          <table>
            <thead><tr><th>Use of funds (12 months, illustrative)</th><th>Estimate</th></tr></thead>
            <tbody>
              <tr><td>Team (3 to 4 people, incl. technical co-founder hire)</td><td>$420k to 660k</td></tr>
              <tr><td>Infrastructure (validators, indexer, chat gateway, partner GPUs)</td><td>$40k to 100k</td></tr>
              <tr><td>Protocol audit (before mainnet)</td><td>$40k to 80k</td></tr>
              <tr><td>Legal (token structure, trademark, ToS/privacy)</td><td>$30k to 60k</td></tr>
              <tr><td>Liquidity seeding + market-making setup</td><td>$10k to 80k</td></tr>
              <tr><td>Marketing / grants / vouchers</td><td>$20k to 50k</td></tr>
              <tr><td><b>Total</b></td><td><b>~$0.8M to 1.5M</b></td></tr>
            </tbody>
          </table>
        </div>
      </div></section>
      <section><div class="wrap">
        <div class="section-label">How this actually works</div>
        <h2>From email to commitment, concretely.</h2>
        <p class="lede">The round is open now and raised on a rolling basis. Everything on this page is already the substance of the deck.</p>
        ${steps([
          ["01", "Get in touch", "Email us or use the button below. You'll get straight answers and the current terms."],
          ["02", "Intro call", "About 30 minutes, no commitment. We answer questions, you decide whether it's a fit."],
          ["03", "Instrument", "Compute voucher, grant, or other counsel-approved structure against the 10B genesis design. Not a public token sale page."],
          ["04", "Pay", "Wire transfer or USDC/USDT to instructions sent after you sign, personally."],
          ["05", "You're in", "Delivery tracked against the public roadmap. Token allocation, if any, follows the signed instrument and vesting rules."],
        ])}
        <div class="actions"><a class="btn btn-fill" href="mailto:info@abakos.ai?subject=Abakos%20pre-seed">Get in touch</a></div>
      </div></section>
      <section><div class="wrap split"><div><div class="section-label">Next proof points</div><h2>Milestones investors can inspect themselves.</h2><p class="lede">Full phase-by-phase roadmap: <a href="https://status.abakos.ai/">status.abakos.ai</a>.</p></div><div class="milestone-list">
        <div><span>01</span><p><b>Public PoS testnet:</b> external validator, explorer, Provider Agent Dashboard.</p></div>
        <div><span>02</span><p><b>Console:</b> first funded ABA job via template or bundle, visible settlement.</p></div>
        <div><span>03</span><p><b>Idle buyback live:</b> mine best coin then auto-convert to ABA, working end to end.</p></div>
        <div><span>04</span><p><b>API demand:</b> a developer request creates an explorer-visible job.</p></div>
        <div><span>05</span><p><b>Audit gate:</b> no mainnet before independent review. Fiat to ABA onramp stays post-launch.</p></div>
      </div></div></section>
      <section><div class="wrap narrow">
        <div class="section-label">Straight answers</div>
        <h2>What investors ask first.</h2>
        ${faq([
          ["Do I need to request a deck?", "No. Everything substantive from a deck is already on this page. Get in touch if you want a downloadable copy to forward, or if you're ready to talk terms."],
          ["Am I buying equity or tokens?", "Default preference is compute vouchers / strategic capital against a fixed-supply ABA design, not a public SAFT marketing page. Exact instrument depends on counsel and check size. Say what you need when you get in touch."],
          ["Do I need a crypto wallet to invest?", "Not to sign or fund. Funding is a normal fiat or stablecoin wire. A wallet address only matters later if token delivery is part of the signed instrument."],
          ["Why not just run an ICO?", "Wrong instrument for this stage. Public token sales draw securities scrutiny in most jurisdictions, and Abakos has no live product or audited token economics yet."],
          ["Why own-chain instead of deploying on Akash?", "So ABA can be the settlement and staking asset with native fee capture, genesis allocation and validator economics. Forking open Akash modules is the technical path; remaining a tenant app would not capture that value."],
          ["Is there provider token inflation?", "No. Providers earn from buyer ABA or from mining proceeds auto-converted into ABA. Validator inflation is separate and small, for chain security only."],
          ["What happened to Proof-of-Useful-Work?", "Earlier PoUW / btcd research is archived. The product thesis is now maximum hardware utilization on a PoS compute chain: Console rentals plus idle GPU/CPU mining into ABA."],
          ["What happens if the testnet timeline slips?", "Any staged second tranche should be gated on publicly verifiable milestones, so a slip delays the next tranche instead of rewriting history."],
          ["Is ABA a security?", "Undetermined and not overclaimed either way. A legal opinion is required before any public sale. Private instruments are structured with counsel so protection does not hinge on a slogan."],
          ["Why is this solo-founder-led right now?", "Because the project is built to reach this stage capital-efficiently before hiring. Team is the largest line item in the use-of-funds table precisely because this round funds a technical co-founder and early engineering hires."],
        ])}
      </div></section>
      <section><div class="wrap"><div class="notice"><b>What this is not</b><p>No token-price forecast, guaranteed GPU return, guaranteed timeline or claim that planned products are already live. Every status badge on this site says exactly what is proven versus planned; this page uses the same rule.</p></div></div></section>
      <section><div class="wrap split">
        <div>
          <div class="section-label">Ready to look closer</div>
          <h2>Two ways to start, neither requires a decision today.</h2>
          <p class="lede">Get in touch if you're ready to talk terms; everything you need is already above. Read the litepaper first if you want the short version before a call.</p>
          <div class="actions"><a class="btn btn-fill" href="mailto:info@abakos.ai?subject=Abakos%20pre-seed">Get in touch</a><a class="btn btn-line" href="/litepaper/">Read the litepaper</a></div>
        </div>
        <div class="surface-card">
          <h3>Not ready to talk terms yet?</h3>
          <p>Follow delivery progress instead, the same public roadmap this page is built on, updated as it happens.</p>
          <div class="actions"><a class="btn btn-line" href="https://status.abakos.ai/">View delivery status</a></div>
        </div>
      </div></section>
    `,
  },
  about: {
    title: "About Abakos",
    description: "Why Abakos exists and how it is being built.",
    eyebrow: "Company",
    h1: "Infrastructure, not a casino.",
    lede: "Abakos is being built around one falsifiable idea: hardware should stay fully utilized, earning from Console rentals (CPU, RAM, GPU, storage) or from idle GPU/CPU mining auto-converted into ABA, without minting ABA as a fake compute subsidy.",
    status: ["BUILDING", "development"],
    primary: ["Read the roadmap", "https://status.abakos.ai/"],
    secondary: ["Contact", "/contact/"],
    body: `<section><div class="wrap narrow"><div class="section-label">Principles</div><h2>Honesty is part of the protocol story.</h2>${steps([
      ["01", "Show current state", "Separate design, testnet and production. Do not claim planned products, or the archived PoUW work, as live."],
      ["02", "Maximize real utilization", "Rent via the Console when demanded; mine idle GPU/CPU into ABA. No provider inflation."],
      ["03", "Use open standards", "Open models, OpenAI-shaped APIs, an auditable fork of open compute rails."],
      ["04", "Gate mainnet", "Testnet, audit and legal review before real economic launch."],
    ])}</div></section>`,
  },
  contact: {
    title: "Contact",
    description: "Reach the right Abakos contact: general, enterprise, provider or investor.",
    eyebrow: "Get in touch",
    h1: "Talk to the right person.",
    lede: "One inbox, routed by intent. Pick the row that matches you: everything else is the same info@abakos.ai address with a clear subject.",
    status: ["LIVE", "live"],
    body: `
      <section><div class="wrap">
        <div class="tablewrap">
          <table>
            <thead><tr><th>You are</th><th>Best path</th><th></th></tr></thead>
            <tbody>
              <tr><td>Renting compute, day to day</td><td>Console waitlist</td><td><a class="btn btn-line" href="https://console.abakos.ai/#waitlist">Console waitlist</a></td></tr>
              <tr><td>Buying compute in volume</td><td>Enterprise / offtake track</td><td><a class="btn btn-line" href="mailto:info@abakos.ai?subject=Abakos%20enterprise%20offtake">Email</a></td></tr>
              <tr><td>Running a GPU or two</td><td>Provider waitlist</td><td><a class="btn btn-line" href="/providers/#waitlist">Provider waitlist</a></td></tr>
              <tr><td>Running a data center or 50+ GPUs</td><td>Compute partner track</td><td><a class="btn btn-line" href="mailto:info@abakos.ai?subject=Abakos%20compute%20partner">Email</a></td></tr>
              <tr><td>Building on the API</td><td>Developer waitlist</td><td><a class="btn btn-line" href="/developers/#waitlist">Developer waitlist</a></td></tr>
              <tr><td>Investing or diligence</td><td>Investor overview (tokenomics, fees, process)</td><td><a class="btn btn-line" href="/investors/">Investor overview</a></td></tr>
              <tr><td>Press, security or general</td><td>Direct email</td><td><a class="btn btn-line" href="mailto:info@abakos.ai">Email</a></td></tr>
            </tbody>
          </table>
        </div>
        <p class="source-note">Every path reaches the same small team today. Response times will be published once support is a dedicated function, not a founder inbox.</p>
      </div></section>
      <section><div class="wrap split">
        <div>
          <div class="section-label">Community</div>
          <h2>Public, real-time, unmoderated hype.</h2>
          <p class="lede">Discord is where delivery updates, testnet status and honest questions get answered fastest, including "is X actually live yet?"</p>
        </div>
        <div class="surface-card">
          <span class="status-badge status-live">LIVE</span>
          <h3>Discord</h3>
          <p>Product updates, testnet status and direct access to the team.</p>
          <div class="actions"><a class="btn btn-fill" href="https://discord.gg/zBxNvdMjtM" target="_blank" rel="noopener">Join the Discord</a></div>
        </div>
      </div></section>
      <section><div class="wrap"><div class="notice"><b>Security disclosure</b><p>Found a vulnerability in the node, consensus or website? Email <a href="mailto:info@abakos.ai?subject=Security%20disclosure">info@abakos.ai</a> with subject "Security disclosure." Do not open a public issue first.</p></div></div></section>
    `,
  },
  privacy: {
    title: "Privacy",
    description: "Abakos website privacy notice.",
    eyebrow: "Legal · Draft",
    h1: "Privacy notice.",
    lede: "A plain-language interim notice for the current website and waitlist.",
    status: ["DRAFT", "development"],
    body: `<section><div class="wrap narrow legal-copy"><h2>Current data collection</h2><p>The current site collects email addresses submitted voluntarily through segmented waitlists, together with submission time, segment, referring path and IP address for abuse prevention.</p><h2>Purpose</h2><p>Data is used to respond to product interest, testnet participation, provider onboarding and investor enquiries. It is not sold.</p><h2>Retention and contact</h2><p>Before production products launch, this notice will be replaced by reviewed terms covering accounts, billing and compute inputs. Contact <a href="mailto:info@abakos.ai">info@abakos.ai</a> for access or deletion requests.</p></div></section>`,
  },
  terms: {
    title: "Terms",
    description: "Abakos website terms.",
    eyebrow: "Legal · Draft",
    h1: "Website terms.",
    lede: "The current website is informational and does not execute financial or GPU transactions.",
    status: ["DRAFT", "development"],
    body: `<section><div class="wrap narrow legal-copy"><h2>No production service</h2><p>The Console, API, Chat, tokens and public testnet access are not currently offered as production services. Illustrative figures, listings and prices shown on this site are target designs, not live offers.</p><h2>No financial advice</h2><p>ABA parameters and timelines are drafts. Nothing on this site is an offer, investment recommendation or guarantee of returns.</p><h2>Contact</h2><p>Questions may be sent to <a href="mailto:info@abakos.ai">info@abakos.ai</a>.</p></div></section>`,
  },
};

export const sharedFaq = faq;
