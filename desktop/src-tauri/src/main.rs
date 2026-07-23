// Prevent a second console window on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod miner;
mod provider;

use serde::Serialize;
use tauri::{Manager, State};

/// Only these hosts may be reached through the net_get/net_post bridge. All chain
/// RPC/REST + agent/proxy calls go through the Rust core so the webview never runs
/// into CORS on endpoints that don't send permissive headers.
const ALLOWED_HOSTS: &[&str] = &[
    "abakos.ai",
    "evm-rpc.abakos.ai",
    "rest.abakos.ai",
    "rpc.abakos.ai",
    "explorer.abakos.ai",
    "mine.abakos.ai",
];

fn host_allowed(url: &str) -> bool {
    let Some(rest) = url.strip_prefix("https://") else {
        return false;
    };
    let host = rest.split(['/', ':', '?']).next().unwrap_or("");
    ALLOWED_HOSTS.iter().any(|h| host == *h)
}

fn http_client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .map_err(|e| e.to_string())
}

#[derive(Serialize, Clone)]
struct HardwareInfo {
    os: String,
    arch: String,
    cpu_threads: usize,
    has_nvidia: bool,
}

#[tauri::command]
async fn hardware_info() -> HardwareInfo {
    // Detect off the main thread. A sync command runs on the main (UI) thread, so a
    // slow/hanging nvidia-smi used to freeze the whole app while "Detecting hardware".
    tauri::async_runtime::spawn_blocking(|| HardwareInfo {
        os: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
        cpu_threads: std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1),
        has_nvidia: detect_nvidia(),
    })
    .await
    .unwrap_or(HardwareInfo {
        os: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
        cpu_threads: 1,
        has_nvidia: false,
    })
}

/// Probe nvidia-smi for a GPU, but never wait longer than ~2s (some machines have a
/// slow or hanging nvidia-smi). Returns false on timeout or absence.
fn detect_nvidia() -> bool {
    use std::sync::mpsc;
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let mut cmd = std::process::Command::new("nvidia-smi");
        cmd.arg("-L");
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        }
        let ok = cmd
            .output()
            .map(|o| o.status.success() && !o.stdout.is_empty())
            .unwrap_or(false);
        let _ = tx.send(ok);
    });
    rx.recv_timeout(std::time::Duration::from_secs(2)).unwrap_or(false)
}

#[tauri::command]
async fn net_get(url: String) -> Result<String, String> {
    if !host_allowed(&url) {
        return Err("host not allowed".into());
    }
    // Run the blocking HTTP off the UI thread so frequent polling never freezes the app.
    tauri::async_runtime::spawn_blocking(move || {
        http_client()?
            .get(&url)
            .header("User-Agent", "abakos-provider")
            .send()
            .map_err(|e| e.to_string())?
            .text()
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn net_post(url: String, body: String) -> Result<String, String> {
    if !host_allowed(&url) {
        return Err("host not allowed".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        http_client()?
            .post(&url)
            .header("Content-Type", "application/json")
            .header("User-Agent", "abakos-provider")
            .body(body)
            .send()
            .map_err(|e| e.to_string())?
            .text()
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

fn kv_path(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    let dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("store.json"))
}

#[tauri::command]
fn kv_get(app: tauri::AppHandle, key: String) -> Result<Option<String>, String> {
    let p = kv_path(&app)?;
    if !p.exists() {
        return Ok(None);
    }
    let txt = std::fs::read_to_string(&p).map_err(|e| e.to_string())?;
    let v: serde_json::Value = serde_json::from_str(&txt).unwrap_or_else(|_| serde_json::json!({}));
    Ok(v.get(&key).and_then(|x| x.as_str()).map(|s| s.to_string()))
}

#[tauri::command]
fn kv_set(app: tauri::AppHandle, key: String, value: String) -> Result<(), String> {
    let p = kv_path(&app)?;
    let mut v: serde_json::Value = if p.exists() {
        serde_json::from_str(&std::fs::read_to_string(&p).map_err(|e| e.to_string())?)
            .unwrap_or_else(|_| serde_json::json!({}))
    } else {
        serde_json::json!({})
    };
    v[key] = serde_json::Value::String(value);
    std::fs::write(
        &p,
        serde_json::to_string_pretty(&v).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn kv_delete(app: tauri::AppHandle, key: String) -> Result<(), String> {
    let p = kv_path(&app)?;
    if !p.exists() {
        return Ok(());
    }
    let mut v: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&p).map_err(|e| e.to_string())?)
            .unwrap_or_else(|_| serde_json::json!({}));
    if let Some(obj) = v.as_object_mut() {
        obj.remove(&key);
    }
    std::fs::write(
        &p,
        serde_json::to_string_pretty(&v).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}

/// Allow mining on this PC: adds a Windows Defender exclusion for the app's data
/// dir (where the miner binaries live) via one elevated (UAC) prompt the user
/// accepts. Every mining binary is flagged as riskware by AVs; this is the
/// standard, user-consented way to permit it. No-op on non-Windows.
#[tauri::command]
async fn enable_mining(app: tauri::AppHandle) -> Result<String, String> {
    // The elevated PowerShell runs with -Wait; do it off the UI thread so the app
    // doesn't freeze while the UAC prompt is open.
    tauri::async_runtime::spawn_blocking(move || {
        let dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        #[cfg(windows)]
        {
            let dir_s = dir.to_string_lossy().replace('\'', "''");
            let ps1 = dir.join("allow-mining.ps1");
            std::fs::write(&ps1, format!("Add-MpPreference -ExclusionPath '{dir_s}'\r\n"))
                .map_err(|e| e.to_string())?;
            let file = ps1.to_string_lossy().replace('\'', "''");
            let outer = format!(
                "Start-Process powershell -Verb RunAs -WindowStyle Hidden -Wait -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{file}'"
            );
            let status = std::process::Command::new("powershell")
                .args(["-NoProfile", "-WindowStyle", "Hidden", "-Command", &outer])
                .status()
                .map_err(|e| e.to_string())?;
            if status.success() {
                Ok("Mining allowed (Windows Defender exclusion added).".into())
            } else {
                Err("The Windows prompt was declined. Windows Defender may block the miner.".into())
            }
        }
        #[cfg(not(windows))]
        {
            let _ = dir;
            Ok("No exclusion needed on this OS.".into())
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn start_miner(
    app: tauri::AppHandle,
    state: State<miner::MinerState>,
    address: String,
    threads: u32,
    cpu: bool,
    gpu: bool,
) -> Result<(), String> {
    // start() spawns a worker thread and returns immediately, so it stays sync.
    miner::start(app, &state.0, address, threads, cpu, gpu)
}

#[tauri::command]
async fn stop_miner(state: State<'_, miner::MinerState>) -> Result<(), String> {
    // stop() runs netstat/taskkill (slow) -> off the UI thread.
    let arc = state.0.clone();
    tauri::async_runtime::spawn_blocking(move || miner::stop(&arc))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn miner_status(state: State<'_, miner::MinerState>) -> Result<miner::Status, String> {
    // status() probes the miner HTTP APIs (blocking) -> off the UI thread so the 4s
    // poll never freezes the app.
    let arc = state.0.clone();
    tauri::async_runtime::spawn_blocking(move || miner::status(&arc))
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn start_provider(state: State<'_, provider::ProviderState>) -> Result<(), String> {
    let arc = state.0.clone();
    tauri::async_runtime::spawn_blocking(move || provider::start(&arc))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn stop_provider(state: State<'_, provider::ProviderState>) -> Result<(), String> {
    let arc = state.0.clone();
    tauri::async_runtime::spawn_blocking(move || provider::stop(&arc))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn provider_status(
    state: State<'_, provider::ProviderState>,
) -> Result<provider::Status, String> {
    let arc = state.0.clone();
    tauri::async_runtime::spawn_blocking(move || provider::status(&arc))
        .await
        .map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .manage(miner::MinerState::default())
        .manage(provider::ProviderState::default())
        .invoke_handler(tauri::generate_handler![
            hardware_info,
            net_get,
            net_post,
            kv_get,
            kv_set,
            kv_delete,
            enable_mining,
            start_miner,
            stop_miner,
            miner_status,
            start_provider,
            stop_provider,
            provider_status
        ])
        .run(tauri::generate_context!())
        .expect("error while running Abakos Provider");
}
