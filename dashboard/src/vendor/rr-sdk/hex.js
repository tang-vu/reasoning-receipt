// Isomorphic hex helpers — no Node Buffer, works in every runtime.
export function bytesToHex(bytes) {
    let out = "";
    for (const b of bytes)
        out += b.toString(16).padStart(2, "0");
    return out;
}
export function hexToBytes(hex) {
    const raw = hex.startsWith("0x") ? hex.slice(2) : hex;
    const out = new Uint8Array(raw.length / 2);
    for (let i = 0; i < out.length; i++) {
        out[i] = parseInt(raw.slice(i * 2, i * 2 + 2), 16);
    }
    return out;
}
export function bytesEqual(a, b) {
    if (a.length !== b.length)
        return false;
    let diff = 0;
    for (let i = 0; i < a.length; i++)
        diff |= a[i] ^ b[i];
    return diff === 0;
}
