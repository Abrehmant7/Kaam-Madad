"""Synthetic test audio. Generated in code: no real voices or personal data in the repository."""

import io
import math
import struct
import wave


def make_wav(seconds: float, rate: int = 16000) -> bytes:
    frames = bytearray()
    for i in range(int(rate * seconds)):
        frames += struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / rate)))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()
