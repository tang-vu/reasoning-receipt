use serde_json::{Value, json};
use std::{env, fs, path::PathBuf};

// The audit deployment is baked into the artifact from the same JSON the API
// reads (RR_AUDIT_CONFIG). Without it, or with enabled=false, the app has no
// EVM namespace and its tools refuse before any HTTP call.
fn main() {
    println!("cargo::rustc-check-cfg=cfg(audit_configured)");
    println!("cargo::rerun-if-env-changed=RR_AUDIT_CONFIG");
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let config = match env::var("RR_AUDIT_CONFIG") {
        Ok(path) => {
            println!("cargo::rerun-if-changed={path}");
            serde_json::from_str::<Value>(&fs::read_to_string(path).expect("read audit deployment"))
                .expect("valid audit deployment JSON")
        }
        Err(_) => json!({"enabled": false}),
    };
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
