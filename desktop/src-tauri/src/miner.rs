//! Dual-mining orchestration.
//!   CPU = xmrig (RandomX / Monero) through the Abakos stratum proxy, login = the
//!         user's ABA address, so the proxy attributes verified shares to it.
//!   GPU = SRBMiner-MULTI (PearlHash / Pearl) to Kryptex. Pearl is GPU-only and not
//!         relayed by the proxy yet, so it mines to the project Kryptex account
//!         (auto-exchanged to USDT); per-address GPU attribution is a later step.
//! Both run in parallel. Binaries are downloaded on first run. Stats come from each
//! miner's local HTTP API.

use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::{Manager, State};

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
}

pub fn start(
    app: tauri::AppHandle,
    state: State<MinerState>,
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
        let mut g = state.0.lock().map_err(|_| "lock poisoned")?;
        if g.cpu.is_some() || g.gpu.is_some() {
            return Err("miner already running".into());
        }
        g.status = "starting".into();
        g.error = None;
        g.address = Some(address.clone());
    }
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let arc = state.0.clone();
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

pub fn stop(state: State<MinerState>) -> Result<(), String> {
    let mut g = state.0.lock().map_err(|_| "lock poisoned")?;
    for child in [g.cpu.take(), g.gpu.take()].into_iter().flatten() {
        let mut child = child;
        let _ = child.kill();
        let _ = child.wait();
    }
    g.status = "stopped".into();
    g.error = None;
    Ok(())
}

pub fn status(state: State<MinerState>) -> Status {
    let (st, err, addr, pool, cpu_up, gpu_up) = {
        let mut g = match state.0.lock() {
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
        let cpu_up = g.cpu.is_some();
        let gpu_up = g.gpu.is_some();
        if !cpu_up && !gpu_up && g.status == "running" {
            g.status = "stopped".into();
        }
        (g.status.clone(), g.error.clone(), g.address.clone(), g.pool.clone(), cpu_up, gpu_up)
    };

    let (mut chr, mut sg, mut stot) = (0.0, 0u64, 0u64);
    if cpu_up {
        if let Ok(v) = query_xmrig() {
            chr = v.0;
            sg = v.1;
            stot = v.2;
        }
    }
    let mut ghr = 0.0;
    if gpu_up {
        if let Ok(v) = query_srbminer() {
            ghr = v;
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
    let cfg = serde_json::json!({
        "autosave": false,
        "http": { "enabled": true, "host": "127.0.0.1", "port": XMRIG_API_PORT, "access-token": serde_json::Value::Null, "restricted": true },
        "cpu": { "enabled": true },
        "randomx": { "1gb-pages": false },
        "pools": [ {
            "url": format!("{POOL_HOST}:{POOL_PORT}"),
            "user": address,
            "pass": "x",
            "rig-id": rig,
            "keepalive": true,
            "tls": false,
            "algo": "rx/0"
        } ]
    });
    let cfg_path = data_dir.join("xmrig-abakos.json");
    std::fs::write(&cfg_path, serde_json::to_vec_pretty(&cfg).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
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
    let mut cmd = Command::new(&bin);
    cmd.args([
        "--algorithm", "pearlhash",
        "--pool", PRL_POOL,
        "--wallet", &format!("{}.{}", kryptex_user(), worker),
        "--password", "x",
        "--disable-cpu",
        "--api-enable",
        "--api-port", &SRB_API_PORT.to_string(),
    ]);
    hidden(&mut cmd);
    cmd.spawn().map_err(|e| format!("failed to start SRBMiner: {e}"))
}

fn hidden(cmd: &mut Command) {
    cmd.stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
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

fn query_srbminer() -> Result<f64, String> {
    let c = http_client(4)?;
    let v: serde_json::Value = c
        .get(format!("http://127.0.0.1:{SRB_API_PORT}/"))
        .send()
        .map_err(|e| e.to_string())?
        .json()
        .map_err(|e| e.to_string())?;
    let hr = v
        .pointer("/algorithms/0/hashrate/total/0")
        .and_then(|x| x.as_f64())
        .or_else(|| v.pointer("/hashrate_total_now").and_then(|x| x.as_f64()))
        .unwrap_or(0.0);
    Ok(hr)
}
