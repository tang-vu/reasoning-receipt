//! ReasoningReceipt settlement on Aomi: pay a deployment-configured recipient
//! for an audited reasoning receipt and get back a linked outcome receipt.

mod settlement;

use aomi_sdk::{Secret, dyn_aomi_app};

#[derive(Clone, Default)]
pub struct RrApp;

const PREAMBLE: &str = "You help a user settle an audited ReasoningReceipt: an oracle trace that the independent \
auditor approved and published on chain. Settlement is one wallet-approved USDC transfer whose chain, token, recipient \
and amount are fixed by this app's deployment. A pending, sealed or rejected audit never settles. After the transfer is \
independently verified on chain, the API issues a separate outcome receipt that links to the audited trace.

Activate reasoning-receipt/settlement to prepare and verify a transfer. Rules you must keep:
- Settle only by audit id. Never write, repair or re-hash a receipt yourself, and never work around a blocked audit.
- Only status settled is success. pending, pending_finality and reverted are not outcomes; say so plainly.
- A receipt records evidence for a decision; it does not prove the decision was right.";

macro_rules! register_app {
    ([$($namespace:expr),*] $(, $guard:expr)?) => {
        dyn_aomi_app!(
            app = RrApp,
            name = "reasoning-receipt",
            version = "0.1.0",
            preamble = PREAMBLE,
            tools = [],
            secrets = [
                Secret::new("RR_SETTLEMENT_API_TOKEN", "Settlement API credential. Never a signing key.", false)
            ],
            namespaces = [$($namespace),*],
            skills = [{
                id: "reasoning-receipt/settlement",
                description: "Settle an audited reasoning receipt with one wallet-approved USDC transfer and a linked outcome receipt",
                tags: ["receipt", "settlement", "payment"],
                tools: [settlement::PrepareSettlement, settlement::VerifySettlement],
                sections: {
                    instructions: "skill/instructions.md",
                    workflows: "skill/workflows.md",
                    action_rules: "skill/action-rules.md",
                    safety: "skill/safety.md"
                }
                $(, guard: $guard)?
            }]
        );
    };
}

// Unconfigured artifacts have no EVM namespace and cannot stage a transfer.
#[cfg(not(settlement_configured))]
register_app!([]);
#[cfg(settlement_configured)]
register_app!(
    ["evm-core"],
    concat!(env!("OUT_DIR"), "/settlement-guard.json")
);

#[cfg(test)]
mod tests {
    /// Aomi's deploy gate reads the pin from the repo-root Cargo.toml; the
    /// platform builds this folder with its own. They must agree, exactly.
    #[test]
    fn root_pin_matches_app_pin_and_app_is_its_own_workspace() {
        let pin = |manifest: &str| {
            manifest
                .lines()
                .find(|l| l.trim_start().starts_with("aomi-sdk"))
                .and_then(|l| l.split('"').nth(1))
                .map(str::to_string)
        };
        let here = pin(include_str!("../Cargo.toml")).expect("this App pins aomi-sdk");
        assert!(here.starts_with('='), "Aomi loads only an exact SDK pin");
        assert!(
            include_str!("../Cargo.toml")
                .lines()
                .any(|l| l.trim() == "[workspace]")
        );
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        assert!(
            dir.join("Cargo.lock").is_file(),
            "Cargo.lock must sit beside this App"
        );
        let repo = dir.join("../..");
        if repo.join(".aomi/config.json").is_file() {
            let root = std::fs::read_to_string(repo.join("Cargo.toml"))
                .expect("the repo root needs the Cargo.toml Aomi's deploy gate reads");
            assert_eq!(pin(&root), Some(here), "root pin differs from App pin");
        }
    }
}
