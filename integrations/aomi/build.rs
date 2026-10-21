use serde_json::{Value, json};
use std::{env, fs, path::PathBuf};

// The settlement deployment is baked into the artifact from the same JSON the
// API reads (RR_SETTLEMENT_CONFIG). Without it, or with enabled=false, the app
// has no EVM namespace and its tools refuse before any HTTP call.
fn main() {
    println!("cargo::rustc-check-cfg=cfg(settlement_configured)");
    println!("cargo::rerun-if-env-changed=RR_SETTLEMENT_CONFIG");
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let config = match env::var("RR_SETTLEMENT_CONFIG") {
        Ok(path) => {
            println!("cargo::rerun-if-changed={path}");
            serde_json::from_str::<Value>(
                &fs::read_to_string(path).expect("read settlement deployment"),
            )
            .expect("valid settlement deployment JSON")
        }
        Err(_) => json!({"enabled": false}),
    };
    if config["enabled"] == true {
        let chain = config["chain_id"]
            .as_u64()
            .expect("chain_id must be a number");
        assert!(chain > 0 && chain < (1 << 53), "valid chain id required");
        for key in ["token", "recipient"] {
            let a = config[key].as_str().expect("address required");
            assert!(
                a.len() == 42
                    && a.starts_with("0x")
                    && a[2..].bytes().all(|b| b.is_ascii_hexdigit())
                    && a[2..].bytes().any(|b| b != b'0'),
                "replace {key} with a nonzero address"
            );
        }
        let amount = config["amount_units"]
            .as_str()
            .expect("amount_units must be an integer string");
        assert!(
            amount.parse::<u128>().is_ok_and(|a| a > 0),
            "amount_units must be a positive integer in token base units"
        );
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
            out.join("settlement-guard.json"),
            json!({"evm": {
                "chain_ids": [chain], "contracts": {"USDC": config["token"]},
                "selectors": {"TRANSFER": "transfer(address,uint256)"},
                "allowed_contracts": ["USDC"], "allowed_selectors": ["TRANSFER"]
            }})
            .to_string(),
        )
        .unwrap();
        println!("cargo::rustc-cfg=settlement_configured");
    }
    fs::write(out.join("settlement-deployment.json"), config.to_string()).unwrap();
}
