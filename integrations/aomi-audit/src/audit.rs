//! Deployment-bound audit tools. The auditor wallet, chain, registry and API
//! origin come only from the build-time deployment. What each cited source
//! returned is recorded by this app's own requests, never written by the model.
use crate::RrAuditApp;
use aomi_sdk::{
    DynAomiTool, DynToolCallCtx, EnforcementPolicy, ToolReturn, host, resolve_secret_value,
};
use reqwest::Method;
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    io::Read,
    net::{IpAddr, ToSocketAddrs},
    sync::OnceLock,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

#[derive(Deserialize)]
pub struct Deployment {
    pub enabled: bool,
    #[serde(default)]
    pub chain_id: u64,
    #[serde(default)]
    pub registry: String,
    #[serde(default)]
    pub auditor: String,
    #[serde(default)]
    pub api_url: String,
}

fn deployment() -> Result<Deployment, String> {
    let value: Value = serde_json::from_str(include_str!(concat!(
        env!("OUT_DIR"),
        "/audit-deployment.json"
    )))
    .unwrap();
    if value["enabled"] != true {
        return Err("Audits are disabled until an auditor and registry are configured.".into());
    }
    serde_json::from_value(value).map_err(|_| "Invalid audit deployment".into())
}

fn request(
    ctx: &DynToolCallCtx,
    d: &Deployment,
    method: Method,
    path: &str,
    body: Option<Value>,
) -> Result<Value, String> {
    let token = resolve_secret_value(ctx, None, "RR_AUDIT_API_TOKEN", "")
        .map_err(|_| "Configure the audit API credential in the app environment.")?;
    static HTTP: OnceLock<reqwest::blocking::Client> = OnceLock::new();
    let http = HTTP.get_or_init(|| {
        reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(60))
            .connect_timeout(Duration::from_secs(10))
            // A redirect must not carry this credential elsewhere.
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .unwrap()
    });
    let url = format!("{}{}", d.api_url.trim_end_matches('/'), path);
    let mut call = http.request(method, url).bearer_auth(token);
    if let Some(body) = body {
        call = call.json(&body);
    }
    let response = call.send().map_err(
        |_| "Audit API unavailable. Retry the read; never publish an uncertain audit twice.",
    )?;
    let status = response.status();
    if !status.is_success() {
        let detail = response
            .json::<Value>()
            .ok()
            .and_then(|v| v["detail"].as_str().map(str::to_owned));
        // Relay only the API's own static refusals, never arbitrary upstream bodies.
        if let Some(message) = detail.filter(|s| {
            s.starts_with("This audit is already ")
                || matches!(
                    s.as_str(),
                    "Audits are disabled until an auditor and registry are configured"
                        | "Only the configured auditor wallet can seal audits"
                        | "Auditor wallet is on the wrong network"
                        | "No audit with this id"
                        | "Report every cited source exactly once, at its cited URL"
                        | "Stored trace commitments do not verify; nothing was sealed"
                        | "This sealed trace already exists; manual review required"
                        | "Deployment changed since sealing; manual review required"
                        | "This audit was already published by a different transaction"
                        | "This audit is not sealed; there is nothing to publish"
                        | "This transaction already published a different audit"
                        | "Transaction is not in the canonical chain; nothing was recorded"
                        | "Transaction does not contain exactly one receipt from the registry"
                        | "Published receipt is not the sealed trace from the auditor"
                        | "RPC cannot report finality; nothing was recorded"
                        | "Audit changed during confirmation; manual review required"
                )
        }) {
            return Err(message);
        }
        return Err(match status.as_u16() {
            401 | 403 => "Audit access denied. Check the app credential.",
            404 => "No such audit.",
            409 => "Audit blocked by its current state. Do not publish.",
            422 => "Invalid audit request; report every cited source once.",
            _ => "Audit state unavailable. Do not publish.",
        }
        .into());
    }
    response
        .json()
        .map_err(|_| "Invalid audit API response; stop.".into())
}

/// The connected wallet must be the deployment's auditor on its chain.
fn auditor_wallet(ctx: &DynToolCallCtx, d: &Deployment) -> Result<String, String> {
    ctx.attribute_string(&["domain", "evm", "address"])
        .filter(|a| {
            ctx.attribute_u64(&["domain", "evm", "chain_id"]) == Some(d.chain_id)
                && a.eq_ignore_ascii_case(&d.auditor)
        })
        .map(|a| a.to_ascii_lowercase())
        .ok_or_else(|| "Connect the configured auditor wallet on the configured network.".into())
}

fn public_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            let [a, b, ..] = v4.octets();
            !(v4.is_private()
                || v4.is_loopback()
                || v4.is_link_local()
                || v4.is_unspecified()
                || v4.is_broadcast()
                || v4.is_documentation()
                || a == 0
                || (a == 100 && (b & 0xc0) == 64))
        }
        IpAddr::V6(v6) => match v6.to_ipv4_mapped() {
            Some(v4) => public_ip(IpAddr::V4(v4)),
            None => {
                let s = v6.segments()[0];
                !(v6.is_loopback()
                    || v6.is_unspecified()
                    || (s & 0xfe00) == 0xfc00
                    || (s & 0xffc0) == 0xfe80)
            }
        },
    }
}

/// Sources are fetched only over https from named hosts that resolve to public addresses.
fn public_https(url: &reqwest::Url) -> bool {
    let Some(host) = url.host_str().map(str::to_ascii_lowercase) else {
        return false;
    };
    url.scheme() == "https"
        && url.username().is_empty()
        && url.password().is_none()
        && !host.starts_with('[')
        && host.parse::<IpAddr>().is_err()
        && host != "localhost"
        && ![".localhost", ".local", ".internal"]
            .iter()
            .any(|s| host.ends_with(s))
        && (host.as_str(), url.port_or_known_default().unwrap_or(443))
            .to_socket_addrs()
            .is_ok_and(|addrs| {
                let addrs: Vec<_> = addrs.collect();
                !addrs.is_empty() && addrs.iter().all(|a| public_ip(a.ip()))
            })
}

/// Visible text: common entities decoded, whitespace collapsed, capped at `max` chars.
fn squash(text: &str, max: usize) -> String {
    [
        ("&nbsp;", " "),
        ("&quot;", "\""),
        ("&#39;", "'"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&amp;", "&"),
    ]
    .iter()
    .fold(text.to_string(), |t, (entity, ch)| t.replace(entity, ch))
    .split_whitespace()
    .collect::<Vec<_>>()
    .join(" ")
    .chars()
    .take(max)
    .collect()
}

const MAX_BODY: u64 = 2 * 1024 * 1024;

/// Fetch one cited source and record what came back. Returns the check the API
/// stores, and a text excerpt for the auditor to read.
fn check_source(url: &str, cited_title: &str) -> (Value, String) {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_secs()) as i64;
    // Civil date from days since epoch (Howard Hinnant's algorithm).
    let (z, rem) = (secs.div_euclid(86_400) + 719_468, secs.rem_euclid(86_400));
    let doe = z - z.div_euclid(146_097) * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let fetched_at = format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        yoe + z.div_euclid(146_097) * 400 + i64::from(month <= 2),
        month,
        doy - (153 * mp + 2) / 5 + 1,
        rem / 3600,
        rem % 3600 / 60,
        rem % 60
    );
    let failed = |error: &str| {
        let check = json!({"http_status": null, "final_url": null, "content_sha256": null,
            "page_title": null, "title_matches": false, "fetched_at": fetched_at, "error": error});
        (check, String::new())
    };
    let Ok(parsed) = reqwest::Url::parse(url) else {
        return failed("not a valid URL");
    };
    if !public_https(&parsed) {
        return failed("not a public https URL");
    }
    static HTTP: OnceLock<reqwest::blocking::Client> = OnceLock::new();
    let http = HTTP.get_or_init(|| {
        reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(15))
            .connect_timeout(Duration::from_secs(8))
            .user_agent("ReasoningReceipt-Auditor/0.1")
            .redirect(reqwest::redirect::Policy::custom(|attempt| {
                if attempt.previous().len() >= 5 || !public_https(attempt.url()) {
                    attempt.stop()
                } else {
                    attempt.follow()
                }
            }))
            .build()
            .unwrap()
    });
    let Ok(response) = http.get(parsed).send() else {
        return failed("request failed");
    };
    let status = response.status().as_u16();
    let final_url = response.url().to_string();
    let mut body = Vec::new();
    if response.take(MAX_BODY).read_to_end(&mut body).is_err() {
        return failed("body could not be read");
    }

    let text = String::from_utf8_lossy(&body);
    // ASCII lowercasing keeps byte offsets, so indexes found in `lower` slice `text`.
    let lower = text.to_ascii_lowercase();
    let page_title = lower.find("<title").and_then(|start| {
        let open = start + lower[start..].find('>')? + 1;
        let close = open + lower[open..].find("</title")?;
        Some(squash(&text[open..close], 300))
    });
    let words = |s: &str| {
        s.to_lowercase()
            .split(|c: char| !c.is_alphanumeric())
            .filter(|w| !w.is_empty())
            .collect::<Vec<_>>()
            .join(" ")
    };
    let (cited, found) = (
        words(cited_title),
        words(page_title.as_deref().unwrap_or("")),
    );
    let title_matches = !cited.is_empty()
        && !found.is_empty()
        && (found.contains(&cited) || cited.contains(&found));
    let mut visible = String::new();
    let mut at = 0;
    while let Some(offset) = lower[at..].find('<') {
        let tag = at + offset;
        visible.push_str(&text[at..tag]);
        visible.push(' ');
        let end = ["script", "style"]
            .iter()
            .find(|name| lower[tag + 1..].starts_with(*name))
            .map_or(">".to_string(), |name| format!("</{name}"));
        at = match lower[tag..].find(&end) {
            Some(e) => tag + e + end.len(),
            None => lower.len(),
        };
        if end != ">" {
            at += lower[at..].find('>').map_or(lower.len() - at, |e| e + 1);
        }
    }
    visible.push_str(&text[at..]);
    let check = json!({
        "http_status": status,
        "final_url": final_url.chars().take(2000).collect::<String>(),
        "content_sha256": format!("0x{:x}", Sha256::digest(&body)),
        "page_title": page_title,
        "title_matches": title_matches,
        "fetched_at": fetched_at,
        "error": null,
    });
    (check, squash(&visible, 2000))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NextArgs {}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum Verdict {
    Approved,
    Rejected,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Judgment {
    /// evidence_id exactly as rr_next_audit listed it.
    pub evidence_id: String,
    /// True only if the fetched page shows what the trace cites it for.
    pub supports: bool,
    /// One sentence on what the page does or does not show.
    pub note: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SealArgs {
    /// audit_id from rr_next_audit.
    pub audit_id: u64,
    /// approved only if the claim follows from the sources that could be read; the API also requires most of them to support it.
    pub verdict: Verdict,
    /// Why, in a few sentences. Stored in the published trace.
    pub notes: String,
    /// Exactly one judgment per cited source.
    pub judgments: Vec<Judgment>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ConfirmArgs {
    /// audit_id that was sealed and published.
    pub audit_id: u64,
    /// Actual broadcast hash returned by the auditor wallet, never an invented identifier.
    pub transaction_hash: String,
}

pub struct NextAudit;
impl DynAomiTool for NextAudit {
    type App = RrAuditApp;
    type Args = NextArgs;
    const NAME: &'static str = "rr_next_audit";
    const DESCRIPTION: &'static str = "Take the oldest oracle trace waiting for audit. Fetches every cited source and returns, per source, what came back (status, content hash, page title) and a text excerpt to judge against what the trace cites it for. A sealed audit waiting for its wallet comes back instead, already staged and simulated, only when no trace is pending.";
    fn run_with_routes(
        _: &RrAuditApp,
        _: NextArgs,
        ctx: DynToolCallCtx,
    ) -> Result<ToolReturn, String> {
        let d = deployment()?;
        let mut result = request(&ctx, &d, Method::GET, "/v1/audits/next", None)?;
        if result["status"] == "sealed" {
            auditor_wallet(&ctx, &d)?;
            return audit_route(result, &d);
        }
        if result["status"] != "pending" {
            return Ok(ToolReturn::value(result));
        }
        let evidence = result
            .as_object_mut()
            .and_then(|o| o.remove("evidence"))
            .unwrap_or_default();
        result["sources"] = evidence
            .as_array()
            .into_iter()
            .flatten()
            .map(|e| {
                let (check, excerpt) = check_source(
                    e["url"].as_str().unwrap_or(""),
                    e["title"].as_str().unwrap_or(""),
                );
                json!({"evidence_id": e["id"], "stance": e["stance"], "url": e["url"],
                    "cited_title": e["title"], "cited_for": e["cited_for"],
                    "check": check, "page_excerpt": excerpt})
            })
            .collect();
        Ok(ToolReturn::value(result))
    }
}

pub struct SealAudit;
impl DynAomiTool for SealAudit {
    type App = RrAuditApp;
    type Args = SealArgs;
    const NAME: &'static str = "rr_seal_audit";
    const DESCRIPTION: &'static str = "Record the audit. Re-fetches every cited source itself and sends those results with your judgments. A rejected audit is stored and never published. An approved one is sealed into the trace and returned as one unsigned publishV2 from the auditor wallet, staged and simulated; commit only after explicit wallet approval.";
    fn run_with_routes(
        _: &RrAuditApp,
        args: SealArgs,
        ctx: DynToolCallCtx,
    ) -> Result<ToolReturn, String> {
        let d = deployment()?;
        let auditor = auditor_wallet(&ctx, &d)?;
        let path = format!("/v1/audits/{}", args.audit_id);
        let current = request(&ctx, &d, Method::GET, &path, None)?;
        if current["status"] == "sealed" {
            return audit_route(current, &d);
        }
        if current["status"] != "pending" {
            return Ok(ToolReturn::value(current));
        }
        let evidence = current["evidence"].as_array().cloned().unwrap_or_default();
        if args.judgments.len() != evidence.len() {
            return Err("Give exactly one judgment per cited source.".into());
        }
        let mut sources = Vec::new();
        for e in &evidence {
            let id = e["id"].as_str().unwrap_or("");
            let mut found = args.judgments.iter().filter(|j| j.evidence_id == id);
            let (Some(judgment), None) = (found.next(), found.next()) else {
                return Err(format!("Give exactly one judgment for {id}."));
            };
            let (mut check, _) = check_source(
                e["url"].as_str().unwrap_or(""),
                e["title"].as_str().unwrap_or(""),
            );
            check["evidence_id"] = json!(id);
            check["url"] = e["url"].clone();
            check["supports"] = json!(judgment.supports);
            check["note"] = json!(judgment.note.chars().take(500).collect::<String>());
            sources.push(check);
        }
        let verdict = match args.verdict {
            Verdict::Approved => "approved",
            Verdict::Rejected => "rejected",
        };
        let result = request(
            &ctx,
            &d,
            Method::POST,
            &format!("{path}/seal"),
            Some(
                json!({"auditor": auditor, "chain_id": d.chain_id, "verdict": verdict,
                "notes": args.notes.chars().take(1000).collect::<String>(), "sources": sources}),
            ),
        )?;
        if result["status"] == "sealed" {
            return audit_route(result, &d);
        }
        Ok(ToolReturn::value(result))
    }
}

// keccak256("publishV2(address,bytes32,uint32,uint32,bytes32,bytes32,bytes16,string)")[0..4]
const PUBLISH_V2_SELECTOR: &str = "0xfd7b54b6";

fn audit_route(result: Value, d: &Deployment) -> Result<ToolReturn, String> {
    let tx = &result["transaction"];
    let data = tx["data"].as_str().unwrap_or("").to_ascii_lowercase();
    let text = |v: &Value| v.as_str().unwrap_or("").to_ascii_lowercase();
    let word = |i: usize| data.get(10 + 64 * i..10 + 64 * (i + 1)).unwrap_or("");
    let ppm = |v: &Value| v.as_f64().map(|p| (p * 1_000_000.0).round() as i64);
    let ppm_word = |i: usize| i64::from_str_radix(word(i), 16).ok();
    let cid = text(&result["trace_cid"]);
    let cid_len = usize::from_str_radix(word(8), 16).unwrap_or(usize::MAX);
    let cid_hex: String = result["trace_cid"]
        .as_str()
        .unwrap_or("")
        .bytes()
        .map(|b| format!("{b:02x}"))
        .collect();
    let schema_hex: String = result["schema_version"]
        .as_str()
        .unwrap_or("")
        .bytes()
        .map(|b| format!("{b:02x}"))
        .collect();
    let market = format!(
        "{:x}",
        Sha256::digest(result["market_id"].as_str().unwrap_or("").as_bytes())
    );
    // Decode every ABI word so the preview cannot diverge from the staged bytes.
    if !d.enabled
        || result["status"] != "sealed"
        || text(&result["auditor"]) != d.auditor.to_ascii_lowercase()
        || tx["chain_id"] != d.chain_id
        || tx["value"] != "0"
        || text(&tx["to"]) != d.registry.to_ascii_lowercase()
        || !data.starts_with(PUBLISH_V2_SELECTOR)
        || !data[2..].bytes().all(|b| b.is_ascii_hexdigit())
        || cid.is_empty()
        || schema_hex.is_empty()
        || schema_hex.len() > 32
        || word(0) != "0".repeat(64)
        || word(1) != market
        || ppm_word(2)
            .zip(ppm(&result["probability"]))
            .is_none_or(|(a, b)| (a - b).abs() > 1)
        || ppm_word(3)
            .zip(ppm(&result["confidence"]))
            .is_none_or(|(a, b)| (a - b).abs() > 1)
        || format!("0x{}", word(4)) != text(&result["trace_hash"])
        || format!("0x{}", word(5)) != text(&result["merkle_root"])
        || word(6) != format!("{schema_hex:0<64}")
        || word(7) != format!("{:064x}", 256)
        || cid_len != cid_hex.len() / 2
        || data.len() != 10 + 64 * 9 + cid_len.div_ceil(32) * 64
        || data[10 + 64 * 9..10 + 64 * 9 + cid_hex.len()] != cid_hex
        || data[10 + 64 * 9 + cid_hex.len()..]
            .bytes()
            .any(|b| b != b'0')
    {
        return Err("Sealed publish does not match this app's deployment and seal; stop.".into());
    }
    let stage = json!({"to": d.registry, "data": data, "value": "0",
        "description": format!(
            "Publish audited trace for market {} on chain {}: trace hash {}, Merkle root {}, publisher {}",
            result["market_id"].as_str().unwrap_or(""), d.chain_id,
            text(&result["trace_hash"]), text(&result["merkle_root"]), d.auditor),
        "kind": "rr_audit_publish"});
    ToolReturn::route(result)
        .next(|next| {
            next.add::<host::StageTx>(stage)
                // The host simulates the staged bytes immediately; a failure stops the plan.
                .enforce(EnforcementPolicy::Stop, |enforce| {
                    enforce.add::<host::SimulateBatch>(json!({}));
                })
                .note("Stage these exact bytes unchanged; the host simulates them. If simulation fails, stop and say nothing was published. Otherwise show the preview and call commit_txs for this one transaction only after the user explicitly approves it in the auditor wallet, then call rr_confirm_published with the wallet's transaction_hash. Never publish the same audit twice.");
        })
        .try_build()
}

pub struct ConfirmPublished;
impl DynAomiTool for ConfirmPublished {
    type App = RrAuditApp;
    type Args = ConfirmArgs;
    const NAME: &'static str = "rr_confirm_published";
    const DESCRIPTION: &'static str = "Independently check the wallet's finalized publish transaction against the sealed trace and record the audited receipt. Safe to repeat with the same hash. Only status published is success; pending, pending_finality and reverted mean nothing was recorded.";
    fn run(_: &RrAuditApp, args: ConfirmArgs, ctx: DynToolCallCtx) -> Result<Value, String> {
        let hash = &args.transaction_hash;
        if hash.len() != 66
            || !hash.starts_with("0x")
            || !hash[2..].bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err("Provide the wallet's 32-byte transaction hash.".into());
        }
        let d = deployment()?;
        let result = request(
            &ctx,
            &d,
            Method::POST,
            &format!("/v1/audits/{}/published", args.audit_id),
            Some(json!({"transaction_hash": hash})),
        )?;
        if result["status"] == "published"
            && !result["publisher"]
                .as_str()
                .is_some_and(|p| p.eq_ignore_ascii_case(&d.auditor))
        {
            return Err("Recorded publisher is not the configured auditor; stop.".into());
        }
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aomi_sdk::{
        DynAomiApp,
        testing::{TestCtxBuilder, run_tool},
    };

    fn fixture() -> (Deployment, Value) {
        let d = Deployment {
            enabled: true,
            chain_id: 5042002,
            registry: format!("0x{}", "44".repeat(20)),
            auditor: format!("0x{}", "55".repeat(20)),
            api_url: "http://127.0.0.1".into(),
        };
        let cid = "ar://abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";
        let cid_hex: String = cid.bytes().map(|b| format!("{b:02x}")).collect();
        let market = format!("{:x}", Sha256::digest(b"m-1"));
        let data = format!(
            "{PUBLISH_V2_SELECTOR}{}{market}{:064x}{:064x}{}{}{:0<64}{:064x}{:064x}{:0<128}",
            "0".repeat(64),
            612_345,
            700_000,
            "ab".repeat(32),
            "cd".repeat(32),
            "72722d74726163652f33",
            256,
            cid.len(),
            cid_hex
        );
        let sealed = json!({"status": "sealed", "audit_id": 1, "market_id": "m-1",
            "probability": 0.612345, "confidence": 0.7, "schema_version": "rr-trace/3",
            "trace_hash": format!("0x{}", "ab".repeat(32)), "merkle_root": format!("0x{}", "cd".repeat(32)),
            "trace_cid": cid, "auditor": d.auditor,
            "transaction": {"to": d.registry, "chain_id": 5042002, "value": "0", "data": data}});
        (d, sealed)
    }

    #[test]
    fn route_stages_and_simulates_exact_publish_without_committing() {
        let (d, sealed) = fixture();
        let result = audit_route(sealed.clone(), &d).unwrap();
        let serialized = serde_json::to_value(result).unwrap();
        let routes = serialized["__aomi_tool_routes"].as_array().unwrap();
        assert_eq!(routes.len(), 1);
        assert_eq!(routes[0]["tool"], "stage_tx");
        assert_eq!(routes[0]["args"]["data"], sealed["transaction"]["data"]);
        assert_eq!(routes[0]["args"]["to"], d.registry);
        assert_eq!(routes[0]["enforcement"]["on_failure"], "stop");
        assert_eq!(
            routes[0]["enforcement"]["steps"][0]["tool"],
            "simulate_batch"
        );
        assert_eq!(
            routes[0]["enforcement"]["steps"].as_array().unwrap().len(),
            1
        );
        assert!(!serialized.to_string().contains("commit_txs\""));
    }

    #[test]
    fn changed_seal_or_bytes_never_get_a_route() {
        for (field, value) in [
            ("status", json!("pending")),
            ("auditor", json!(format!("0x{}", "66".repeat(20)))),
            ("market_id", json!("m-2")),
            ("probability", json!(0.9)),
            ("confidence", json!(0.1)),
            ("trace_hash", json!(format!("0x{}", "ef".repeat(32)))),
            ("merkle_root", json!(format!("0x{}", "ef".repeat(32)))),
            ("schema_version", json!("rr-trace/2")),
            ("trace_cid", json!("ar://other")),
        ] {
            let (d, mut sealed) = fixture();
            sealed[field] = value;
            assert!(audit_route(sealed, &d).is_err(), "{field}");
        }
        let (_, sealed) = fixture();
        let data = sealed["transaction"]["data"].as_str().unwrap().to_string();
        let consumer = format!("{}{}{}", &data[..10], "1".repeat(64), &data[74..]);
        let selector = format!("0xa9059cbb{}", &data[10..]);
        let trailing = format!("{data}00");
        for (field, value) in [
            ("chain_id", json!(1)),
            ("value", json!("1")),
            ("to", json!(format!("0x{}", "77".repeat(20)))),
            ("data", json!(consumer)),
            ("data", json!(selector)),
            ("data", json!(trailing)),
            ("data", json!(&data[..data.len() - 64])),
        ] {
            let (d, mut sealed) = fixture();
            sealed["transaction"][field] = value;
            assert!(audit_route(sealed, &d).is_err(), "{field}");
        }
    }

    #[test]
    fn sources_must_be_public_https_names() {
        for url in [
            "http://example.com/a",
            "https://127.0.0.1/a",
            "https://[::1]/a",
            "https://localhost/a",
            "https://metadata.internal/a",
            "https://user:pw@example.com/a",
        ] {
            let (check, excerpt) = check_source(url, "A title");
            assert_eq!(check["error"], "not a public https URL", "{url}");
            assert!(check["http_status"].is_null() && check["content_sha256"].is_null());
            assert!(excerpt.is_empty());
        }
        assert_eq!(check_source("not a url", "").0["error"], "not a valid URL");
        for ip in [
            "10.0.0.1",
            "169.254.169.254",
            "192.168.1.1",
            "100.64.0.1",
            "::1",
            "fd00::1",
            "::ffff:10.0.0.1",
        ] {
            assert!(!public_ip(ip.parse().unwrap()), "{ip}");
        }
        assert!(public_ip("93.184.216.34".parse().unwrap()));
    }

    #[test]
    fn tools_are_skill_owned_and_disabled_by_default() {
        let manifest = RrAuditApp.manifest();
        aomi_sdk::validate_app_skills_with_tools(&manifest.name, &manifest.skills, &manifest.tools)
            .unwrap();
        assert_eq!(manifest.skills[0].injected_tools.len(), 3);
        #[cfg(not(audit_configured))]
        {
            assert!(manifest.namespaces.unwrap().is_empty());
            assert!(manifest.skills[0].guard.is_none());
            let args = json!({"audit_id": 1, "verdict": "approved", "notes": "", "judgments": []});
            assert!(
                run_tool::<SealAudit>(&RrAuditApp, args, TestCtxBuilder::new("seal").build())
                    .is_err()
            );
            assert!(
                run_tool::<NextAudit>(&RrAuditApp, json!({}), TestCtxBuilder::new("next").build())
                    .is_err()
            );
        }
        #[cfg(audit_configured)]
        {
            let d = deployment().unwrap();
            assert_eq!(manifest.namespaces.unwrap(), ["evm-core"]);
            let guard = serde_json::to_value(manifest.skills[0].guard.as_ref().unwrap()).unwrap();
            assert_eq!(guard["evm"]["chain_ids"], json!([d.chain_id]));
            assert_eq!(guard["evm"]["contracts"]["REGISTRY"], d.registry);
            assert_eq!(guard["evm"]["allowed_selectors"], json!(["PUBLISH"]));
        }
    }

    #[cfg(audit_configured)]
    #[test]
    fn only_the_configured_auditor_wallet_can_seal() {
        let d = deployment().unwrap();
        let args = json!({"audit_id": 1, "verdict": "approved", "notes": "", "judgments": []});
        for (chain, address) in [
            (d.chain_id, format!("0x{}", "66".repeat(20))),
            (1, d.auditor.clone()),
        ] {
            let ctx = TestCtxBuilder::new("seal")
                .attribute(
                    "domain",
                    json!({"evm": {"chain_id": chain, "address": address}}),
                )
                .build();
            let refused = run_tool::<SealAudit>(&RrAuditApp, args.clone(), ctx).unwrap_err();
            assert!(refused.contains("auditor wallet"), "{refused}");
        }
    }
}
