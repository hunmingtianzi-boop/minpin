import { describe, expect, it } from "vitest";

import { encodeQrMatrix, qrPathData } from "./qrCode";

describe("local QR encoder", () => {
  it("creates a deterministic version 10 matrix with finder patterns", () => {
    const first = encodeQrMatrix("https://example.test/c/example-company");
    const second = encodeQrMatrix("https://example.test/c/example-company");

    expect(first).toEqual(second);
    expect(first).toHaveLength(57);
    expect(first.every((row) => row.length === 57)).toBe(true);
    expect(first[0].slice(0, 7)).toEqual([true, true, true, true, true, true, true]);
    expect(first[1].slice(0, 7)).toEqual([true, false, false, false, false, false, true]);
    expect(first[3].slice(0, 7)).toEqual([true, false, true, true, true, false, true]);
    expect(qrPathData(first)).toContain("M4,4h1v1h-1z");

    const flattened = first
      .map((row) => row.map((value) => (value ? "1" : "0")).join(""))
      .join("");
    let referenceHash = 2166136261;
    for (const character of flattened) {
      referenceHash ^= character.charCodeAt(0);
      referenceHash = Math.imul(referenceHash, 16777619);
    }
    // Cross-checked against an independent standards-compliant QR encoder
    // using version 10, error correction L, no border and automatic masking.
    expect((referenceHash >>> 0).toString(16)).toBe("b0474c43");
  });

  it("fails closed when a share URL exceeds the local QR capacity", () => {
    expect(() => encodeQrMatrix(`https://example.test/${"x".repeat(280)}`)).toThrow(
      "分享链接过长",
    );
  });
});
