use serde_json::{Value, json};
use std::{env, fs, path::PathBuf};

// The audit deployment is baked into the artifact from the same JSON the API
// reads. Inline JSON and an explicit file override the committed Arc profile.
// An explicitly disabled build has no EVM namespace and refuses all tools.
fn main() {
    println!("cargo::rustc-check-cfg=cfg(audit_configured)");
    println!("cargo::rerun-if-env-changed=RR_AUDIT_CONFIG");
    println!("cargo::rerun-if-env-changed=RR_AUDIT_CONFIG_JSON");
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let config = if let Some(raw) = env::var("RR_AUDIT_CONFIG_JSON")
        .ok()
        .filter(|value| !value.trim().is_empty())
    {
        serde_json::from_str::<Value>(&raw).expect("valid inline audit deployment JSON")
    } else {
        match env::var("RR_AUDIT_CONFIG")
            .ok()
            .filter(|path| !path.trim().is_empty())
        {
            Some(path) => {
                println!("cargo::rerun-if-changed={path}");
                serde_json::from_str::<Value>(
                    &fs::read_to_string(path).expect("read audit deployment"),
                )
                .expect("valid audit deployment JSON")
            }
            None => {
                let profile = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap())
                    .join("deployment.arc-testnet.json");
                println!("cargo::rerun-if-changed={}", profile.display());
                if profile.is_file() {
                    serde_json::from_str::<Value>(
                        &fs::read_to_string(profile).expect("read Arc testnet profile"),
                    )
                    .expect("valid Arc testnet profile JSON")
                } else {
                    json!({"enabled": false})
                }
            }
        }
    };
    assert!(config.is_object(), "audit deployment must be a JSON object");
    if config["enabled"] == true {
        let chain = config["chain_id"]
            .as_u64()
            .expect("chain_id must be a number");
        assert!(chain > 0 && chain < (1 << 53), "valid chain id required");
        for key in ["registry", "auditor"] {
            let a = config[key].as_str().expect("address required");
            assert!(
                a.len() == 42
                    && a.starts_with("0x")
                    && a[2..].bytes().all(|b| b.is_ascii_hexdigit())
                    && a[2..].bytes().any(|b| b != b'0'),
                "replace {key} with a nonzero address"
            );
        }
        let url = config["api_url"].as_str().expect("API URL required");
        let url = reqwest::Url::parse(url).expect("valid API URL");
        assert!(
            url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none()
                && url.path() == "/"
                && (url.scheme() == "https"
                    || (url.scheme() == "http"
                        && matches!(url.host_str(), Some("127.0.0.1" | "localhost")))),
            "HTTPS origin or local test origin required"
        );
        fs::write(
            out.join("audit-guard.json"),
            json!({"evm": {
                "chain_ids": [chain], "contracts": {"REGISTRY": config["registry"]},
                "selectors": {"PUBLISH": "publishV2(address,bytes32,uint32,uint32,bytes32,bytes32,bytes16,string)"},
                "allowed_contracts": ["REGISTRY"], "allowed_selectors": ["PUBLISH"]
            }})
            .to_string(),
        )
        .unwrap();
        println!("cargo::rustc-cfg=audit_configured");
    }
    fs::write(out.join("audit-deployment.json"), config.to_string()).unwrap();
}
