/**
 * Web3 / wagmi config for the dashboard's `/try-live` flow.
 *
 * Arc Testnet (chain id 5042002) is a Canteen-hosted EVM L1 — not in any
 * standard chain list. We define it inline as a viem custom chain. Users
 * connecting via injected wallets will be prompted to add it on first
 * "connect".
 */
import { createConfig, http } from "wagmi";
import { defineChain } from "viem";
import { injected, walletConnect } from "wagmi/connectors";

export const arcTestnet = defineChain({
  id: 5_042_002,
  name: "Arc Testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: {
    default: {
      http: ["https://rpc.testnet.arc-node.thecanteenapp.com/v1/public"],
    },
  },
  blockExplorers: {
    default: { name: "ArcScan", url: "https://testnet.arcscan.app" },
  },
  testnet: true,
});

// WalletConnect project id — public-safe, only enables wallet-connect modal.
// If absent, ConnectKit still works with injected wallets (MetaMask etc).
const walletConnectProjectId =
  process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || "";

export const wagmiConfig = createConfig({
  chains: [arcTestnet],
  connectors: [
    injected(),
    ...(walletConnectProjectId
      ? [
          walletConnect({
            projectId: walletConnectProjectId,
            metadata: {
              name: "ReasoningReceipt",
              description:
                "x402-paywalled AI oracle with byte-verifiable reasoning traces on Arc",
              url: "https://rrtrace.xyz",
              icons: ["https://rrtrace.xyz/favicon-512.png"],
            },
          }),
        ]
      : []),
  ],
  transports: {
    [arcTestnet.id]: http(),
  },
  ssr: true,
});
