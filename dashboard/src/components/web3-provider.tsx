"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConnectKitProvider } from "connectkit";
import { useState } from "react";
import { WagmiProvider } from "wagmi";

import { wagmiConfig } from "@/lib/web3";

/**
 * Client-only Web3 context boundary. Wraps the app so any descendant page
 * can call `useAccount`, `useConnect`, etc. Lives in a separate file so the
 * root layout stays a server component.
 */
export function Web3Provider({ children }: { children: React.ReactNode }) {
  // QueryClient must be stable across renders — useState ensures one instance per mount.
  const [queryClient] = useState(() => new QueryClient());
  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <ConnectKitProvider
          theme="midnight"
          options={{
            initialChainId: 5_042_002,
            enforceSupportedChains: true,
            disclaimer: (
              <span>
                Arc Testnet only — no real value at stake. The agent operator
                covers gas for free demo queries.
              </span>
            ),
          }}
        >
          {children}
        </ConnectKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
