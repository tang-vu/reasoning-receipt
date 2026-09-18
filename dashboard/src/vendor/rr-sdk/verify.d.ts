/** Unified verification entry point — dispatch strictly on `schema_version`.
 * Mirrors `protocol/verify.py` + `protocol/legacy.py`. */
import type { JsonValue } from "./canon.js";
import type { VerifyReport } from "./receipt.js";
export declare const KNOWN_SCHEMAS: string[];
export declare function legacyTraceHash(document: Record<string, JsonValue>): string;
export declare function verifyTraceBlob(document: Record<string, JsonValue>, expectedHash?: string): VerifyReport;
export declare function verifyTrace3(document: Record<string, JsonValue>): VerifyReport;
export declare function verifyReceiptDraft(document: Record<string, JsonValue>): VerifyReport;
export declare function verifyAny(document: unknown, expectedHash?: string): VerifyReport;
export declare function supportedSchemas(): Record<string, JsonValue>[];
