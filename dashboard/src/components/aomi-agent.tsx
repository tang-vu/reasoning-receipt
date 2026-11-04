"use client";

import { AomiWidget } from "@aomi-labs/widget";
import "@aomi-labs/widget/styles.css";

// The hosted Aomi app built from integrations/aomi. Every chat runs that one
// app directly; its chain, token, recipient and amount come from the app's
// deployment, never from this page.
export function AomiAgent({ applicationId }: { applicationId: number }) {
  return (
    <AomiWidget
      applicationId={applicationId}
      routing={{ defaultMode: "direct", targets: [{ mode: "direct", apps: [{ applicationId }] }] }}
      theme="dark"
      width="100%"
      height="100%"
      showSidebar={false}
      walletFamilies={["evm"]}
      features={{ library: false, theme: false }}
      persistThread
    />
  );
}
