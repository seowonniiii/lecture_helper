"""Offline tests for local WhisperKit exports. No cloud credentials required."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcript_import import parse_local_transcript


class LocalTranscriptImportTests(unittest.TestCase):
    def parse(self, extension, content):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / ("lecture" + extension)
            f.write_text(content, encoding="utf-8")
            return parse_local_transcript(f)

    def test_whisperkit_json_preserves_spoken_words_and_timing(self):
        obj = {
            "title": "생리학",
            "model": "large-v3-v20240930_626MB", "language": "ko",
            "spokenLanguage": "ko", "duration": 145.2,
            "segments": [
                {"start": 0.25, "end": 8.8, "text": "insulin",
                 "original": "인슐린", "speaker": "교수"},
                {"start": 9.01, "end": 19.3, "text": "ACTH",
                 "original": None, "speaker": None}
            ],
        }
        out = self.parse(".json", json.dumps(obj, ensure_ascii=False))
        self.assertEqual(len(out["segments"]), 2)
        self.assertEqual(out["segments"][0]["text"], "교수: 인슐린")
        self.assertEqual(out["segments"][0]["start"], 0.25)
        self.assertEqual(out["segments"][1]["text"], "ACTH")
        self.assertEqual(out["duration"], 145.2)
        self.assertEqual(out["language"], "ko")

    def test_srt_timestamps(self):
        srt = "1\n00:00:01,200 --> 00:00:06,400\n안녕, 갑상선.\n\n2\n00:00:07,300 --> 00:00:10,600\nACTH 발음\n"
        out = self.parse(".srt", srt)
        self.assertEqual([x["start"] for x in out["segments"]], [1.2, 7.3])
        self.assertEqual(out["segments"][1]["end"], 10.6)

    def test_vtt_speaker(self):
        out = self.parse(".vtt", "WEBVTT\n\n00:01:00.000 --> 00:01:03.800\n<v 교수>쿠싱\n")
        self.assertEqual(out["segments"][0]["text"], "교수: 쿠싱")
        self.assertEqual(out["segments"][0]["start"], 60.0)

    def test_txt_keeps_all_nonempty_lines(self):
        out = self.parse(".txt", "첫째 문장.\n\n둘째 문장.\n")
        self.assertEqual([s["text"] for s in out["segments"]], ["첫째 문장.", "둘째 문장."])
        self.assertIsNone(out["duration"])

    def test_invalid_json_fails_closed(self):
        with self.assertRaises(ValueError):
            self.parse(".json", '{"text":"hello"}')


if __name__ == "__main__":
    unittest.main()
