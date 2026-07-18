//! Miner orchestration (CPU / RandomX). Downloads xmrig on first run, writes a
//! config that points at the Abakos stratum proxy with the user's ABA address as
//! the login (so the proxy attributes verified shares to it), and runs it.
//! GPU (KawPow) is a phase-2 handler. Stats are read from xmrig's local HTTP API.

use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::{Manager, State};

/// Default Abakos pool (our stratum proxy -> Kryptex upstream). DNS `mine.abakos.ai`
/// resolves to the sandbox VPS; the proxy listens on 3355 (RandomX/cryptonote).
const POOL_HOST: &str = "mine.abakos.ai";
const POOL_PORT: u16 = 3355;
const XMRIG_API_PORT: u16 = 16000;

pub struct Inner {
    pub child: Option<Child>,
    pub status: String, // "stopped" | "starting" | "running" | "error"
    pub error: Option<String>,
    pub address: Option<String>,
    pub pool: String,
}

impl Default for Inner {
    fn default() -> Self {
        Inner {
            child: None,
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
    pub hashrate: f64,
    pub shares_good: u64,
    pub shares_total: u64,
}

pub fn start(
    app: tauri::AppHandle,
    state: State<MinerState>,
    address: String,
    threads: u32,
    _cpu: bool,
    _gpu: bool,
) -> Result<(), String> {
    if !address.starts_with("abakos1") {
        return Err("address must be an abakos1 address".into());
    }
    {
        let mut g = state.0.lock().map_err(|_| "lock poisoned")?;
        if g.child.is_some() {
            return Err("miner already running".into());
        }
        g.status = "starting".into();
        g.error = None;
        g.address = Some(address.clone());
    }
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?;
    let arc = state.0.clone();
    // Download + launch off the UI thread; status reflects progress.
    std::thread::spawn(move || {
        let res = run_cpu(&data_dir, &address, threads);
        if let Ok(mut g) = arc.lock() {
            match res {
                Ok(child) => {
                    g.child = Some(child);
                    g.status = "running".into();
                }
                Err(e) => {
                    g.status = "error".into();
                    g.error = Some(e);
                }
            }
        }
    });
    Ok(())
}

pub fn stop(state: State<MinerState>) -> Result<(), String> {
    let mut g = state.0.lock().map_err(|_| "lock poisoned")?;
    if let Some(mut child) = g.child.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    g.status = "stopped".into();
    g.error = None;
    Ok(())
}

pub fn status(state: State<MinerState>) -> Status {
    let (st, err, addr, pool) = {
        let mut g = match state.0.lock() {
            Ok(g) => g,
            Err(_) => {
                return Status {
                    state: "error".into(),
                    error: Some("lock poisoned".into()),
                    address: None,
                    pool: format!("{POOL_HOST}:{POOL_PORT}"),
                    hashrate: 0.0,
                    shares_good: 0,
                    shares_total: 0,
                }
            }
        };
        // Reap the child if it exited on its own.
        if let Some(child) = g.child.as_mut() {
            if let Ok(Some(_)) = child.try_wait() {
                g.child = None;
                if g.status == "running" {
                    g.status = "stopped".into();
                }
            }
        }
        (g.status.clone(), g.error.clone(), g.address.clone(), g.pool.clone())
    };

    let (mut hr, mut sg, mut stot) = (0.0, 0u64, 0u64);
    if st == "running" {
        if let Ok(v) = query_xmrig() {
            hr = v.0;
            sg = v.1;
            stot = v.2;
        }
    }
    Status {
        state: st,
        error: err,
        address: addr,
        pool,
        hashrate: hr,
        shares_good: sg,
        shares_total: stot,
    }
}

fn run_cpu(data_dir: &Path, address: &str, threads: u32) -> Result<Child, String> {
    let bin = ensure_xmrig(data_dir)?;
    let rig = &address[..address.len().min(24)];
    let cfg = serde_json::json!({
        "autosave": false,
        "http": {
            "enabled": true,
            "host": "127.0.0.1",
            "port": XMRIG_API_PORT,
            "access-token": serde_json::Value::Null,
            "restricted": true
        },
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
    std::fs::write(
        &cfg_path,
        serde_json::to_vec_pretty(&cfg).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;

    let mut cmd = Command::new(&bin);
    cmd.arg("-c").arg(&cfg_path);
    if threads > 0 {
        cmd.arg("-t").arg(threads.to_string());
    }
    cmd.stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd.spawn().map_err(|e| format!("failed to start xmrig: {e}"))
}

fn ensure_xmrig(data_dir: &Path) -> Result<PathBuf, String> {
    let root = data_dir.join("xmrig");
    std::fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    let exe = if cfg!(windows) { "xmrig.exe" } else { "xmrig" };
    if let Some(p) = find_file(&root, exe) {
        return Ok(p);
    }
    let (url, name) = latest_xmrig_asset()?;
    let archive = root.join(&name);
    download(&url, &archive)?;
    extract(&archive, &root)?;
    let p = find_file(&root, exe).ok_or_else(|| "xmrig binary not found after extract".to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perm = std::fs::metadata(&p).map_err(|e| e.to_string())?.permissions();
        perm.set_mode(0o755);
        std::fs::set_permissions(&p, perm).map_err(|e| e.to_string())?;
    }
    Ok(p)
}

fn latest_xmrig_asset() -> Result<(String, String), String> {
    let c = http_client(30)?;
    let rel: serde_json::Value = c
        .get("https://api.github.com/repos/xmrig/xmrig/releases/latest")
        .header("User-Agent", "abakos-provider")
        .header("Accept", "application/vnd.github+json")
        .send()
        .map_err(|e| e.to_string())?
        .json()
        .map_err(|e| e.to_string())?;
    let assets = rel
        .get("assets")
        .and_then(|a| a.as_array())
        .ok_or("no release assets")?;
    let want: &[&str] = if cfg!(windows) {
        &["msvc-win64", "win64", "windows-x64"]
    } else if cfg!(target_os = "macos") {
        if cfg!(target_arch = "aarch64") {
            &["macos-arm64"]
        } else {
            &["macos-x64"]
        }
    } else if cfg!(target_arch = "aarch64") {
        &["linux-static-arm64", "linux-arm64"]
    } else {
        &["linux-static-x64", "linux-x64"]
    };
    for w in want {
        for a in assets {
            let n = a.get("name").and_then(|x| x.as_str()).unwrap_or("");
            let nl = n.to_lowercase();
            if nl.contains(w) && (nl.ends_with(".zip") || nl.ends_with(".tar.gz")) {
                if let Some(u) = a.get("browser_download_url").and_then(|x| x.as_str()) {
                    return Ok((u.to_string(), n.to_string()));
                }
            }
        }
    }
    Err("no matching xmrig asset for this platform".into())
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
