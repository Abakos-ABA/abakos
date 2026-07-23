//! Local compute-provider (host) control.
//! Linux-first: drives the `abakos-provider` systemd unit and reads host_uri from
//! the on-disk provider config when present. Windows/macOS return an unavailable
//! status — hosting requires the Linux/k3s provider VM.

use std::sync::{Arc, Mutex};

use serde::Serialize;

pub struct Inner {
    #[allow(dead_code)]
    pub status: String, // "stopped" | "starting" | "running" | "error" | "unavailable"
    #[allow(dead_code)]
    pub error: Option<String>,
    #[allow(dead_code)]
    pub host_uri: Option<String>,
    pub unit: String,
}

impl Default for Inner {
    fn default() -> Self {
        Inner {
            status: "stopped".into(),
            error: None,
            host_uri: None,
            unit: "abakos-provider".into(),
        }
    }
}

#[derive(Default)]
pub struct ProviderState(pub Arc<Mutex<Inner>>);

#[derive(Serialize, Clone)]
pub struct Status {
    pub state: String,
    pub error: Option<String>,
    pub host_uri: Option<String>,
    pub unit: String,
    pub platform_ok: bool,
}

#[cfg(target_os = "linux")]
fn run_cmd(bin: &str, args: &[&str]) -> Result<(i32, String, String), String> {
    use std::process::Command;
    let out = Command::new(bin)
        .args(args)
        .output()
        .map_err(|e| format!("{bin}: {e}"))?;
    let code = out.status.code().unwrap_or(-1);
    let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&out.stderr).trim().to_string();
    Ok((code, stdout, stderr))
}

#[cfg(target_os = "linux")]
fn read_host_uri() -> Option<String> {
    use std::path::PathBuf;
    let home = std::env::var_os("HOME").map(PathBuf::from);
    let candidates = [
        home.as_ref()
            .map(|h| h.join("abakos/provider-compute/provider.local.yaml")),
        home.as_ref()
            .map(|h| h.join("abakos/provider-compute/provider.yaml")),
        Some(PathBuf::from(
            "/opt/abakos/provider-compute/provider.local.yaml",
        )),
        Some(PathBuf::from("/etc/abakos/provider.yaml")),
    ];
    for path in candidates.into_iter().flatten() {
        if let Ok(txt) = std::fs::read_to_string(&path) {
            for line in txt.lines() {
                let t = line.trim();
                if let Some(rest) = t
                    .strip_prefix("host_uri:")
                    .or_else(|| t.strip_prefix("host:"))
                {
                    let v = rest
                        .trim()
                        .trim_matches('"')
                        .trim_matches('\'')
                        .to_string();
                    if v.starts_with("http") {
                        return Some(v);
                    }
                }
            }
        }
    }
    None
}

#[cfg(target_os = "linux")]
fn probe_unit(unit: &str) -> (String, Option<String>) {
    match run_cmd("systemctl", &["is-active", unit]) {
        Ok((_code, stdout, stderr)) => match stdout.as_str() {
            "active" => ("running".into(), None),
            "activating" => ("starting".into(), None),
            "inactive" | "failed" => ("stopped".into(), None),
            other => {
                let err = if other.is_empty() {
                    stderr
                } else {
                    format!("{other} {stderr}").trim().to_string()
                };
                if err.contains("not found") || err.contains("could not be found") {
                    (
                        "unavailable".into(),
                        Some(
                            "abakos-provider unit not found. Install provider-compute on this Linux host first."
                                .into(),
                        ),
                    )
                } else {
                    ("stopped".into(), if err.is_empty() { None } else { Some(err) })
                }
            }
        },
        Err(e) => (
            "unavailable".into(),
            Some(format!("systemctl unavailable: {e}")),
        ),
    }
}

pub fn status(inner: &Arc<Mutex<Inner>>) -> Status {
    #[cfg(not(target_os = "linux"))]
    {
        let _ = inner;
        Status {
            state: "unavailable".into(),
            error: Some(
                "Compute hosting runs on a Linux provider host (k3s + abakos-provider). Use your Ubuntu VM."
                    .into(),
            ),
            host_uri: None,
            unit: "abakos-provider".into(),
            platform_ok: false,
        }
    }

    #[cfg(target_os = "linux")]
    {
        let host_uri = read_host_uri();
        let unit = {
            let g = inner.lock().unwrap();
            g.unit.clone()
        };
        let (state, error) = probe_unit(&unit);
        {
            let mut g = inner.lock().unwrap();
            g.status = state.clone();
            g.error = error.clone();
            g.host_uri = host_uri.clone();
        }
        Status {
            state,
            error,
            host_uri,
            unit,
            platform_ok: true,
        }
    }
}

pub fn start(inner: &Arc<Mutex<Inner>>) -> Result<(), String> {
    #[cfg(not(target_os = "linux"))]
    {
        let _ = inner;
        Err("Hosting requires Linux (provider VM).".into())
    }

    #[cfg(target_os = "linux")]
    {
        let unit = {
            let mut g = inner.lock().unwrap();
            g.status = "starting".into();
            g.error = None;
            g.unit.clone()
        };
        let (code, stdout, stderr) = run_cmd("systemctl", &["start", &unit])?;
        if code != 0 {
            let msg = if stderr.is_empty() { stdout } else { stderr };
            let hint = if msg.contains("Permission denied") || msg.contains("Interactive authentication")
            {
                format!("{msg} — try: sudo systemctl start {unit}")
            } else {
                msg
            };
            let mut g = inner.lock().unwrap();
            g.status = "error".into();
            g.error = Some(hint.clone());
            return Err(hint);
        }
        let _ = status(inner);
        Ok(())
    }
}

pub fn stop(inner: &Arc<Mutex<Inner>>) -> Result<(), String> {
    #[cfg(not(target_os = "linux"))]
    {
        let _ = inner;
        Err("Hosting requires Linux (provider VM).".into())
    }

    #[cfg(target_os = "linux")]
    {
        let unit = {
            let g = inner.lock().unwrap();
            g.unit.clone()
        };
        let (code, stdout, stderr) = run_cmd("systemctl", &["stop", &unit])?;
        if code != 0 {
            let msg = if stderr.is_empty() { stdout } else { stderr };
            let hint = if msg.contains("Permission denied") || msg.contains("Interactive authentication")
            {
                format!("{msg} — try: sudo systemctl stop {unit}")
            } else {
                msg
            };
            let mut g = inner.lock().unwrap();
            g.status = "error".into();
            g.error = Some(hint.clone());
            return Err(hint);
        }
        let _ = status(inner);
        Ok(())
    }
}
