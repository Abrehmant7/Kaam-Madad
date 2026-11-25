import { describe, expect, it } from "vitest";

import { concatenate, downsample, encodeWav } from "./wav";

describe("wav helpers", () => {
  it("encodes 16 kHz mono 16-bit PCM with a correct header", async () => {
    const blob = encodeWav(new Float32Array(16_000).fill(0.5));
    const bytes = new DataView(await blob.arrayBuffer());
    const text = (offset: number) => String.fromCharCode(...[0, 1, 2, 3].map((i) => bytes.getUint8(offset + i)));
    expect(blob.type).toBe("audio/wav");
    expect(text(0)).toBe("RIFF");
    expect(text(8)).toBe("WAVE");
    expect(bytes.getUint16(22, true)).toBe(1); // mono
    expect(bytes.getUint32(24, true)).toBe(16_000);
    expect(bytes.getUint16(34, true)).toBe(16);
    expect(bytes.getUint32(40, true)).toBe(32_000); // 1 s of 2-byte samples
    expect(blob.size).toBe(44 + 32_000);
  });

  it("downsamples 48 kHz to 16 kHz and concatenates chunks", () => {
    const joined = concatenate([new Float32Array(24_000), new Float32Array(24_000)]);
    expect(joined.length).toBe(48_000);
    expect(downsample(joined, 48_000).length).toBe(16_000);
    expect(downsample(joined, 16_000)).toBe(joined);
  });
});
