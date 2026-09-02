"""Turning speech into text, on the gateway, with a swappable engine.

Two decisions are baked in here.

**It happens on the gateway, not the glasses.** The headset should spend
its battery on the display and the microphone. Loading a speech model
onto it would cost power, memory and a deployment story, for no gain: the
gateway is already the thing that knows about tasks and agents.

**No engine ships by default.** A speech model is hundreds of megabytes,
and nobody should have that arrive because they cloned a repository. So
the gateway has an interface with a plug in it, and the whole audio path
— capture, upload, review, drafts, sending — works the same whichever
engine is behind it. With none configured, Audio simply reports itself
unavailable, which the display already knows how to show.

What never happens: the audio going anywhere else. There is no cloud
transcription option here and no place to add one without it being
obvious. The recording is held only as long as it takes to turn into
text, and then it is gone — there is deliberately nowhere to write it.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# The longest recording the gateway will take. About a minute of speech
# at the headset's sample rate, which is far more than anyone dictates
# into a pair of glasses in one go.
MAX_AUDIO_BYTES = 6 * 1024 * 1024

# The longest transcript it will hand back. Matches the cap the glasses
# put on a message before sending it.
MAX_TEXT = 2000


@dataclass(frozen=True)
class Transcript:
    """What came of one recording.

    Attributes:
        text: What was heard. Empty when nothing was.
        ok: False when the recording could not be turned into text at all.
        reason: Why not, in words a person can read.
    """

    text: str = ""
    ok: bool = True
    reason: str = ""


def looks_like_wav(audio: bytes) -> bool:
    """A cheap sanity check before anything else touches the bytes.

    Not a security boundary and not pretending to be one — an engine is
    still handed a file it did not choose. It is here so that an obvious
    mistake, like posting JSON to the audio endpoint, is refused with a
    sentence rather than by whatever a decoder does with nonsense.
    """
    if len(audio) < 44:
        return False
    if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return False
    try:
        (declared,) = struct.unpack_from("<I", audio, 4)
    except struct.error:
        return False
    # The size field counts everything after it. A little slack, because
    # some writers round and some streams are truncated by a byte or two.
    return declared <= len(audio) + 8


class Transcriber:
    """The plug. Anything that turns a recording into words fits here.

    Subclass it, set ``name``, and implement ``transcribe``. Nothing else
    in the gateway needs to know which engine is in use.
    """

    name = "none"

    @property
    def available(self) -> bool:
        """Whether Audio should be offered at all.

        The display asks this before drawing the Audio button as
        pressable. Recording something the gateway cannot process would
        waste the wearer's time and their battery.
        """
        return False

    def transcribe(self, audio: bytes, *, language: str = "auto") -> Transcript:
        raise NotImplementedError


class NoTranscriber(Transcriber):
    """The default: an honest refusal.

    It never returns empty text and calls it success, because an empty
    transcript looks exactly like "you said nothing", and the wearer would
    have no way to tell that apart from "there is no engine installed".
    """

    name = "none"

    def transcribe(self, audio: bytes, *, language: str = "auto") -> Transcript:
        return Transcript(
            ok=False,
            reason="No transcription engine is configured on this gateway.",
        )


class WhisperTranscriber(Transcriber):
    """A local Whisper model, if one has been installed.

    Imported lazily and never listed as a dependency, so its absence
    costs nothing at all. The model runs on this machine; nothing is
    uploaded anywhere.
    """

    name = "faster-whisper"

    def __init__(self, model: str = "base", device: str = "auto") -> None:
        self._model_name = model
        self._device = device
        self._model = None
        self._error = ""

    def _load(self):
        if self._model is not None or self._error:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            self._error = (
                "faster-whisper is not installed on this gateway. "
                "Install it to turn on Audio."
            )
            return None
        try:
            self._model = WhisperModel(self._model_name, device=self._device)
        except Exception as exc:  # a missing model, no disk, wrong device
            self._error = f"the speech model would not load: {exc}"
            return None
        return self._model

    @property
    def available(self) -> bool:
        return self._load() is not None

    def transcribe(self, audio: bytes, *, language: str = "auto") -> Transcript:
        model = self._load()
        if model is None:
            return Transcript(ok=False, reason=self._error)

        import io

        try:
            segments, _ = model.transcribe(
                io.BytesIO(audio),
                language=None if language in ("", "auto") else language,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            return Transcript(ok=False, reason=f"could not transcribe: {exc}")

        return Transcript(text=text[:MAX_TEXT], ok=True)


# Every engine the gateway knows how to plug in. Adding one means adding
# a class above and a line here, and nothing else anywhere.
ENGINES = {
    "none": NoTranscriber,
    "faster-whisper": WhisperTranscriber,
}


def load_transcriber(name: str = "", **options) -> Transcriber:
    """Build the configured engine. An unknown name means none.

    Unknown rather than an error on purpose: a typo in a setting should
    leave Audio switched off and say so, not stop the gateway starting
    and take the task list down with it.
    """
    engine = ENGINES.get((name or "none").strip().lower(), NoTranscriber)
    try:
        return engine(**options)
    except TypeError:
        return NoTranscriber()


def transcribe_upload(
    transcriber: Transcriber, audio: bytes, *, language: str = "auto"
) -> Transcript:
    """Check a recording and hand it to the engine.

    The bytes are not kept anywhere by this function, and there is
    nowhere in this module that writes them down.
    """
    if not audio:
        return Transcript(ok=False, reason="nothing was recorded")
    if len(audio) > MAX_AUDIO_BYTES:
        return Transcript(
            ok=False,
            reason=f"that recording is over {MAX_AUDIO_BYTES // (1024 * 1024)} MB",
        )
    if not looks_like_wav(audio):
        return Transcript(ok=False, reason="that is not a recording")
    if not transcriber.available:
        return Transcript(
            ok=False,
            reason="No transcription engine is configured on this gateway.",
        )

    result = transcriber.transcribe(audio, language=language)
    if result.ok and not result.text.strip():
        # Heard nothing. Said plainly, because an empty draft would look
        # like the wearer had dictated silence on purpose.
        return Transcript(ok=False, reason="nothing was heard")
    return Transcript(
        text=result.text[:MAX_TEXT], ok=result.ok, reason=result.reason
    )
