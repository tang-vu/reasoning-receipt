//! Deployment-bound settlement tools. No caller-controlled chain, token,
//! recipient, amount, payer or API origin.
use crate::RrApp;
use aomi_sdk::{
    DynAomiTool, DynToolCallCtx, EnforcementPolicy, ToolReturn, host, resolve_secret_value,
};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{sync::OnceLock, time::Duration};

#[derive(Deserialize)]
pub struct Deployment {
    pub enabled: bool,
    #[serde(default)]
    pub chain_id: u64,
    #[serde(default)]
    pub token: String,
    #[serde(default)]
    pub recipient: String,
    #[serde(default)]
    pub amount_units: String,
    #[serde(default)]
    pub api_url: String,
}

fn deployment() -> Result<Deployment, String> {
    let value: Value = serde_json::from_str(include_str!(concat!(
        env!("OUT_DIR"),
        "/settlement-deployment.json"
    )))
    .unwrap();
    if value["enabled"] != true {
        return Err("Settlement transfers are disabled until a recipient is configured.".into());
    }
    serde_json::from_value(value).map_err(|_| "Invalid settlement deployment".into())
}

fn request(ctx: &DynToolCallCtx, d: &Deployment, path: &str, body: Value) -> Result<Value, String> {
    let token = resolve_secret_value(ctx, None, "RR_SETTLEMENT_API_TOKEN", "")
        .map_err(|_| "Configure the settlement API credential in the app environment.")?;
    static HTTP: OnceLock<reqwest::blocking::Client> = OnceLock::new();
    let http = HTTP.get_or_init(|| {
        reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(45))
            .connect_timeout(Duration::from_secs(10))
            // A redirect must not carry this credential or payment request elsewhere.
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .unwrap()
    });
    let url = format!("{}{}", d.api_url.trim_end_matches('/'), path);
    let response = http
        .post(url)
        .json(&body)
        .bearer_auth(token)
        .send()
        .map_err(
            |_| "Settlement API unavailable. Retry the read; never resubmit an uncertain payment.",
        )?;
    let status = response.status();
    if !status.is_success() {
        let detail = response
            .json::<Value>()
            .ok()
            .and_then(|v| v["detail"].as_str().map(str::to_owned));
        // Relay only the API's own static refusals, never arbitrary upstream bodies.
        if let Some(message) = detail.filter(|s| {
            matches!(
                s.as_str(),
                "Settlement transfers are disabled until a recipient is configured"
                    | "Connected wallet is on the wrong network"
                    | "No audit with this id; nothing was prepared"
                    | "The audit rejected this trace; settlement is blocked"
                    | "This trace has no published audit yet; settlement is blocked"
                    | "Simulation failed; nothing was prepared and nothing may be submitted"
                    | "This receipt is already settled; verify its transaction instead of paying again"
                    | "No prepared settlement for this receipt"
                    | "This receipt was already settled by a different transaction"
                    | "This transaction already settled a different receipt"
                    | "Deployment changed since preparation; prepare and approve again"
                    | "Transaction is not in the canonical chain; nothing was recorded"
                    | "Transaction does not contain the exact configured transfer"
                    | "RPC cannot report finality; nothing was recorded"
            )
        }) {
            return Err(message);
        }
        return Err(match status.as_u16() {
            401 | 403 => "Settlement access denied. Check the app credential.",
            404 => "No prepared settlement was found.",
            409 => "Settlement blocked by its current state. Do not submit another payment.",
            422 => "Invalid settlement request; do not change the audit to work around it.",
            _ => "Settlement state unavailable. Do not submit a payment.",
        }
        .into());
    }
    response
        .json()
        .map_err(|_| "Invalid settlement API response; stop.".into())
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PrepareArgs {
    /// Id of the audit to pay for. Only an audit the auditor approved and published settles.
    pub audit_id: u64,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct VerifyArgs {
    /// audit_id that rr_prepare_settlement prepared.
    pub audit_id: u64,
    /// Actual broadcast hash returned by the connected wallet, never an invented identifier.
    pub transaction_hash: String,
}

fn is_hash(value: &str) -> bool {
    value.len() == 66
        && value.starts_with("0x")
        && value[2..].bytes().all(|b| b.is_ascii_hexdigit())
}

pub struct PrepareSettlement;
impl DynAomiTool for PrepareSettlement {
    type App = RrApp;
    type Args = PrepareArgs;
    const NAME: &'static str = "rr_prepare_settlement";
    const DESCRIPTION: &'static str = "Confirm the audit was approved and published on chain, then prepare the deployment's one unsigned USDC transfer from the connected wallet. The API simulates it first and refuses if it would fail. Stages the exact bytes and simulates them; commit only after explicit wallet approval. Never automatically retry submission.";
    fn run_with_routes(
        _: &RrApp,
        args: PrepareArgs,
        ctx: DynToolCallCtx,
    ) -> Result<ToolReturn, String> {
        let d = deployment()?;
        if ctx.attribute_u64(&["domain", "evm", "chain_id"]) != Some(d.chain_id) {
            return Err("Connect the paying wallet on the configured settlement network.".into());
        }
        let payer = ctx
            .attribute_string(&["domain", "evm", "address"])
            .filter(|a| {
                a.len() == 42
                    && a.starts_with("0x")
                    && a[2..].bytes().all(|b| b.is_ascii_hexdigit())
                    && a[2..].bytes().any(|b| b != b'0')
            })
            .ok_or("Connect the paying wallet; no address override is accepted.")?;
        let result = request(
            &ctx,
            &d,
            "/v1/settlements/prepare",
            json!({"audit_id": args.audit_id, "execution_account": payer, "chain_id": d.chain_id}),
        )?;
        settlement_route(result, &d, &payer)
    }
}

fn settlement_route(result: Value, d: &Deployment, payer: &str) -> Result<ToolReturn, String> {
    let tx = &result["transaction"];
    let data = tx["data"].as_str().unwrap_or("");
    let same = |field: &Value, expected: &str| {
        field
            .as_str()
            .is_some_and(|v| v.eq_ignore_ascii_case(expected))
    };
    if !d.enabled
        || result["status"] != "prepared"
        || result["chain_id"] != d.chain_id
        || !same(&result["token"], &d.token)
        || !same(&result["recipient"], &d.recipient)
        || result["amount_units"] != d.amount_units
        || !same(&result["payer"], payer)
        || !result["trace_hash"].as_str().is_some_and(is_hash)
        || tx["chain_id"] != d.chain_id
        || tx["value"] != "0"
        || !same(&tx["to"], &d.token)
        || data.len() != 2 + 8 + 64 * 2
        || !data.starts_with("0x")
        || !data[2..].bytes().all(|b| b.is_ascii_hexdigit())
    {
        return Err(
            "Prepared transfer does not match this app's deployment and wallet; stop.".into(),
        );
    }
    // Decode both ABI words so the preview cannot diverge from the staged bytes.
    let recipient = format!("0x{}", &data[34..74]);
    let amount = u128::from_str_radix(&data[74..138], 16)
        .map_err(|_| "Transfer amount outside supported exact range")?;
    if !data[..10].eq_ignore_ascii_case(TRANSFER_SELECTOR)
        || data[10..34].bytes().any(|b| b != b'0')
        || !recipient.eq_ignore_ascii_case(&d.recipient)
        || amount.to_string() != d.amount_units
    {
        return Err("Transfer preview differs from the encoded transaction; stop.".into());
    }
    let trace_hash = result["trace_hash"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    let stage = json!({"to": d.token, "data": data, "value": "0",
        "description": format!("Settle audited trace {trace_hash}: transfer {amount} USDC base units to {recipient} on chain {}", d.chain_id),
        "kind": "rr_settlement"});
    ToolReturn::route(result)
        .next(|next| {
            next.add::<host::StageTx>(stage)
                // The host simulates the staged bytes immediately; a failure stops the plan.
                .enforce(EnforcementPolicy::Stop, |enforce| {
                    enforce.add::<host::SimulateBatch>(json!({}));
                })
                .note("Stage these exact bytes unchanged; the host simulates them. If simulation fails, stop and tell the user nothing was sent. Otherwise show the preview and call commit_txs for this one transaction only after the user explicitly approves it, then call rr_verify_settlement with the wallet's transaction_hash. Never resubmit automatically.");
        })
        .try_build()
}

// keccak256("transfer(address,uint256)")[0..4]
const TRANSFER_SELECTOR: &str = "0xa9059cbb";

pub struct VerifySettlement;
impl DynAomiTool for VerifySettlement {
    type App = RrApp;
    type Args = VerifyArgs;
    const NAME: &'static str = "rr_verify_settlement";
    const DESCRIPTION: &'static str = "Independently verify the wallet's finalized transaction against the configured transfer and record the linked outcome receipt. Safe to repeat with the same hash. Only status settled is success; pending, pending_finality and reverted mean no outcome was recorded.";
    fn run(_: &RrApp, args: VerifyArgs, ctx: DynToolCallCtx) -> Result<Value, String> {
        if !is_hash(&args.transaction_hash) {
            return Err(
                "Provide the prepared audit_id and the wallet's 32-byte transaction hash.".into(),
            );
        }
        let d = deployment()?;
        let result = request(
            &ctx,
            &d,
            "/v1/settlements/verify",
            json!({"audit_id": args.audit_id, "transaction_hash": args.transaction_hash}),
        )?;
        let links_back =
            result["outcome_receipt"]["metadata"]["links"]["audit_id"] == json!(args.audit_id);
        if result["status"] == "settled" && !links_back {
            return Err("Outcome receipt does not link to this audit; stop.".into());
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
            token: format!("0x36{}", "0".repeat(38)),
            recipient: format!("0x{}", "22".repeat(20)),
            amount_units: "10000".into(),
            api_url: "http://127.0.0.1".into(),
        };
        let data = format!(
            "{TRANSFER_SELECTOR}{}{}{:064x}",
            "0".repeat(24),
            "22".repeat(20),
            10000u64
        );
        let p = json!({"status": "prepared", "chain_id": 5042002, "token": d.token,
            "recipient": d.recipient, "amount_units": "10000", "payer": format!("0x{}", "33".repeat(20)),
            "trace_hash": format!("0x{}", "cd".repeat(32)),
            "transaction": {"to": d.token, "chain_id": 5042002, "value": "0", "data": data}});
        (d, p)
    }

    #[test]
    fn route_stages_and_simulates_exact_transfer_without_committing() {
        let (d, p) = fixture();
        let result = settlement_route(p.clone(), &d, p["payer"].as_str().unwrap()).unwrap();
        let serialized = serde_json::to_value(result).unwrap();
        let routes = serialized["__aomi_tool_routes"].as_array().unwrap();
        assert_eq!(routes.len(), 1);
        assert_eq!(routes[0]["tool"], "stage_tx");
        assert_eq!(routes[0]["args"]["data"], p["transaction"]["data"]);
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
    fn changed_preview_or_bytes_never_get_a_route() {
        for field in [
            "status",
            "token",
            "recipient",
            "amount_units",
            "payer",
            "trace_hash",
        ] {
            let (d, mut p) = fixture();
            let payer = p["payer"].as_str().unwrap().to_string();
            p[field] = json!("changed");
            assert!(settlement_route(p, &d, &payer).is_err(), "{field}");
        }
        let other = format!(
            "{TRANSFER_SELECTOR}{}{}{:064x}",
            "0".repeat(24),
            "44".repeat(20),
            10000u64
        );
        let more = format!(
            "{TRANSFER_SELECTOR}{}{}{:064x}",
            "0".repeat(24),
            "22".repeat(20),
            10001u64
        );
        for (field, value) in [
            ("chain_id", json!(1)),
            ("value", json!("1")),
            ("to", json!(format!("0x{}", "44".repeat(20)))),
            ("data", json!(other)),
            ("data", json!(more)),
            ("data", json!("0x095ea7b3")),
        ] {
            let (d, mut p) = fixture();
            let payer = p["payer"].as_str().unwrap().to_string();
            p["transaction"][field] = value;
            assert!(settlement_route(p, &d, &payer).is_err(), "{field}");
        }
        let (d, p) = fixture();
        assert!(settlement_route(p, &d, &format!("0x{}", "55".repeat(20))).is_err());
    }

    #[test]
    fn tools_are_skill_owned_and_disabled_by_default() {
        let manifest = RrApp.manifest();
        aomi_sdk::validate_app_skills_with_tools(&manifest.name, &manifest.skills, &manifest.tools)
            .unwrap();
        assert_eq!(manifest.skills[0].injected_tools.len(), 2);
        #[cfg(not(settlement_configured))]
        {
            assert!(manifest.namespaces.unwrap().is_empty());
            assert!(manifest.skills[0].guard.is_none());
            let ctx = TestCtxBuilder::new("prepare")
                .attribute("domain", json!({"evm": {"chain_id": 5042002, "address": format!("0x{}", "33".repeat(20))}}))
                .build();
            let refused = run_tool::<PrepareSettlement>(&RrApp, json!({"audit_id": 1}), ctx);
            assert!(refused.is_err());
        }
        #[cfg(settlement_configured)]
        {
            let d = deployment().unwrap();
            assert_eq!(manifest.namespaces.unwrap(), ["evm-core"]);
            let guard = serde_json::to_value(manifest.skills[0].guard.as_ref().unwrap()).unwrap();
            assert_eq!(guard["evm"]["chain_ids"], json!([d.chain_id]));
            assert_eq!(guard["evm"]["contracts"]["USDC"], d.token);
            assert_eq!(guard["evm"]["allowed_selectors"], json!(["TRANSFER"]));
        }
    }

    #[test]
    fn payer_comes_only_from_host_context() {
        let args = json!({"audit_id": 1, "execution_account": format!("0x{}", "44".repeat(20))});
        assert!(
            run_tool::<PrepareSettlement>(&RrApp, args, TestCtxBuilder::new("prepare").build())
                .is_err()
        );
    }
}
