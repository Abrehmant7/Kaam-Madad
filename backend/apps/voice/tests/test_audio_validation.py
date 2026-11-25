from django.test import SimpleTestCase

from apps.voice.audio import (
    AudioInvalid,
    AudioTooLarge,
    AudioTooLong,
    AudioTooShort,
    AudioUnsupported,
    inspect_audio,
    sniff_format,
)

from .helpers import make_wav


class InspectAudioTests(SimpleTestCase):
    def test_accepts_wav_and_measures_duration(self):
        info = inspect_audio(make_wav(2.5))
        self.assertEqual(info.format.kind, "wav")
        self.assertEqual(info.format.provider_mime_type, "audio/wav")
        self.assertAlmostEqual(info.duration_seconds, 2.5, places=2)
        self.assertEqual(len(info.sha256), 64)

    def test_accepts_exactly_sixty_seconds(self):
        self.assertAlmostEqual(inspect_audio(make_wav(60, rate=8000)).duration_seconds, 60.0, places=1)

    def test_rejects_longer_than_sixty_seconds(self):
        with self.assertRaises(AudioTooLong) as ctx:
            inspect_audio(make_wav(61, rate=8000))
        self.assertEqual(ctx.exception.details["max_seconds"], 60)

    def test_rejects_too_short(self):
        with self.assertRaises(AudioTooShort):
            inspect_audio(make_wav(0.1))

    def test_rejects_over_ten_megabytes(self):
        with self.assertRaises(AudioTooLarge):
            inspect_audio(b"RIFF" + b"\0" * (10 * 1024 * 1024))

    def test_rejects_non_audio_regardless_of_name(self):
        for data in (b"hello, this is text pretending to be a wav", b"%PDF-1.7 ...", b"\x89PNG\r\n\x1a\n...."):
            with self.subTest(data=data[:8]):
                with self.assertRaises(AudioUnsupported):
                    inspect_audio(data)

    def test_rejects_webm(self):
        with self.assertRaises(AudioUnsupported):
            inspect_audio(b"\x1a\x45\xdf\xa3" + b"\0" * 100)

    def test_rejects_corrupt_files_with_valid_headers(self):
        for data in (b"RIFF\x24\x00\x00\x00WAVEjunkjunkjunk", b"ID3\x03\x00\x00\x00\x00\x00\x00garbage" * 3, b"fLaC" + b"\0" * 40):
            with self.subTest(data=data[:4]):
                with self.assertRaises((AudioInvalid, AudioUnsupported)):
                    inspect_audio(data)

    def test_sniffing(self):
        self.assertEqual(sniff_format(b"OggS\0\0"), "ogg")
        self.assertEqual(sniff_format(b"\0\0\0\x20ftypM4A "), "m4a")
        self.assertEqual(sniff_format(b"\xff\xfb\x90\x00"), "mp3")
        self.assertEqual(sniff_format(b"\xff\xf1\x50\x80"), "aac")
        self.assertIsNone(sniff_format(b"plain text"))
