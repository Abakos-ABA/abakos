// Prevent a second console window on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod miner;

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
fn hardware_info() -> HardwareInfo {
    let cpu_threads = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1);
    let has_nvidia = std::process::Command::new("nvidia-smi")
        .arg("-L")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);
    HardwareInfo {
        os: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
        cpu_threads,
        has_nvidia,
    }
}

#[tauri::command]
fn net_get(url: String) -> Result<String, String> {
    if !host_allowed(&url) {
        return Err("host not allowed".into());
    }
    http_client()?
        .get(&url)
        .header("User-Agent", "abakos-provider")
        .send()
        .map_err(|e| e.to_string())?
        .text()
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn net_post(url: String, body: String) -> Result<String, String> {
    if !host_allowed(&url) {
        return Err("host not allowed".into());
    }
    http_client()?
        .post(&url)
        .header("Content-Type", "application/json")
        .header("User-Agent", "abakos-provider")
        .body(body)
        .send()
        .map_err(|e| e.to_string())?
        .text()
        .map_err(|e| e.to_string())
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

#[tauri::command]
fn start_miner(
    app: tauri::AppHandle,
    state: State<miner::MinerState>,
    address: String,
    threads: u32,
    cpu: bool,
    gpu: bool,
) -> Result<(), String> {
    miner::start(app, state, address, threads, cpu, gpu)
}

#[tauri::command]
fn stop_miner(state: State<miner::MinerState>) -> Result<(), String> {
    miner::stop(state)
}

#[tauri::command]
fn miner_status(state: State<miner::MinerState>) -> miner::Status {
    miner::status(state)
}

fn main() {
    tauri::Builder::default()
        .manage(miner::MinerState::default())
        .invoke_handler(tauri::generate_handler![
            hardware_info,
            net_get,
            net_post,
            kv_get,
            kv_set,
            kv_delete,
            start_miner,
            stop_miner,
            miner_status
        ])
        .run(tauri::generate_context!())
        .expect("error while running Abakos Provider");
}
