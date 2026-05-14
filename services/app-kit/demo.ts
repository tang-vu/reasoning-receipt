/**
 * App Kit Unified Balance demo for ReasoningReceipt.
 *
 * The agent's deployer wallet (DEPLOYER_PRIVATE_KEY) holds testnet USDC on
 * multiple chains from the CCTP V2 demo (Sepolia, Arc Testnet, etc.). The
 * Unified Balance Kit gives one view of those balances and lets the agent
 * spend from them as a single pool — judges can see Circle's newest 2026 SDK
 * wrapped into a real production codebase, not a stand-alone toy.
 *
 * Usage:
 *   npm --prefix services/app-kit run balance   # read-only balance dump
 *   npm --prefix services/app-kit run spend     # execute a small spend
 *
 * Output is structured JSON so the dashboard's /try page can quote it
 * verbatim without paraphrasing.
 */
import {
  AppKit,
  type GetBalancesResult,
} from "@circle-fin/app-kit";
import { createViemAdapterFromPrivateKey } from "@circle-fin/adapter-viem-v2";
import { privateKeyToAccount } from "viem/accounts";

const PRIVATE_KEY = process.env.DEPLOYER_PRIVATE_KEY;
if (!PRIVATE_KEY) {
  console.error("DEPLOYER_PRIVATE_KEY env var is required");
  process.exit(1);
}

// Default recipient is the agent's portfolio wallet on Arc; override via CLI.
const RECIPIENT =
  process.env.APP_KIT_RECIPIENT ?? "0x0077777d7EBA4688BDeF3E311b846F25870A19B9";
// Conservative — $0.10 per smoke run keeps the agent funded across many test runs.
const SPEND_AMOUNT = process.env.APP_KIT_SPEND_AMOUNT ?? "0.10";

const args = new Set(process.argv.slice(2));
const wantSpend = args.has("--spend");
const wantBalance = args.has("--balance") || !wantSpend;

async function readBalances(kit: AppKit, account: `0x${string}`): Promise<GetBalancesResult> {
  return kit.unifiedBalance.getBalances({
    token: "USDC",
    // SDK accepts `address` (or `adapter`); the public docs example shows
    // `account` but the runtime validator rejects it.
    sources: { address: account },
    networkType: "testnet",
    includePending: true,
  } as Parameters<typeof kit.unifiedBalance.getBalances>[0]);
}

async function main() {
  // Derive the EOA address from the private key — App Kit accepts a raw
  // account string for read-only balance queries, no adapter needed.
  const account = privateKeyToAccount(PRIVATE_KEY as `0x${string}`).address;

  // Adapter is only built when we actually need to sign a spend.
  const adapter = wantSpend
    ? createViemAdapterFromPrivateKey({ privateKey: PRIVATE_KEY as `0x${string}` })
    : null;

  const kit = new AppKit();

  if (wantBalance) {
    const balances = await readBalances(kit, account);
    console.log(JSON.stringify({ stage: "balance", account, balances }, null, 2));
  }

  if (wantSpend && adapter) {
    // Subscribe to lifecycle events so the dashboard can quote the real
    // event stream emitted during a spend.
    kit.unifiedBalance.on("*", (payload) => {
      console.log(JSON.stringify({ event: payload }));
    });

    const result = await kit.unifiedBalance.spend({
      from: { adapter },
      to: { adapter, chain: "Arc_Testnet" },
      token: "USDC",
      amount: SPEND_AMOUNT,
      recipientAddress: RECIPIENT as `0x${string}`,
    } as Parameters<typeof kit.unifiedBalance.spend>[0]);
    console.log(JSON.stringify({ stage: "spend", result }, null, 2));
  }
}

main().catch((err) => {
  console.error("app-kit demo failed:", err);
  process.exit(1);
});
