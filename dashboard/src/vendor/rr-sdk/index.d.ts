/** @reasoning-receipt/sdk — portable, byte-verifiable evidence receipts
 * for AI decisions and actions (reasoning-receipt/1). */
export { canonicalBytes, canonicalString, parseJsonObject, CANONICALIZATION_ID } from "./canon.js";
export type { JsonValue } from "./canon.js";
export { legacyCanonicalBytes, LEGACY_CANONICALIZATION_ID } from "./legacy_canon.js";
export { sha256Hex, digestBytes, merkleRoot, merkleProof, verifyMerkleProof, } from "./merkle.js";
export { bytesToHex, hexToBytes, bytesEqual } from "./hex.js";
export { SCHEMA_VERSION, CANONICALIZATION, ReceiptNode, ReceiptEdge, PortableReceipt, ReceiptBuilder, KeyError, IndexError, nodeLeaf, edgeLeaf, merkleRootOf, receiptHashOf, validTimestamp, bytes32Hex, restoreReceipt, verifyReceipt, verifyProofDocument, verifyReceiptProof, loadReceipt, loadReceiptFile, } from "./receipt.js";
export type { NodeDict, EdgeDict, ProofDocument, VerifyReport } from "./receipt.js";
export { ALG_ED25519, generateKeypair, sign, verifySignatures, } from "./signatures.js";
export type { SignatureObject, SignatureResult } from "./signatures.js";
export { KNOWN_SCHEMAS, verifyAny, verifyTraceBlob, verifyTrace3, verifyReceiptDraft, legacyTraceHash, supportedSchemas, } from "./verify.js";
export { ReceiptError, CanonError, ShapeError, GraphError, SchemaError, SignatureError, } from "./errors.js";
