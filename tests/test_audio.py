"""Tests for transcription and for the drafts it produces.

Two things are being protected.

The recording is never kept. There is no path through any of this that
writes audio down, and the tests below check the shape of that promise
rather than trusting the comment above it.

And an engine that is not installed says so. It must never return empty
text and call that success, because an empty transcript looks exactly
like "you said nothing" — the wearer would have no way to tell that apart
from "there is nothing here to listen with".
"""

import io
import struct
import wave

import pytest

from stub_server.drafts import (
    DRAFT_TTL_SECONDS,
    MAX_DRAFTS,
    DraftBook,
    DraftState,
)
from stub_server.transcription import (
    MAX_AUDIO_BYTES,
    MAX_TEXT,
    NoTranscriber,
    Transcriber,
    Transcript,
    load_transcriber,
    looks_like_wav,
    transcribe_upload,
)

# Ways a module could put something on disk. Word-bounded, so a method
# called is_open does not read as opening a file.
#
# These are written with re.escape rather than as literal patterns
# because an earlier version had a backspace character baked into every
# one of them instead of a word boundary, which made the whole guard
# match nothing and pass without checking anything. _the_guard_itself_works
# below is what would have caught that.
_WRITES = (
    r"\bopen\s*\(",
    r"\bPath\s*\(",
    r"\bos\.(write|makedirs|mkdir)\b",
    r"\bshutil\b",
    r"\btempfile\b",
    r"\bsqlite3\b",
    r"\bjson\.dump\b",
)


def _disk_writes_in(module_name: str) -> list[str]:
    """Every disk-writing thing found in a module. Empty is the good case."""
    import importlib
    import inspect
    import re

    module = importlib.import_module(module_name)
    source = inspect.getsource(module)
    return [
        match.group(0)
        for pattern in _WRITES
        for match in [re.search(pattern, source)]
        if match
    ]


def wav_bytes(seconds: float = 0.1, rate: int = 16000) -> bytes:
    """A real, tiny, silent WAV. Invented; nothing was recorded."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


class Fake(Transcriber):
    """An engine that hears whatever the test tells it to."""

    name = "fake"

    def __init__(self, text="hello there", ok=True, reason="", available=True):
        self._text, self._ok, self._reason = text, ok, reason
        self._available = available
        self.heard: list[bytes] = []

    @property
    def available(self):
        return self._available

    def transcribe(self, audio, *, language="auto"):
        self.heard.append(audio)
        return Transcript(text=self._text, ok=self._ok, reason=self._reason)


# --- what counts as a recording ---------------------------------------


def test_a_real_wav_is_recognised():
    assert looks_like_wav(wav_bytes()) is True


@pytest.mark.parametrize(
    "audio, reason",
    [
        (b"", "nothing at all"),
        (b"short", "too short to be a header"),
        (b"x" * 100, "no RIFF marker"),
        (b"RIFF" + b"\x00" * 100, "no WAVE marker"),
        (b'{"not": "audio"}' + b"\x00" * 60, "JSON posted by mistake"),
    ],
)
def test_things_that_are_not_recordings_are_refused(audio, reason):
    assert looks_like_wav(audio) is False, reason


def test_a_header_claiming_more_than_it_has_is_refused():
    audio = bytearray(wav_bytes())
    struct.pack_into("<I", audio, 4, 900_000_000)

    assert looks_like_wav(bytes(audio)) is False


# --- no engine means saying so ----------------------------------------


def test_with_no_engine_audio_is_not_offered():
    assert NoTranscriber().available is False


def test_no_engine_never_returns_empty_text_and_calls_it_success():
    # The failure this guards: an empty transcript is indistinguishable
    # from "you said nothing", so a missing engine has to say what it is.
    result = transcribe_upload(NoTranscriber(), wav_bytes())

    assert result.ok is False
    assert "engine" in result.reason.lower()


def test_the_default_engine_is_none():
    assert load_transcriber().name == "none"
    assert load_transcriber("").available is False


def test_an_unknown_engine_name_turns_audio_off_rather_than_breaking():
    # A typo in a setting must not stop the gateway starting and take the
    # task list down with it.
    assert load_transcriber("wisper").available is False


def test_the_optional_engine_is_known_but_not_required():
    from stub_server.transcription import ENGINES

    assert "faster-whisper" in ENGINES
    # Absent, it is simply unavailable. Nothing raises.
    assert load_transcriber("faster-whisper").available in (True, False)


# --- transcribing -----------------------------------------------------


def test_a_recording_becomes_words():
    result = transcribe_upload(Fake(text="rerun the tests"), wav_bytes())

    assert result.ok is True
    assert result.text == "rerun the tests"


def test_hearing_nothing_is_said_out_loud():
    result = transcribe_upload(Fake(text="   "), wav_bytes())

    assert result.ok is False
    assert "nothing" in result.reason.lower()


def test_an_engine_that_fails_reports_why():
    result = transcribe_upload(
        Fake(ok=False, reason="the model fell over"), wav_bytes()
    )

    assert result.ok is False
    assert result.reason == "the model fell over"


def test_an_oversized_recording_is_refused_before_the_engine_sees_it():
    engine = Fake()

    result = transcribe_upload(engine, b"RIFF" + b"\x00" * (MAX_AUDIO_BYTES + 10))

    assert result.ok is False
    assert engine.heard == [], "it was handed to the engine anyway"


def test_an_empty_upload_is_refused():
    assert transcribe_upload(Fake(), b"").ok is False


def test_a_very_long_transcript_is_cut():
    result = transcribe_upload(Fake(text="x" * 9000), wav_bytes())

    assert len(result.text) == MAX_TEXT


def test_an_engine_that_is_not_ready_is_not_handed_audio():
    engine = Fake(available=False)

    result = transcribe_upload(engine, wav_bytes())

    assert result.ok is False
    assert engine.heard == []


def test_nothing_in_the_module_writes_audio_anywhere():
    """The promise, checked rather than trusted.

    If transcription ever grows a path that saves a recording, this is
    the test that should make it argue for itself first.
    """
    assert _disk_writes_in("stub_server.transcription") == []


# --- drafts -----------------------------------------------------------


@pytest.fixture
def book():
    return DraftBook()


def test_a_draft_is_created_from_what_was_heard(book):
    draft = book.create("task-17", 4, "rerun the tests", now=1000.0)

    assert draft.task_id == "task-17"
    assert draft.revision == 4
    assert draft.text == "rerun the tests"
    assert draft.state is DraftState.PENDING
    assert draft.is_open is True


def test_a_draft_can_be_edited_from_somewhere_more_comfortable(book):
    draft = book.create("task-17", 4, "rerun the tets", now=1000.0)

    edited = book.edit(draft.id, "rerun the tests and deploy if they pass")

    assert edited.text == "rerun the tests and deploy if they pass"
    assert book.get(draft.id, now=1000.0).text == edited.text


def test_editing_something_that_is_gone_changes_nothing(book):
    assert book.edit("nope", "text") is None


def test_discarding_takes_the_words_with_it(book):
    draft = book.create("task-17", 4, "something private", now=1000.0)

    assert book.discard(draft.id) is True
    assert book.get(draft.id, now=1000.0) is None


def test_sending_drops_the_text_rather_than_keeping_a_copy(book):
    # The words live in the agent's own record now. A second copy here
    # would be the start of the archive this is not.
    draft = book.create("task-17", 4, "rerun the tests", now=1000.0)

    sent = book.mark_sent(draft.id)

    assert sent.state is DraftState.SENT
    assert sent.text == ""
    assert book.get(draft.id, now=1000.0) is None


def test_a_draft_carries_the_revision_it_was_written_against(book):
    # So a task that moved on refuses it, exactly as an action would be.
    draft = book.create("task-17", 4, "words", now=1000.0)

    assert draft.revision == 4
    assert book.to_payload(now=1000.0)[0]["revision"] == 4


def test_a_forgotten_draft_does_not_sit_there_for_a_week(book):
    book.create("task-17", 4, "words", now=1000.0)

    later = 1000.0 + DRAFT_TTL_SECONDS + 1

    assert book.open_drafts(now=later) == []


def test_a_draft_within_its_life_is_still_there(book):
    book.create("task-17", 4, "words", now=1000.0)

    assert len(book.open_drafts(now=1000.0 + DRAFT_TTL_SECONDS - 1)) == 1


def test_drafts_do_not_pile_up_without_bound(book):
    for n in range(MAX_DRAFTS + 10):
        book.create(f"task-{n}", 1, "words", now=1000.0)

    assert len(book.open_drafts(now=1000.0)) <= MAX_DRAFTS


def test_the_open_draft_for_a_task_can_be_found(book):
    book.create("task-1", 1, "one", now=1000.0)
    book.create("task-2", 1, "two", now=1001.0)

    assert book.for_task("task-2", now=1002.0).text == "two"
    assert book.for_task("task-9", now=1002.0) is None


def test_very_long_dictation_is_cut_when_the_draft_is_made(book):
    draft = book.create("task-17", 4, "x" * 9000, now=1000.0)

    assert len(draft.text) <= 2000


def test_the_payload_is_what_both_screens_read(book):
    book.create("task-17", 4, "rerun the tests", now=1000.0)

    payload = book.to_payload(now=1000.0)[0]

    assert set(payload) == {"draft_id", "task_id", "revision", "text", "state"}


def test_nothing_in_the_module_writes_a_draft_to_disk():
    assert _disk_writes_in("stub_server.drafts") == []


def test_the_guard_itself_works():
    """The two tests above are only worth anything if they can fail.

    An earlier version of them had a backspace character where a word
    boundary was meant, so every pattern matched nothing and both passed
    without checking a thing. This points the same guard at a module that
    genuinely does read files, and insists it notices.
    """
    assert _disk_writes_in("stub_server.server") != []
