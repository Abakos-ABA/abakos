//! Dual-mining orchestration.
//!   CPU = xmrig (RandomX / Monero) through the Abakos stratum proxy, login = the
//!         user's ABA address, so the proxy attributes verified shares to it.
//!   GPU = SRBMiner-MULTI (PearlHash / Pearl), primary pool = the same Abakos proxy
//!         (it auto-detects the Pearl dialect and attributes VERIFIED per-address GPU
//!         shares); failover = the project Kryptex account if the proxy is unreachable.
//! Both run in parallel. Binaries are downloaded on first run. Stats come from each
//! miner's local HTTP API.

use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::Manager;

const POOL_HOST: &str = "mine.abakos.ai";
const POOL_PORT: u16 = 3355;
const XMRIG_API_PORT: u16 = 16000;
const SRB_API_PORT: u16 = 21555;
const PRL_POOL: &str = "prl.kryptex.network:7048";
/// Kryptex account that receives the mined value (auto-exchanged to USDT).
fn kryptex_user() -> String {
    std::env::var("ABA_KRYPTEX_USER").unwrap_or_else(|_| "krxXP93EGN".to_string())
}

pub struct Inner {
    pub cpu: Option<Child>,
    pub gpu: Option<Child>,
    pub status: String, // "stopped" | "starting" | "running" | "error"
    pub error: Option<String>,
    pub address: Option<String>,
    pub pool: String,
}

impl Default for Inner {
    fn default() -> Self {
        Inner {
            cpu: None,
            gpu: None,
            status: "stopped".into(),
            error: None,
            address: None,
            pool: format!("{POOL_HOST}:{POOL_PORT}"),
        }
    }
}

#[derive(Default)]
pub struct MinerState(pub Arc<Mutex<Inner>>);

#[derive(Serialize, Clone)]
pub struct Status {
    pub state: String,
    pub error: Option<String>,
    pub address: Option<String>,
    pub pool: String,
    pub cpu_running: bool,
    pub gpu_running: bool,
    pub cpu_hashrate: f64, // H/s (RandomX)
    pub gpu_hashrate: f64, // H/s (PearlHash)
    pub shares_good: u64,  // CPU accepted shares (xmrig)
    pub shares_total: u64,
    pub gpu_shares_good: u64, // GPU accepted shares (SRBMiner)
}

pub fn start(
    app: tauri::AppHandle,
    inner: &Arc<Mutex<Inner>>,
    address: String,
    threads: u32,
    cpu: bool,
    gpu: bool,
) -> Result<(), String> {
    if !address.starts_with("abakos1") {
        return Err("address must be an abakos1 address".into());
    }
    if !cpu && !gpu {
        return Err("enable CPU and/or GPU".into());
    }
    {
        let mut g = inner.lock().map_err(|_| "lock poisoned")?;
        if g.cpu.is_some() || g.gpu.is_some() {
            return Err("miner already running".into());
        }
        g.status = "starting".into();
        g.error = None;
        g.address = Some(address.clone());
    }
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let arc = inner.clone();
    std::thread::spawn(move || {
        let mut err: Option<String> = None;
        if cpu {
            match run_cpu(&data_dir, &address, threads) {
                Ok(c) => {
                    if let Ok(mut g) = arc.lock() {
                        g.cpu = Some(c);
                    }
                }
                Err(e) => err = Some(format!("cpu: {e}")),
            }
        }
        if gpu {
            match run_gpu(&data_dir, &address) {
                Ok(c) => {
                    if let Ok(mut g) = arc.lock() {
                        g.gpu = Some(c);
                    }
                }
                Err(e) => {
                    let m = format!("gpu: {e}");
                    err = Some(match err {
                        Some(p) => format!("{p}; {m}"),
                        None => m,
                    });
                }
            }
        }
        if let Ok(mut g) = arc.lock() {
            g.error = err;
            g.status = if g.cpu.is_some() || g.gpu.is_some() {
                "running".into()
            } else {
                "error".into()
            };
        }
    });
    Ok(())
}

pub fn stop(inner: &Arc<Mutex<Inner>>) -> Result<(), String> {
    {
        let mut g = inner.lock().map_err(|_| "lock poisoned")?;
        for child in [g.cpu.take(), g.gpu.take()].into_iter().flatten() {
            let mut child = child;
            let _ = child.kill();
            let _ = child.wait();
        }
        g.status = "stopped".into();
        g.error = None;
    }
    // Outside the lock (netstat/taskkill can be slow). Kill by API port AND by
    // executable name so Stop always halts everything: duplicates, miners from a
    // previous session, and any that never bound their API port.
    kill_on_port(XMRIG_API_PORT);
    kill_on_port(SRB_API_PORT);
    kill_process_name(xmrig_proc());
    kill_process_name(srbminer_proc());
    Ok(())
}

pub fn status(inner: &Arc<Mutex<Inner>>) -> Status {
    let (st, err, addr, pool, tracked_cpu, tracked_gpu) = {
        let mut g = match inner.lock() {
            Ok(g) => g,
            Err(_) => {
                return Status {
                    state: "error".into(),
                    error: Some("lock poisoned".into()),
                    address: None,
                    pool: format!("{POOL_HOST}:{POOL_PORT}"),
                    cpu_running: false,
                    gpu_running: false,
                    cpu_hashrate: 0.0,
                    gpu_hashrate: 0.0,
                    shares_good: 0,
                    shares_total: 0,
                    gpu_shares_good: 0,
                }
            }
        };
        let cpu_done = g.cpu.as_mut().map(|c| matches!(c.try_wait(), Ok(Some(_)))).unwrap_or(false);
        if cpu_done {
            g.cpu = None;
        }
        let gpu_done = g.gpu.as_mut().map(|c| matches!(c.try_wait(), Ok(Some(_)))).unwrap_or(false);
        if gpu_done {
            g.gpu = None;
        }
        (g.status.clone(), g.error.clone(), g.address.clone(), g.pool.clone(), g.cpu.is_some(), g.gpu.is_some())
    };

    // Query the miner APIs regardless of whether *this* session spawned the miners.
    // A miner can outlive the window (a UI reload) or the whole app (it keeps hashing
    // after the window closes), leaving the child handle gone but the process alive.
    // Trusting only the handle would show 0; querying the API surfaces the real stats.
    let (mut chr, mut sg, mut stot) = (0.0, 0u64, 0u64);
    let cpu_api = match query_xmrig() {
        Ok(v) => {
            chr = v.0;
            sg = v.1;
            stot = v.2;
            true
        }
        Err(_) => false,
    };
    let (mut ghr, mut gsg) = (0.0, 0u64);
    let mut err = err;
    let gpu_api = match query_srbminer() {
        Ok(v) => {
            ghr = v.0;
            gsg = v.1;
            true
        }
        // Only surface a GPU error when a GPU miner is supposed to be up (we started
        // one); otherwise a refused connection just means no GPU miner is running.
        Err(e) => {
            if tracked_gpu && err.is_none() {
                err = Some(format!("gpu stats: {e}"));
            }
            false
        }
    };

    let cpu_up = tracked_cpu || cpu_api;
    let gpu_up = tracked_gpu || gpu_api;

    // keep the stored status coherent with what's actually running
    if let Ok(mut g) = inner.lock() {
        if cpu_up || gpu_up {
            g.status = "running".into();
        } else if g.status == "running" {
            g.status = "stopped".into();
        }
    }

    Status {
        state: if cpu_up || gpu_up { "running".into() } else { st },
        error: err,
        address: addr,
        pool,
        cpu_running: cpu_up,
        gpu_running: gpu_up,
        cpu_hashrate: chr,
        gpu_hashrate: ghr,
        shares_good: sg,
        shares_total: stot,
        gpu_shares_good: gsg,
    }
}

// ------------------------------------------------------------------ CPU (xmrig)
fn run_cpu(data_dir: &Path, address: &str, threads: u32) -> Result<Child, String> {
    let bin = ensure_binary(
        data_dir,
        "xmrig",
        if cfg!(windows) { "xmrig.exe" } else { "xmrig" },
        xmrig_asset,
    )?;
    let rig = &address[..address.len().min(24)];
    let tag: String = address.chars().skip(7).take(10).filter(|c| c.is_ascii_alphanumeric()).collect();
    let cfg = serde_json::json!({
        "autosave": false,
        "http": { "enabled": true, "host": "127.0.0.1", "port": XMRIG_API_PORT, "access-token": serde_json::Value::Null, "restricted": true },
        "cpu": { "enabled": true },
        "randomx": { "1gb-pages": false },
        "pools": [
            {
                // Primary: the Abakos proxy attributes verified shares to the ABA address.
                "url": format!("{POOL_HOST}:{POOL_PORT}"),
                "user": address,
                "pass": "x",
                "rig-id": rig,
                "keepalive": true,
                "tls": false,
                "algo": "rx/0"
            },
            {
                // Failover: mine straight to Kryptex if the proxy is unreachable, so
                // the machine keeps earning (attribution resumes once the proxy is up).
                "url": "xmr.kryptex.network:7029",
                "user": format!("{}.cpu{}", kryptex_user(), if tag.is_empty() { "abk".into() } else { tag }),
                "pass": "x",
                "keepalive": true,
                "tls": false,
                "algo": "rx/0"
            }
        ]
    });
    let cfg_path = data_dir.join("xmrig-abakos.json");
    std::fs::write(&cfg_path, serde_json::to_vec_pretty(&cfg).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    // clear any stray/duplicate xmrig (this session, a previous one, or a failed
    // API-port bind) before starting fresh, so we never end up with two CPU miners
    kill_process_name(xmrig_proc());
    kill_on_port(XMRIG_API_PORT);
    let mut cmd = Command::new(&bin);
    cmd.arg("-c").arg(&cfg_path);
    if threads > 0 {
        cmd.arg("-t").arg(threads.to_string());
    }
    hidden(&mut cmd);
    cmd.spawn().map_err(|e| format!("failed to start xmrig: {e}"))
}

// ------------------------------------------------------------------ GPU (SRBMiner)
fn run_gpu(data_dir: &Path, address: &str) -> Result<Child, String> {
    let bin = ensure_binary(
        data_dir,
        "srbminer",
        if cfg!(windows) { "SRBMiner-MULTI.exe" } else { "SRBMiner-MULTI" },
        srbminer_asset,
    )?;
    let tag: String = address.chars().skip(7).take(10).filter(|c| c.is_ascii_alphanumeric()).collect();
    let worker = format!("gpu{}", if tag.is_empty() { "abk".into() } else { tag });
    // clear any stray/duplicate SRBMiner before starting fresh
    kill_process_name(srbminer_proc());
    kill_on_port(SRB_API_PORT);
    // Primary: the Abakos proxy (same host/port as CPU; it auto-detects the Pearl
    // dialect and attributes VERIFIED GPU shares to the ABA address). Failover: mine
    // straight to Kryptex so the GPU keeps earning if the proxy is unreachable.
    let proxy_pool = format!("{POOL_HOST}:{POOL_PORT}");
    let kryptex_wallet = format!("{}.{}", kryptex_user(), worker);
    let mut cmd = Command::new(&bin);
    cmd.args([
        // pearlhash is a GPU algorithm: it MUST be passed via --algorithm-gpu.
        // Using plain --algorithm (the CPU-algo switch) makes SRBMiner crash.
        "--algorithm-gpu", "pearlhash",
        // SRBMiner failover: comma-separated pools + matching wallets (positional).
        "--pool", &format!("{proxy_pool},{PRL_POOL}"),
        "--wallet", &format!("{address},{kryptex_wallet}"),
        "--password", "x,x",
        "--disable-cpu",
        "--api-enable",
        "--api-port", &SRB_API_PORT.to_string(),
    ]);
    // Capture output to a log so we can explain a fast GPU failure (SRBMiner exits
    // within ~1-2s on driver/OpenCL/no-GPU errors) instead of failing silently.
    let log_path = data_dir.join("srbminer.log");
    let (out, errout) = match std::fs::File::create(&log_path) {
        Ok(f) => match f.try_clone() {
            Ok(f2) => (Stdio::from(f), Stdio::from(f2)),
            Err(_) => (Stdio::null(), Stdio::null()),
        },
        Err(_) => (Stdio::null(), Stdio::null()),
    };
    cmd.stdout(out).stderr(errout);
    no_window(&mut cmd);
    let mut child = cmd.spawn().map_err(|e| format!("failed to start SRBMiner: {e}"))?;
    // If it dies almost immediately, surface WHY (GPU/driver problem) to the UI.
    std::thread::sleep(std::time::Duration::from_millis(3500));
    if let Ok(Some(code)) = child.try_wait() {
        let logtxt = std::fs::read_to_string(&log_path).unwrap_or_default();
        let low = logtxt.to_lowercase();
        let hint = if logtxt.trim().is_empty() {
            "GPU miner crashed on launch with no output (access violation). This is almost always a GPU-driver incompatibility \u{2014} e.g. a very new NVIDIA/AMD driver the miner doesn't support yet. Roll back to a stable driver (or wait for a miner update). CPU mining is unaffected."
        } else if low.contains("no gpu") || low.contains("no compatible") || low.contains("no opencl") || low.contains("no cuda") {
            "no usable GPU detected \u{2014} update/repair GPU drivers and disable any old/broken secondary GPU (e.g. Fermi/Quadro)"
        } else {
            "SRBMiner exited on startup"
        };
        let tail = logtxt
            .lines()
            .filter(|l| !l.trim().is_empty())
            .collect::<Vec<_>>();
        let tail = tail.iter().rev().take(3).rev().cloned().collect::<Vec<_>>().join(" | ");
        return Err(format!("{hint} [{code}]: {tail}"));
    }
    Ok(child)
}

fn hidden(cmd: &mut Command) {
    cmd.stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null());
    no_window(cmd);
}

/// Suppress the console window on Windows without discarding stdout (so callers that
/// need to read command output, e.g. netstat, still can).
fn no_window(cmd: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    #[cfg(not(windows))]
    {
        let _ = cmd;
    }
}

/// Best-effort: terminate whatever process is LISTENING on `port`. Used to clear a
/// stray/orphaned miner (from a previous run) that still owns one of our fixed API
/// ports, so a fresh start doesn't collide and Stop reliably halts everything. Only
/// our own miners bind these uncommon ports, so this won't touch unrelated software.
#[cfg(windows)]
fn kill_on_port(port: u16) {
    let mut ns = Command::new("netstat");
    ns.args(["-ano", "-p", "tcp"]);
    no_window(&mut ns);
    let out = match ns.output() {
        Ok(o) => o,
        Err(_) => return,
    };
    let text = String::from_utf8_lossy(&out.stdout);
    let needle = format!(":{port}");
    let mut pids: Vec<String> = Vec::new();
    for line in text.lines() {
        if line.contains(&needle) && line.to_uppercase().contains("LISTENING") {
            if let Some(pid) = line.split_whitespace().last() {
                if pid != "0" && pid.chars().all(|c| c.is_ascii_digit()) && !pids.iter().any(|p| p == pid) {
                    pids.push(pid.to_string());
                }
            }
        }
    }
    for pid in pids {
        let mut tk = Command::new("taskkill");
        tk.args(["/F", "/PID", &pid]);
        no_window(&mut tk);
        let _ = tk.output();
    }
}

#[cfg(not(windows))]
fn kill_on_port(port: u16) {
    if let Ok(out) = Command::new("lsof").args(["-ti", &format!("tcp:{port}")]).output() {
        for pid in String::from_utf8_lossy(&out.stdout).split_whitespace() {
            let _ = Command::new("kill").arg("-9").arg(pid).output();
        }
    }
}

/// Executable names of the miners we launch, so we can force-kill by image name.
fn xmrig_proc() -> &'static str {
    if cfg!(windows) { "xmrig.exe" } else { "xmrig" }
}
fn srbminer_proc() -> &'static str {
    if cfg!(windows) { "SRBMiner-MULTI.exe" } else { "SRBMiner-MULTI" }
}

/// Force-kill EVERY process with this executable name (and its children). The app
/// owns mining on this machine, so this reliably stops miners even when we no longer
/// hold their child handle (a previous session) or a duplicate never bound its API
/// port -- cases the handle/port cleanup alone missed, leaving miners running.
fn kill_process_name(name: &str) {
    #[cfg(windows)]
    {
        let mut c = Command::new("taskkill");
        c.args(["/F", "/T", "/IM", name]);
        no_window(&mut c);
        let _ = c.output();
    }
    #[cfg(not(windows))]
    {
        let _ = Command::new("pkill").arg("-x").arg(name).output();
    }
}

// ------------------------------------------------------------------ downloads
fn ensure_binary(
    data_dir: &Path,
    subdir: &str,
    exe: &str,
    asset: fn() -> Result<(String, String), String>,
) -> Result<PathBuf, String> {
    let root = data_dir.join(subdir);
    std::fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    if let Some(p) = find_file(&root, exe) {
        return Ok(p);
    }
    let (url, name) = asset()?;
    let archive = root.join(&name);
    download(&url, &archive)?;
    extract(&archive, &root)?;
    let p = find_file(&root, exe).ok_or_else(|| format!("{exe} not found after extract"))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perm = std::fs::metadata(&p).map_err(|e| e.to_string())?.permissions();
        perm.set_mode(0o755);
        std::fs::set_permissions(&p, perm).map_err(|e| e.to_string())?;
    }
    Ok(p)
}

fn gh_latest_asset(repo: &str, wants: &[&str], exts: &[&str]) -> Result<(String, String), String> {
    let c = http_client(30)?;
    let rel: serde_json::Value = c
        .get(format!("https://api.github.com/repos/{repo}/releases/latest"))
        .header("User-Agent", "abakos-provider")
        .header("Accept", "application/vnd.github+json")
        .send()
        .map_err(|e| e.to_string())?
        .json()
        .map_err(|e| e.to_string())?;
    let assets = rel.get("assets").and_then(|a| a.as_array()).ok_or("no release assets")?;
    for w in wants {
        for a in assets {
            let n = a.get("name").and_then(|x| x.as_str()).unwrap_or("");
            let nl = n.to_lowercase();
            if nl.contains(w) && exts.iter().any(|e| nl.ends_with(e)) {
                if let Some(u) = a.get("browser_download_url").and_then(|x| x.as_str()) {
                    return Ok((u.to_string(), n.to_string()));
                }
            }
        }
    }
    Err(format!("no matching asset in {repo}"))
}

fn xmrig_asset() -> Result<(String, String), String> {
    let wants: &[&str] = if cfg!(windows) {
        &["windows-x64", "msvc-win64", "win64"]
    } else if cfg!(target_os = "macos") {
        if cfg!(target_arch = "aarch64") { &["macos-arm64"] } else { &["macos-x64"] }
    } else if cfg!(target_arch = "aarch64") {
        &["linux-static-arm64", "linux-arm64"]
    } else {
        &["linux-static-x64", "linux-x64"]
    };
    gh_latest_asset("xmrig/xmrig", wants, &[".zip", ".tar.gz"])
}

fn srbminer_asset() -> Result<(String, String), String> {
    let wants: &[&str] = if cfg!(windows) { &["win64"] } else { &["linux"] };
    gh_latest_asset("doktor83/SRBMiner-Multi", wants, &[".zip", ".tar.gz"])
}

fn http_client(secs: u64) -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(secs))
        .build()
        .map_err(|e| e.to_string())
}

fn download(url: &str, dest: &Path) -> Result<(), String> {
    let c = http_client(300)?;
    let bytes = c
        .get(url)
        .header("User-Agent", "abakos-provider")
        .send()
        .map_err(|e| e.to_string())?
        .bytes()
        .map_err(|e| e.to_string())?;
    std::fs::write(dest, &bytes).map_err(|e| e.to_string())
}

fn extract(archive: &Path, into: &Path) -> Result<(), String> {
    let name = archive.to_string_lossy().to_lowercase();
    if name.ends_with(".zip") {
        let f = std::fs::File::open(archive).map_err(|e| e.to_string())?;
        let mut zip = zip::ZipArchive::new(f).map_err(|e| e.to_string())?;
        zip.extract(into).map_err(|e| e.to_string())?;
    } else {
        let f = std::fs::File::open(archive).map_err(|e| e.to_string())?;
        let gz = flate2::read::GzDecoder::new(f);
        let mut ar = tar::Archive::new(gz);
        ar.unpack(into).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn find_file(root: &Path, name: &str) -> Option<PathBuf> {
    let rd = std::fs::read_dir(root).ok()?;
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            if let Some(f) = find_file(&p, name) {
                return Some(f);
            }
        } else if p.file_name().and_then(|x| x.to_str()) == Some(name) {
            return Some(p);
        }
    }
    None
}

// ------------------------------------------------------------------ stats
fn query_xmrig() -> Result<(f64, u64, u64), String> {
    let c = http_client(4)?;
    let v: serde_json::Value = c
        .get(format!("http://127.0.0.1:{XMRIG_API_PORT}/2/summary"))
        .send()
        .map_err(|e| e.to_string())?
        .json()
        .map_err(|e| e.to_string())?;
    let hr = v.pointer("/hashrate/total/0").and_then(|x| x.as_f64()).unwrap_or(0.0);
    let sg = v.pointer("/results/shares_good").and_then(|x| x.as_u64()).unwrap_or(0);
    let stot = v.pointer("/results/shares_total").and_then(|x| x.as_u64()).unwrap_or(0);
    Ok((hr, sg, stot))
}

fn query_srbminer() -> Result<(f64, u64), String> {
    let c = http_client(4)?;
    let v: serde_json::Value = c
        .get(format!("http://127.0.0.1:{SRB_API_PORT}/"))
        .send()
        .map_err(|e| e.to_string())?
        .json()
        .map_err(|e| e.to_string())?;
    // SRBMiner-MULTI shape: /algorithms/0/hashrate/now (total, H/s). Fall back to
    // summing per-GPU entries under /algorithms/0/hashrate/gpu, then the legacy field.
    let hr = v
        .pointer("/algorithms/0/hashrate/now")
        .and_then(|x| x.as_f64())
        .or_else(|| {
            v.pointer("/algorithms/0/hashrate/gpu")
                .and_then(|g| g.as_object())
                .map(|gpus| gpus.values().filter_map(|x| x.as_f64()).sum::<f64>())
        })
        .or_else(|| v.pointer("/hashrate_total_now").and_then(|x| x.as_f64()))
        .unwrap_or(0.0);
    let shares = v
        .pointer("/algorithms/0/shares/accepted")
        .and_then(|x| x.as_u64())
        .or_else(|| v.pointer("/shares/accepted").and_then(|x| x.as_u64()))
        .unwrap_or(0);
    Ok((hr, shares))
}
