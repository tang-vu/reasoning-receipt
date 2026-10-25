"""Offline publication recovery: no provider, wallet funds or RPC are used."""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from eth_abi import encode
from eth_account import Account
from eth_utils import keccak


@pytest.fixture
def driver(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "e2e-audit-testnet.py"
    spec = importlib.util.spec_from_file_location("audit_e2e_recovery", path)
    module = importlib.util.module_from_spec(spec)
    # Import must not initialize services or require any credentials.
    monkeypatch.delenv("RR_AUDITOR_ARC_TESTNET_PRIVATE_KEY", raising=False)
    spec.loader.exec_module(module)
    module.work = tmp_path
    # Public, deterministic test key. Never connected to an external service.
    module.auditor = Account.from_key("0x" + "01" * 32)
    module.durable_json(tmp_path / "transaction-journal-v1.json", {"version": 1})
    return module


@pytest.fixture
def sealed(driver):
    trace_hash, root = bytes.fromhex("12" * 32), bytes.fromhex("34" * 32)
    data = (
        driver.PUBLISH_V2
        + encode(
            ["address", "bytes32", "uint32", "uint32", "bytes32", "bytes32", "bytes16", "string"],
            ["0x" + "00" * 20, bytes(32), 5000, 9000, trace_hash, root, bytes(16), "test-cid"],
        ).hex()
    )
    return {
        "audit_id": 7,
        "status": "sealed",
        "trace_hash": "0x" + trace_hash.hex(),
        "merkle_root": "0x" + root.hex(),
        "trace_cid": "test-cid",
        "transaction": {"to": driver.REGISTRY, "chain_id": driver.CHAIN_ID, "value": "0", "data": data},
    }


class FakeRpc:
    def __init__(self):
        self.calls = []
        self.known = False
        self.lose_broadcast_response = False

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == "eth_getTransactionByHash":
            return {"result": {"hash": params[0]} if self.known else None}
        if method == "eth_sendRawTransaction":
            if self.lose_broadcast_response:
                raise TimeoutError("response lost after broadcast")
            return {"result": "0x" + keccak(bytes.fromhex(params[0][2:])).hex()}
        if method == "eth_chainId":
            return {"result": hex(5042002)}
        return {
            "result": {
                "eth_call": "0x",
                "eth_estimateGas": "0x10000",
                "eth_gasPrice": "0x2",
                "eth_getTransactionCount": "0x9",
            }[method]
        }


def test_broadcast_response_lost_resumes_identical_bytes(driver, sealed):
    rpc = FakeRpc()
    driver.rpc = rpc
    rpc.lose_broadcast_response = True
    with pytest.raises(TimeoutError):
        driver.publish(sealed)
    saved = json.loads(next(driver.work.glob("publish-*.json")).read_text())
    rpc.lose_broadcast_response = False
    assert driver.publish(sealed) == saved["transaction_hash"]
    broadcasts = [params[0] for method, params in rpc.calls if method == "eth_sendRawTransaction"]
    assert broadcasts == [saved["raw_transaction"], saved["raw_transaction"]]
    assert sum(method == "eth_getTransactionCount" for method, _ in rpc.calls) == 1


def test_confirmation_timeout_resumes_known_transaction_without_signing(driver, sealed):
    rpc = FakeRpc()
    driver.rpc = rpc
    original = driver.publish(sealed)
    # Confirmation timed out, but the transaction remains pending or mined.
    rpc.known = True
    rpc.calls.clear()
    assert driver.publish(sealed) == original
    assert rpc.calls == [("eth_getTransactionByHash", [original])]


def test_journal_is_durable_before_any_broadcast(driver, sealed):
    rpc = FakeRpc()

    def check(method, params):
        if method == "eth_sendRawTransaction":
            journal = next(driver.work.glob("publish-*.json"))
            assert journal.stat().st_mode & 0o777 == 0o600
            saved = json.loads(journal.read_text())
            assert saved["raw_transaction"] == params[0]
        return rpc(method, params)

    driver.rpc = check
    driver.publish(sealed)


def test_persist_failure_never_broadcasts(driver, sealed, monkeypatch):
    rpc = FakeRpc()
    driver.rpc = rpc

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(driver, "durable_json", fail)
    with pytest.raises(OSError, match="disk full"):
        driver.publish(sealed)
    assert not any(method == "eth_sendRawTransaction" for method, _ in rpc.calls)


def test_legacy_work_directory_requires_manual_recovery(driver, sealed):
    (driver.work / "transaction-journal-v1.json").unlink()
    rpc = FakeRpc()
    driver.rpc = rpc
    with pytest.raises(RuntimeError, match="Legacy work directory"):
        driver.publish(sealed)
    assert rpc.calls == []


def test_saved_transaction_rejects_changed_auditor(driver, sealed):
    rpc = FakeRpc()
    driver.rpc = rpc
    driver.publish(sealed)
    rpc.calls.clear()
    driver.auditor = Account.from_key("0x" + "02" * 32)
    with pytest.raises(RuntimeError, match="differs from the seal/deployment"):
        driver.publish(sealed)
    assert rpc.calls == []


def test_saved_hash_corruption_fails_closed(driver, sealed):
    rpc = FakeRpc()
    driver.rpc = rpc
    driver.publish(sealed)
    journal = next(driver.work.glob("publish-*.json"))
    saved = json.loads(journal.read_text())
    saved["transaction_hash"] = "0x" + "00" * 32
    journal.write_text(json.dumps(saved))
    rpc.calls.clear()
    with pytest.raises(RuntimeError, match="Invalid saved transaction"):
        driver.publish(sealed)
    assert rpc.calls == []


def test_interruption_after_journaling_before_broadcast_is_recoverable(driver, sealed):
    rpc = FakeRpc()
    driver.rpc = rpc
    original_broadcast = driver.broadcast_saved
    driver.broadcast_saved = lambda *args: (_ for _ in ()).throw(KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        driver.publish(sealed)
    driver.broadcast_saved = original_broadcast
    saved = json.loads(next(driver.work.glob("publish-*.json")).read_text())
    assert driver.publish(sealed) == saved["transaction_hash"]
    assert sum(method == "eth_getTransactionCount" for method, _ in rpc.calls) == 1


def test_main_confirmation_timeout_then_resume_does_not_republish(driver, sealed, monkeypatch):
    class Reply:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    class Api:
        finalized = False

        def get(self, path, **kwargs):
            return Reply(sealed if path == "/v1/audits/next" else {"verified": True})

        def post(self, path, **kwargs):
            assert path == "/v1/audits/7/published"
            return Reply(
                {"status": "published", "receipt_id": 42} if self.finalized else {"status": "pending"}
            )

    driver.configure_runtime = lambda: None
    driver.init_db = lambda: None
    driver.AUTH = {}
    driver.api = Api()
    driver.rpc = FakeRpc()
    monkeypatch.setattr(driver.time, "sleep", lambda _: None)
    with pytest.raises(SystemExit, match="not finalized in 10 minutes"):
        asyncio.run(driver.main())
    driver.rpc.known = True
    driver.api.finalized = True
    asyncio.run(driver.main())
    assert sum(method == "eth_sendRawTransaction" for method, _ in driver.rpc.calls) == 1
    assert sum(method == "eth_getTransactionCount" for method, _ in driver.rpc.calls) == 1


@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize(
    "changed",
    [
        {"to": "0x" + "ab" * 20},
        {"chainId": 1},
        {"value": 1},
        {"data": "0x12345678"},
    ],
)
def test_same_signer_transaction_swap_is_rejected(driver, sealed, typed, changed):
    rpc = FakeRpc()
    driver.rpc = rpc
    driver.publish(sealed)
    journal = next(driver.work.glob("publish-*.json"))
    saved = json.loads(journal.read_text())
    tx = {
        "to": driver.to_checksum_address(driver.REGISTRY),
        "chainId": driver.CHAIN_ID,
        "value": 0,
        "data": sealed["transaction"]["data"],
        "nonce": 9,
        "gas": 100000,
        **changed,
    }
    tx["to"] = driver.to_checksum_address(tx["to"])
    tx.update({"type": 2, "maxFeePerGas": 2, "maxPriorityFeePerGas": 1} if typed else {"gasPrice": 2})
    different = driver.auditor.sign_transaction(tx)
    saved["raw_transaction"] = "0x" + different.raw_transaction.hex()
    saved["transaction_hash"] = "0x" + keccak(different.raw_transaction).hex()
    journal.write_text(json.dumps(saved))
    rpc.calls.clear()
    with pytest.raises(RuntimeError, match="Invalid saved transaction"):
        driver.publish(sealed)
    assert rpc.calls == []


@pytest.mark.parametrize("transaction_type", [1, 2])
def test_valid_typed_saved_transaction_can_resume(driver, sealed, transaction_type):
    driver.rpc = FakeRpc()
    driver.publish(sealed)
    journal = next(driver.work.glob("publish-*.json"))
    saved = json.loads(journal.read_text())
    tx = {
        "to": driver.to_checksum_address(driver.REGISTRY),
        "chainId": driver.CHAIN_ID,
        "value": 0,
        "data": sealed["transaction"]["data"],
        "nonce": 9,
        "gas": 100000,
        "type": transaction_type,
        "accessList": [],
    }
    tx.update({"maxFeePerGas": 2, "maxPriorityFeePerGas": 1} if transaction_type == 2 else {"gasPrice": 2})
    signed = driver.auditor.sign_transaction(tx)
    saved["raw_transaction"] = "0x" + signed.raw_transaction.hex()
    saved["transaction_hash"] = "0x" + keccak(signed.raw_transaction).hex()
    journal.write_text(json.dumps(saved))
    driver.rpc.known = True
    driver.rpc.calls.clear()
    assert driver.publish(sealed) == saved["transaction_hash"]
    assert driver.rpc.calls == [("eth_getTransactionByHash", [saved["transaction_hash"]])]
