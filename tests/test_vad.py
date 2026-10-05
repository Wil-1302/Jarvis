from __future__ import annotations

import numpy as np
import pytest

from app.voice.vad import SegmentKind, SileroVAD, SpeechSegmenter, VadState
from tests.voice_fakes import FakeVAD, tone

CHUNK = 1280


def feed_all(segmenter: SpeechSegmenter, audio: np.ndarray) -> list:
    audio = np.concatenate([audio, np.zeros(-audio.size % CHUNK, dtype=np.int16)])
    events = []
    for chunk in audio.reshape(-1, CHUNK):
        event = segmenter.feed(chunk)
        if event is not None:
            events.append(event)
    return events


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(16000 * seconds), dtype=np.int16)


def test_silence_voice_silence() -> None:
    segmenter = SpeechSegmenter(FakeVAD(), min_silence_ms=500, speech_pad_ms=200)
    events = feed_all(segmenter, np.concatenate([silence(1), tone(1000, 1.0), silence(1)]))
    assert [e.kind for e in events] == [SegmentKind.SPEECH_START, SegmentKind.SPEECH_END]
    end = events[-1]
    # 1 s de voz + pre-roll (~200 ms) + silencio final (~500 ms)
    assert 1.5 <= end.duration <= 2.0
    assert segmenter.state is VadState.SILENCE


def test_short_noises_are_discarded() -> None:
    segmenter = SpeechSegmenter(FakeVAD(), min_silence_ms=300, min_speech_ms=250)
    events = feed_all(segmenter, np.concatenate([silence(0.5), tone(1000, 0.08), silence(1)]))
    assert [e.kind for e in events] == [SegmentKind.SPEECH_START]


def test_timeout_when_nobody_speaks() -> None:
    segmenter = SpeechSegmenter(FakeVAD(), start_timeout_s=1.0)
    events = feed_all(segmenter, silence(2))
    assert events[0].kind is SegmentKind.TIMEOUT


def test_arm_timeout_resets_wait_counter() -> None:
    segmenter = SpeechSegmenter(FakeVAD())
    feed_all(segmenter, silence(5))
    segmenter.arm_timeout(1.0)
    assert feed_all(segmenter, silence(0.5)) == []
    assert feed_all(segmenter, silence(0.7))[0].kind is SegmentKind.TIMEOUT


def test_max_utterance_cuts_long_speech() -> None:
    segmenter = SpeechSegmenter(FakeVAD(), max_utterance_s=2.0)
    events = feed_all(segmenter, tone(1000, 5.0))
    ends = [e for e in events if e.kind is SegmentKind.SPEECH_END]
    assert ends and ends[0].duration <= 2.2


def test_silero_vad_is_quiet_on_silence() -> None:
    vad = SileroVAD()
    probs = vad.process(np.zeros(16000, dtype=np.int16))
    assert len(probs) == 31  # 16000 // 512
    assert max(probs) < 0.2


def test_silero_vad_buffers_partial_frames() -> None:
    vad = SileroVAD()
    assert len(vad.process(np.zeros(1280, dtype=np.int16))) == 2
    assert len(vad.process(np.zeros(1280, dtype=np.int16))) == 3  # 2560 // 512 = 5 en total


@pytest.mark.integration
def test_silero_vad_detects_real_speech(spanish_speech) -> None:
    segmenter = SpeechSegmenter(SileroVAD())
    events = feed_all(segmenter, np.concatenate([silence(1), spanish_speech, silence(1.5)]))
    kinds = [e.kind for e in events]
    assert SegmentKind.SPEECH_START in kinds
    assert SegmentKind.SPEECH_END in kinds
