"""Pipeline de voz: micrófono -> wake word -> VAD -> Whisper -> Ollama -> Piper -> altavoces.

Todo corre en un único hilo de procesado; el callback de PortAudio solo encola audio.

Flujo de un turno:

1. IDLE: cada bloque de 80 ms pasa por openWakeWord y por el segmentador VAD.
   - Si openWakeWord detecta "Jarvis" -> WAKE_DETECTED -> LISTENING (se sigue grabando
     la frase en curso, así "Jarvis, ¿cómo estás?" llega entera).
   - En modo híbrido/transcripción, al terminar cada frase se transcribe y se busca
     el nombre en las primeras palabras.
2. Si solo se dijo el nombre, JARVIS responde "¿Sí?" y escucha la orden (LISTENING).
3. TRANSCRIBING -> THINKING (Ollama, en streaming) -> SPEAKING (Piper, frase a frase).
4. Anti-eco: el micrófono se silencia mientras JARVIS habla; después se descarta el
   audio acumulado, se espera ``echo_cooldown_ms`` y se reinician wake word y VAD.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from app.brain.ollama_client import OllamaError
from app.core.logging import get_logger
from app.voice.state import StateMachine, VoiceState
from app.voice.vad import SegmentKind, SpeechSegmenter
from app.voice.wakeword import DEFAULT_ALIASES, WakeEvent, match_wake_word

log = get_logger("voice.pipeline")

ACK_TEXT = "¿Sí?"
ERROR_TEXT = "Lo siento, ahora mismo no puedo pensar. Revisa que Ollama esté abierto."
IDLE_MIN_SEGMENT_S = 0.3
IDLE_MAX_SEGMENT_S = 10.0


# --- Interfaces mínimas (permiten tests sin hardware) -------------------------
class AudioSource(Protocol):
    def read(self, timeout: float | None = None) -> np.ndarray | None: ...
    def mute(self) -> None: ...
    def unmute(self) -> None: ...
    def clear(self) -> int: ...


class Player(Protocol):
    def play(self, audio: np.ndarray, samplerate: int, blocking: bool = True) -> None: ...
    def wait(self) -> None: ...


class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> Any: ...  # -> Transcript


class Synthesizer(Protocol):
    def synthesize_sentences(self, text: str) -> Iterator[Any]: ...  # -> SpeechAudio


class Brain(Protocol):
    def reply_sentences(self, text: str) -> Iterator[str]: ...


class AcousticWake(Protocol):
    def process(self, chunk: np.ndarray) -> WakeEvent | None: ...
    def reset(self) -> None: ...


# --- Métricas ----------------------------------------------------------------
@dataclass
class TurnMetrics:
    wake_source: str = ""
    speech_seconds: float = 0.0
    stt_seconds: float = 0.0
    llm_first_sentence: float = 0.0
    llm_total: float = 0.0
    tts_first_sentence: float = 0.0
    first_audio_after_speech: float = 0.0  # fin de la frase (VAD) -> empieza a sonar
    speaking_seconds: float = 0.0
    total: float = 0.0
    transcript: str = ""
    reply: str = ""

    def summary(self) -> str:
        return (
            f"voz {self.speech_seconds:.2f}s | STT {self.stt_seconds:.2f}s | "
            f"LLM 1ª frase {self.llm_first_sentence:.2f}s (total {self.llm_total:.2f}s) | "
            f"TTS 1ª frase {self.tts_first_sentence:.2f}s | "
            f"primer audio {self.first_audio_after_speech:.2f}s tras terminar de hablar"
        )


@dataclass
class PipelineEvent:
    kind: str  # state | wake | transcript | ignored | reply | metrics | error
    data: dict[str, Any] = field(default_factory=dict)


class VoicePipeline:
    def __init__(
        self,
        source: AudioSource,
        segmenter: SpeechSegmenter,
        stt: Transcriber,
        brain: Brain,
        tts: Synthesizer,
        player: Player,
        wake: AcousticWake | None = None,
        engine: str = "hybrid",
        aliases: Iterable[str] = DEFAULT_ALIASES,
        listen_timeout_s: float = 6.0,
        echo_cooldown_ms: int = 400,
        on_event: Callable[[PipelineEvent], None] | None = None,
    ) -> None:
        if engine in ("hybrid", "acoustic") and wake is None:
            raise ValueError(f"el modo '{engine}' necesita el detector acústico")
        self.source = source
        self.segmenter = segmenter
        self.stt = stt
        self.brain = brain
        self.tts = tts
        self.player = player
        self.wake = wake
        self.engine = engine
        self.aliases = tuple(aliases)
        self.listen_timeout_s = listen_timeout_s
        self.echo_cooldown_s = echo_cooldown_ms / 1000
        self.on_event = on_event or (lambda event: None)
        self.state = StateMachine()
        self.state.add_listener(
            lambda t: self._emit("state", previous=t.previous.value, current=t.current.value)
        )
        self.turns: list[TurnMetrics] = []
        self._metrics = TurnMetrics()
        self._ack_audio: list[Any] | None = None
        self.devices: tuple[Any, Any] | None = None  # (micrófono, altavoces), informativo

    # --- utilidades ------------------------------------------------------------
    def _emit(self, kind: str, **data: Any) -> None:
        self.on_event(PipelineEvent(kind, data))

    def _go(self, target: VoiceState, reason: str = "") -> None:
        if self.state.state is not target:
            self.state.transition(target, reason)

    def _listen_for_command(self) -> None:
        self.segmenter.reset(start_timeout_s=self.listen_timeout_s)
        self._go(VoiceState.LISTENING, "esperando la orden")

    def _back_to_idle(self, reason: str) -> None:
        self.state.reset(reason)
        self.segmenter.reset(start_timeout_s=None)
        if self.wake is not None:
            self.wake.reset()

    # --- bucle principal -------------------------------------------------------
    def run(self, stop: threading.Event | None = None, max_turns: int | None = None) -> None:
        stop = stop or threading.Event()
        self._back_to_idle("inicio")
        while not stop.is_set():
            chunk = self.source.read(timeout=0.2)
            if chunk is None:
                continue
            self.process_chunk(chunk)
            if max_turns is not None and len(self.turns) >= max_turns:
                break

    def process_chunk(self, chunk: np.ndarray) -> None:
        state = self.state.state
        if state is VoiceState.IDLE:
            self._process_idle(chunk)
        elif state is VoiceState.LISTENING:
            self._process_listening(chunk)

    def _process_idle(self, chunk: np.ndarray) -> None:
        if self.wake is not None and self.engine in ("hybrid", "acoustic"):
            event = self.wake.process(chunk)
            if event is not None:
                self._metrics = TurnMetrics(wake_source="acoustic")
                self._emit("wake", source="acoustic", score=event.score)
                self._go(VoiceState.WAKE_DETECTED, "openWakeWord")
                # No se reinicia el segmentador: la frase en curso puede traer la orden.
                self.segmenter.arm_timeout(self.listen_timeout_s)
                self._go(VoiceState.LISTENING, "capturando la orden")
                self.segmenter.feed(chunk)
                return

        segment = self.segmenter.feed(chunk)
        if self.engine == "acoustic" or segment is None:
            return
        if segment.kind is SegmentKind.SPEECH_END and (
            IDLE_MIN_SEGMENT_S <= segment.duration <= IDLE_MAX_SEGMENT_S
        ):
            self._metrics = TurnMetrics(wake_source="transcript")
            self._handle_utterance(segment.audio, awake=False)

    def _process_listening(self, chunk: np.ndarray) -> None:
        segment = self.segmenter.feed(chunk)
        if segment is None or segment.kind is SegmentKind.SPEECH_START:
            return
        if segment.kind is SegmentKind.TIMEOUT:
            self._emit("ignored", reason="no se detectó voz tras la wake word")
            self._back_to_idle("tiempo de espera agotado")
            return
        self._handle_utterance(segment.audio, awake=True)

    # --- un turno ---------------------------------------------------------------
    def _handle_utterance(self, audio: np.ndarray, awake: bool) -> None:
        speech_end = time.perf_counter()
        self._metrics.speech_seconds = audio.size / 16000
        self._go(VoiceState.TRANSCRIBING, "fin de la frase")
        transcript = self.stt.transcribe(audio)
        self._metrics.stt_seconds = transcript.elapsed

        if transcript.is_empty:
            self._emit("ignored", reason="no se entendió nada", text=transcript.text)
            self._back_to_idle("transcripción vacía")
            return

        found, remainder = match_wake_word(transcript.text, self.aliases)
        if not awake and not found:
            self._emit("ignored", reason="sin wake word", text=transcript.text)
            self._back_to_idle("frase sin 'Jarvis'")
            return
        if found and not awake:
            self._emit("wake", source="transcript", text=transcript.text)
        command = remainder if found else transcript.text
        self._emit("transcript", text=transcript.text, command=command)

        if not command:
            self._go(VoiceState.WAKE_DETECTED, "solo el nombre")
            self._speak_ack()
            self._listen_for_command()
            return

        self._metrics.transcript = command
        self._go(VoiceState.THINKING, "orden recibida")
        self._respond(command, speech_end)

    def _respond(self, command: str, speech_end: float) -> None:
        metrics = self._metrics
        llm_start = time.perf_counter()
        sentences = self.brain.reply_sentences(command)
        spoken: list[str] = []
        first_audio_at: float | None = None
        try:
            self.source.mute()
            for index, sentence in enumerate(sentences):
                if index == 0:
                    metrics.llm_first_sentence = time.perf_counter() - llm_start
                spoken.append(sentence)
                for i, part in enumerate(self.tts.synthesize_sentences(sentence)):
                    if index == 0 and i == 0:
                        metrics.tts_first_sentence = part.synth_seconds
                    self.player.wait()  # termina la frase anterior mientras se sintetizaba esta
                    if first_audio_at is None:
                        self._go(VoiceState.SPEAKING, "respuesta lista")
                        first_audio_at = time.perf_counter()
                    self.player.play(part.audio, part.sample_rate, blocking=False)
            metrics.llm_total = time.perf_counter() - llm_start
        except OllamaError as exc:
            log.error("Error del cerebro: %s", exc)
            self._emit("error", message=str(exc))
            if first_audio_at is None:
                self._go(VoiceState.SPEAKING, "error")
                first_audio_at = time.perf_counter()
            for part in self.tts.synthesize_sentences(ERROR_TEXT):
                self.player.wait()
                self.player.play(part.audio, part.sample_rate, blocking=False)
        finally:
            self.player.wait()
            self._end_speaking()

        metrics.reply = " ".join(spoken)
        if first_audio_at is not None:
            metrics.first_audio_after_speech = first_audio_at - speech_end
            metrics.speaking_seconds = time.perf_counter() - first_audio_at
        metrics.total = time.perf_counter() - speech_end
        self.turns.append(metrics)
        self._emit("reply", text=metrics.reply)
        self._emit("metrics", summary=metrics.summary(), metrics=metrics)
        log.info("Turno: %s", metrics.summary())
        self._back_to_idle("respuesta terminada")

    def _speak_ack(self) -> None:
        if self._ack_audio is None:
            self._ack_audio = list(self.tts.synthesize_sentences(ACK_TEXT))
        self._go(VoiceState.SPEAKING, "confirmación")
        self.source.mute()
        try:
            for part in self._ack_audio:
                self.player.play(part.audio, part.sample_rate, blocking=True)
        finally:
            self._end_speaking()

    def _end_speaking(self) -> None:
        """Anti-eco: espera, descarta lo grabado mientras hablaba y reinicia detectores."""
        time.sleep(self.echo_cooldown_s)
        self.source.clear()
        self.source.unmute()
        if self.wake is not None:
            self.wake.reset()


def build_pipeline(settings, on_event: Callable[[PipelineEvent], None] | None = None):
    """Crea el pipeline real (micrófono, modelos y Ollama) a partir de la configuración."""
    from app.audio.device_manager import find_device
    from app.audio.stream import AudioPlayer, MicrophoneStream
    from app.brain.conversation import ConversationBrain
    from app.brain.ollama_client import OllamaClient
    from app.voice.stt import SpeechToText
    from app.voice.tts import TextToSpeech
    from app.voice.vad import SileroVAD
    from app.voice.wakeword import WakeWordDetector

    mic_device = find_device("input", settings.audio_input_device, settings.audio_host_api)
    out_device = find_device("output", settings.audio_output_device, settings.audio_host_api)
    models = settings.models_path

    wake = None
    if settings.wake_engine in ("hybrid", "acoustic"):
        wake = WakeWordDetector(
            models,
            settings.wake_model,
            settings.wake_threshold,
            settings.wake_patience,
            word=settings.wake_word,
        )
    segmenter = SpeechSegmenter(
        SileroVAD(),
        threshold=settings.vad_threshold,
        min_silence_ms=settings.vad_min_silence_ms,
        speech_pad_ms=settings.vad_speech_pad_ms,
        max_utterance_s=settings.max_utterance_s,
    )
    stt = SpeechToText(
        models,
        settings.stt_model,
        settings.stt_device,
        settings.stt_compute_type,
        settings.language,
        settings.stt_beam_size,
        settings.stt_prompt,
    )
    tts = TextToSpeech(models, settings.tts_voice, settings.tts_length_scale)
    ollama = OllamaClient(settings.ollama_host, timeout=max(settings.ollama_timeout, 60))
    brain = ConversationBrain(
        ollama,
        settings.ollama_model,
        name=settings.name,
        max_words=settings.voice_max_reply_words,
        keep_alive=settings.ollama_keep_alive,
    )

    # Precalentamiento: la primera respuesta no paga la carga de modelos.
    stt.warmup()
    tts.warmup()
    try:
        brain.warmup()
    except OllamaError as exc:
        log.warning("No se pudo precargar el modelo de Ollama: %s", exc)

    pipeline = VoicePipeline(
        source=MicrophoneStream(mic_device),
        segmenter=segmenter,
        stt=stt,
        brain=brain,
        tts=tts,
        player=AudioPlayer(out_device),
        wake=wake,
        engine=settings.wake_engine,
        aliases=tuple(settings.wake_aliases),
        listen_timeout_s=settings.listen_timeout_s,
        echo_cooldown_ms=settings.echo_cooldown_ms,
        on_event=on_event,
    )
    pipeline.devices = (mic_device, out_device)
    return pipeline
