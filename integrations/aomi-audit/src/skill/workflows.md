# Take, judge, seal, publish, confirm
1. Call rr_next_audit. empty: nothing is waiting; stop. sealed: an approved audit is
   waiting for its wallet and its publish is already staged. Ask the user whether a
   transaction was already sent for it; if so, call rr_confirm_published with that hash
   and do not commit, otherwise continue at step 5.
2. For each source, read check and page_excerpt. A source supports its citation only if
   it was retrieved (2xx status, content hash present) and the excerpt shows what
   cited_for says. A failed fetch, a paywall, a different topic or a page that does not
   mention the figure does not support it. The title match is a hint, not proof.
3. Judge the trace as a whole: does the claim and its probability follow from the
   stances and evidence, and are counter-arguments addressed? Then call rr_seal_audit
   with one judgment per source, a verdict and short notes. Approve only if the
   reasoning holds on the sources you could read. The API skips pages that refused
   the fetch and rejects the audit unless most of the remaining sources support it.
4. rejected: say why; nothing is published, and the next trace can be audited.
   sealed: follow the stage_tx route byte for byte. The host simulates it right away.
   If simulation fails, stop: nothing may be published.
5. Show the preview (market, trace hash, Merkle root, auditor wallet, registry) and ask
   for explicit approval. Only then call commit_txs for that one transaction and let the
   user approve it in the auditor wallet. Never use unattended signing.
6. With the wallet's transaction_hash, call rr_confirm_published. Only status published
   is success. pending or pending_finality: wait and confirm the same hash again.
   reverted: nothing was published; the sealed audit can be published again from step 4.
If the broadcast result is unknown, recover the hash from the wallet and confirm it.
Never publish the same audit a second time to find out.
