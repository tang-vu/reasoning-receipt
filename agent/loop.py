"""Continuous agent loop — scanner → analyst → trace → trader → on-chain.

Runs indefinitely. Default cadence: scan every 60s, batch-process 3 candidates
per tick. Backs off on persistent errors.

Entry point (`rr-agent`):
    python -m agent.loop
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from dataclasses import dataclass

from dotenv import load_dotenv

from server.chain import ChainClient
from storage.db import Receipt as ReceiptRow
from storage.db import Session, init_db
from storage.irys import IrysClient
from wallets.portfolio import Portfolio

from .analyst import Analyst, MarketCandidate
from .calibration_store import CalibrationStore
from .critic import Critic
from .ensemble import Ensemble
from .memory import MarketMemory
from .resolver import resolve_open_markets
from .scanner import Scanner
from .trace import SealedTrace, TraceSealer
from .trace_v3 import ReasoningTraceV3
from .trader import Trader

logger = logging.getLogger("rr.agent")


@dataclass(slots=True)
class LoopConfig:
    scan_interval_s: float = 60.0
    per_tick: int = 3
    error_backoff_s: float = 15.0
    enable_trader: bool = True
    # Time-to-live for the "recently priced" set. After this many seconds, a
    # market becomes eligible to be re-priced. 0 means never re-price (single
    # pass through the candidate list).
    market_cooldown_s: float = 300.0

    @classmethod
    def from_env(cls) -> LoopConfig:
        return cls(
            scan_interval_s=float(os.getenv("RR_LOOP_INTERVAL_S", "60")),
            per_tick=int(os.getenv("RR_LOOP_PER_TICK", "3")),
            error_backoff_s=float(os.getenv("RR_LOOP_BACKOFF_S", "15")),
            enable_trader=os.getenv("RR_LOOP_TRADER", "1").lower() in {"1", "true", "yes"},
            market_cooldown_s=float(os.getenv("RR_LOOP_MARKET_COOLDOWN_S", "300")),
        )


class AgentLoop:
    """Composition root for the autonomous oracle loop."""

    def __init__(self, *, config: LoopConfig | None = None) -> None:
        self.config = config or LoopConfig.from_env()
        self.scanner = Scanner()
        self.analyst = Analyst()
        self.critic = Critic()
        # Ensemble is constructed lazily so existing rr-trace/2 deployments
        # don't pay the Vertex-client init cost unless RR_USE_ENSEMBLE=1.
        self.use_ensemble = os.getenv("RR_USE_ENSEMBLE", "").lower() in {"1", "true", "yes"}
        self._ensemble: Ensemble | None = Ensemble() if self.use_ensemble else None
        # Calibration feedback — supervisor reads per-category Brier + bias
        # before each synthesis. 30-min cache, so per-tick cost is negligible.
        self._calibration: CalibrationStore | None = (
            CalibrationStore() if self.use_ensemble else None
        )
        # Market memory — supervisor also reads the most-similar resolved markets
        # the agent already called (retrieval prior). Self-syncs from resolved
        # receipts; empty until markets resolve, so it's a no-op on a cold DB.
        # Disabled when the LLM provider has no embedding model (e.g. MiMo):
        # without real embeddings the retrieval is meaningless and would write
        # mock vectors into the live memory store, so we skip the experience
        # prior entirely rather than pollute it.
        embeddings_available = os.getenv("RR_LLM_PROVIDER", "").strip().lower() != "mimo"
        self._memory: MarketMemory | None = (
            MarketMemory() if (self.use_ensemble and embeddings_available) else None
        )
        self._irys = IrysClient()
        self.sealer = TraceSealer(self._irys)
        self.chain = ChainClient()
        self.portfolio = Portfolio()
        self.trader = Trader(bankroll_provider=self.portfolio.bankroll)
        self._stop = False
        self._processed: dict[str, float] = {}  # market_id → epoch seconds it was last priced
        self._tick_count = 0
        # Run the resolver every N ticks (~10 min at default 60s interval). It's
        # a polite Gamma API poll, so we don't want to hammer it every tick.
        self._resolver_every = int(os.getenv("RR_RESOLVER_EVERY_TICKS", "10"))

    def stop(self) -> None:
        self._stop = True

    async def run_forever(self) -> None:
        logger.info(
            "loop: starting (interval=%.1fs per_tick=%d trader=%s chain_mock=%s)",
            self.config.scan_interval_s,
            self.config.per_tick,
            self.config.enable_trader,
            self.chain.mock,
        )
        while not self._stop:
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                logger.exception("loop: tick failed (%s); backing off", exc)
                await asyncio.sleep(self.config.error_backoff_s)
                continue
            await asyncio.sleep(self.config.scan_interval_s)

    async def _tick(self) -> None:
        loop = asyncio.get_running_loop()
        self._tick_count += 1

        # Every Nth tick, back-fill resolved outcomes via Polymarket Gamma.
        if self._resolver_every > 0 and self._tick_count % self._resolver_every == 0:
            try:
                report = await loop.run_in_executor(None, resolve_open_markets)
                if report.newly_resolved_markets:
                    logger.info(
                        "resolver: polled=%d newly_resolved=%d rows_updated=%d",
                        report.polled,
                        report.newly_resolved_markets,
                        report.rows_updated,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("resolver: tick failed (%s)", str(exc)[:200])

        candidates = await loop.run_in_executor(None, self.scanner.scan)
        now = time.time()
        cooldown = self.config.market_cooldown_s
        eligible = [
            c
            for c in candidates
            if cooldown <= 0
            or self._processed.get(c.market_id, 0) + cooldown <= now
        ]
        for candidate in eligible[: self.config.per_tick]:
            try:
                await loop.run_in_executor(None, self._process_candidate, candidate)
            except Exception as exc:  # noqa: BLE001
                logger.warning("loop: skipped %s after error (%s)", candidate.market_id, str(exc)[:200])
            # Stamp processed regardless of success so we don't immediately retry
            # the same bad market on the next tick. TTL still lets it come back.
            self._processed[candidate.market_id] = time.time()

    def _process_candidate(self, candidate: MarketCandidate) -> None:
        if self._ensemble is not None:
            self._process_candidate_ensemble(candidate)
            return
        start = time.perf_counter()
        trace = self.analyst.analyse_with_critic(candidate, critic=self.critic)
        sealed: SealedTrace = self.sealer.seal(trace)
        result = self.chain.publish(
            consumer_address=None,
            market_id=candidate.market_id,
            probability=trace.probability,
            confidence=trace.confidence,
            trace_hash_hex=sealed.hash_hex,
            trace_cid=sealed.cid,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        with Session() as session:
            row = ReceiptRow(
                chain_receipt_id=result.receipt_id,
                market_id=candidate.market_id,
                market_question=candidate.question,
                market_source=candidate.source,
                probability=trace.probability,
                confidence=trace.confidence,
                trace_hash=sealed.hash_hex,
                trace_cid=sealed.cid,
                consumer_address=None,
                publisher_address=self.chain.publisher_address,
                paid_micro_usdc=0,
                arc_tx_hash=result.tx_hash,
                arc_block_number=result.block_number,
                latency_ms=latency_ms,
                schema_version=trace.schema_version or "rr-trace/2",
            )
            session.add(row)
            session.flush()
            receipt_id = row.id
        logger.info(
            "loop: priced %s prob=%.3f conf=%.3f tx=%s",
            candidate.market_id,
            trace.probability,
            trace.confidence,
            result.tx_hash[:12],
        )
        if self.config.enable_trader:
            decision = self.trader.decide(candidate=candidate, trace=trace)
            self.trader.execute(
                candidate=candidate,
                trace=trace,
                decision=decision,
                receipt_id=receipt_id,
            )

    def _process_candidate_ensemble(self, candidate: MarketCandidate) -> None:
        """rr-trace/3 path. Bull/Bear/Edge + Supervisor → v3 trace → Irys → V1 emit.

        The V1 contract emit is byte-agnostic: it stores a hash + CID, schema-
        version-blind. Phase 4 swaps in V2 contract emit with the Merkle root
        as a second on-chain field. Trader is disabled on this path until
        Phase 5 wires the v3-trace projection — the ensemble probability is
        still recorded in DB so Phase 5's calibration loop has the data.
        """
        assert self._ensemble is not None
        start = time.perf_counter()
        # Pull the calibration prior — empty string when no category has enough
        # resolved markets yet. Empty → supervisor gets no PRIOR block in prompt.
        prior = self._calibration.prior_text() if self._calibration else ""
        # Experience prior — similar resolved markets. Best-effort: a memory
        # failure must never block pricing, so swallow + continue without it.
        experience = ""
        if self._memory is not None:
            try:
                experience = self._memory.prior_text(candidate.question)
            except Exception as exc:  # noqa: BLE001
                logger.warning("loop[v3]: memory retrieve failed (%s); no experience prior", exc)
        trace_v3: ReasoningTraceV3 = self._ensemble.analyse(
            candidate,
            calibration_prior=prior or None,
            experience_prior=experience or None,
        )

        # Critic verdict gates publication. "rejected" means the trace failed
        # the rigor audit even after a revision pass — emitting it would
        # contaminate the calibration data, so log + skip.
        if trace_v3.critic_audit.verdict == "rejected":
            logger.warning(
                "loop[v3]: REJECTED %s (critic) — not emitting; weak dims=%s",
                candidate.market_id,
                [d for d in ("evidence_relevance", "falsifiability", "scope", "coherence",
                             "exploration_integrity", "methodology")
                 if getattr(trace_v3.critic_audit, d).score < 0.4],
            )
            return

        upload = self._irys.upload(trace_v3.to_dict())
        merkle_root_hex = trace_v3.merkle_root_hex()
        result = self.chain.publish_v2(
            consumer_address=None,
            market_id=candidate.market_id,
            probability=trace_v3.claim.probability,
            confidence=trace_v3.claim.confidence,
            trace_hash_hex=upload.hash_hex,
            merkle_root_hex=merkle_root_hex,
            schema_version=trace_v3.schema_version,
            trace_cid=upload.cid,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        with Session() as session:
            row = ReceiptRow(
                chain_receipt_id=result.receipt_id,
                market_id=candidate.market_id,
                market_question=candidate.question,
                market_source=candidate.source,
                probability=trace_v3.claim.probability,
                confidence=trace_v3.claim.confidence,
                trace_hash=upload.hash_hex,
                trace_cid=upload.cid,
                consumer_address=None,
                publisher_address=self.chain.publisher_address,
                paid_micro_usdc=0,
                arc_tx_hash=result.tx_hash,
                arc_block_number=result.block_number,
                latency_ms=latency_ms,
                schema_version=trace_v3.schema_version,
                disagreement_pp=trace_v3.supervisor_synthesis.disagreement_pp,
                merkle_root=merkle_root_hex,
                category=trace_v3.category,
            )
            session.add(row)
            session.flush()
        logger.info(
            "loop[v3]: priced %s prob=%.3f conf=%.3f disagreement=%.1fpp cat=%s tx=%s",
            candidate.market_id,
            trace_v3.claim.probability,
            trace_v3.claim.confidence,
            trace_v3.supervisor_synthesis.disagreement_pp,
            trace_v3.category,
            result.tx_hash[:12],
        )


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    )
    init_db()
    loop = AgentLoop()
    runner = asyncio.new_event_loop()

    def _shutdown(*_args) -> None:
        logger.info("loop: shutdown requested")
        loop.stop()

    try:
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
    except (ValueError, AttributeError):
        pass

    runner.run_until_complete(loop.run_forever())


if __name__ == "__main__":
    main()
