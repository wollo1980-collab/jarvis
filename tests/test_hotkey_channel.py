"""Tests fuer hotkey_channel.py (ADR-041) - kein echtes Mikrofon, keine
echten Tastatur-Hooks: recorder/transcriber/speak sind injiziert, die
optionalen Modul-Abhaengigkeiten werden gemonkeypatcht."""
from __future__ import annotations

import io
import threading
import time
import wave
from unittest.mock import MagicMock

import hotkey_channel
from hotkey_channel import SAMPLE_RATE, HotkeyChannel, _to_wav


class FakeTranscriber:
    def __init__(self, text="erinnere mich an den Test"):
        self.text = text
        self.calls: list = []

    def transcribe(self, audio: bytes, filename: str = "") -> str:
        self.calls.append((audio, filename))
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


def _channel(transcriber=None, recorder=None, runtime=None):
    return HotkeyChannel(
        runtime=runtime or MagicMock(),
        transcriber=transcriber or FakeTranscriber(),
        speak=MagicMock(),
        recorder=recorder or (lambda: b"PCM-DATEN"),
    )


def test_followup_window_is_configurable_and_clamped():
    """PO-Reibung 2026-07-11 'viel zu lange im Lausch-Modus': das Anschluss-
    Fenster ist konfigurierbar; ein zu kleiner Wert wird auf einen sinnvollen
    Boden geklemmt (nie sofort schliessen)."""
    from hotkey_channel import _FOLLOWUP_WINDOW_SECONDS

    assert _channel()._followup_seconds == _FOLLOWUP_WINDOW_SECONDS   # Default
    assert HotkeyChannel(runtime=MagicMock(), transcriber=FakeTranscriber(),
                         speak=MagicMock(), followup_seconds=2.0)._followup_seconds == 2.0
    # 0/negativ -> Boden 0.5 (sonst wuerde das Fenster sofort zuschnappen)
    assert HotkeyChannel(runtime=MagicMock(), transcriber=FakeTranscriber(),
                         speak=MagicMock(), followup_seconds=0.0)._followup_seconds == 0.5


def _run_toggle_cycle(channel):
    """Erster Hotkey-Druck startet den Worker; auf Abschluss warten."""
    channel._on_hotkey()
    channel._worker.join(timeout=2.0)
    assert not channel._worker.is_alive()


def test_toggle_records_transcribes_and_submits():
    runtime = MagicMock()
    transcriber = FakeTranscriber("was steht an?")
    channel = _channel(transcriber=transcriber, runtime=runtime)

    _run_toggle_cycle(channel)

    # Aufnahme wurde als WAV an den Transcriber gegeben ...
    audio, filename = transcriber.calls[0]
    assert audio.startswith(b"RIFF") and filename == "ptt.wav"
    # ... und das Transkript in die normale Pipeline (volle Intents, async).
    runtime.submit.assert_called_once()
    args, kwargs = runtime.submit.call_args
    assert args[0] == "was steht an?"
    assert kwargs.get("allow_async") is True
    assert "plan_filter" not in kwargs  # lokaler Kanal = wie Konsole


def test_second_press_stops_recording():
    """Toggle: Waehrend der recorder auf das Flag wartet, beendet der zweite
    Druck die Aufnahme - der Worker laeuft durch."""
    channel = _channel()

    def waiting_recorder():
        while channel._recording.is_set():
            time.sleep(0.01)
        return b"PCM"

    channel._recorder = waiting_recorder
    channel._on_hotkey()          # Start
    time.sleep(0.05)
    channel._on_hotkey()          # Stopp
    channel._worker.join(timeout=2.0)

    channel.runtime.submit.assert_called_once()


def test_empty_transcript_speaks_and_does_not_execute():
    runtime = MagicMock()
    channel = _channel(transcriber=FakeTranscriber(""), runtime=runtime)

    _run_toggle_cycle(channel)

    runtime.submit.assert_not_called()
    assert any("verstanden" in c.args[0].lower() for c in channel._raw_speak.call_args_list)


def test_transcriber_error_speaks_and_does_not_execute():
    runtime = MagicMock()
    channel = _channel(transcriber=FakeTranscriber(RuntimeError("api kaputt")), runtime=runtime)

    _run_toggle_cycle(channel)

    runtime.submit.assert_not_called()
    channel._raw_speak.assert_called()


def test_empty_audio_speaks_and_does_not_transcribe():
    runtime = MagicMock()
    transcriber = FakeTranscriber()
    channel = _channel(transcriber=transcriber, recorder=lambda: b"", runtime=runtime)

    _run_toggle_cycle(channel)

    assert transcriber.calls == []
    runtime.submit.assert_not_called()
    assert any("aufgenommen" in c.args[0].lower() for c in channel._raw_speak.call_args_list)


def test_start_refuses_gracefully_without_dependencies(monkeypatch):
    monkeypatch.setattr(hotkey_channel, "_sounddevice", None)
    channel = _channel()
    assert channel.start() is False  # kein Crash, kein Listener


def test_stop_without_start_is_safe():
    channel = _channel()
    channel.stop()  # darf nicht werfen


def test_make_speakable_drops_sources_and_urls():
    """Nutzungslauf-Befund 2026-07-09: URLs und Quellen-Bloecke werden nicht
    vorgelesen - Text-Kanaele behalten sie."""
    from hotkey_channel import make_speakable

    text = (
        "Kurzer Ueberblick zu den Treffern. Details unter https://example.com/sehr/lange/url dazu.\n\n"
        "Quellen:\n- https://tagesschau.de/x\n- https://spiegel.de/y"
    )
    spoken = make_speakable(text)
    assert "http" not in spoken
    assert "Quellen" not in spoken
    assert "Kurzer Ueberblick zu den Treffern." in spoken


def test_make_speakable_caps_long_answers_at_sentence():
    from hotkey_channel import _MAX_SPOKEN_CHARS, make_speakable

    long_text = ("Das ist ein Satz mit etwas Inhalt. " * 60).strip()
    spoken = make_speakable(long_text)
    assert len(spoken) < len(long_text)
    assert len(spoken) <= _MAX_SPOKEN_CHARS + 50
    # Varianten-Pool (Lebendigkeit 2026-07-10) statt fester Satz.
    assert any(spoken.endswith(s.strip()) for s in hotkey_channel._SPOKEN_SUFFIXES)


def test_make_speakable_speaks_ordinals_instead_of_numbers():
    """Nutzungslauf-Befund 2026-07-09: '1. 2. 3.' wird als 'eins, zwei, drei'
    vorgelesen - gesprochen soll es 'Erstens ... Zweitens ...' heissen."""
    from hotkey_channel import make_speakable

    spoken = make_speakable("Die Lage, Sir:\n1. Meldung A\n2. Meldung B\n3. Meldung C")
    assert "Erstens: Meldung A" in spoken
    assert "Zweitens: Meldung B" in spoken
    assert "Drittens: Meldung C" in spoken
    assert "1." not in spoken and "2." not in spoken


def test_make_speakable_caps_lists_at_complete_line():
    """Nutzungslauf-Befund 2026-07-10: 'Die Lage' brach beim Deckel mitten
    in Meldung 2 ab (Titel + halber Anriss). Listen werden jetzt an der
    letzten VOLLSTAENDIGEN Zeile gekappt - nie mitten in einem Punkt."""
    from hotkey_channel import _MAX_SPOKEN_CHARS, make_speakable

    items = [f"{i}. Meldung {i}: " + "Inhalt " * 20 for i in range(1, 6)]
    text = "Die Lage, Sir:\n" + "\n".join(items)
    assert len(text) > _MAX_SPOKEN_CHARS

    spoken = make_speakable(text)
    body = spoken
    for suffix in hotkey_channel._SPOKEN_SUFFIXES:
        body = body.removesuffix(suffix.strip())
    # Jede begonnene Meldung ist vollstaendig drin - keine angeschnittene:
    kept = [line for line in body.splitlines() if line.startswith("Erstens") or "tens: " in line]
    for line in kept:
        assert line.rstrip().endswith("Inhalt")
    assert len(spoken) <= _MAX_SPOKEN_CHARS + 50


def test_make_speakable_leaves_short_text_untouched():
    from hotkey_channel import make_speakable

    assert make_speakable("Notiert, Sir: «Zahnarzt» — 09:00") == "Notiert, Sir: «Zahnarzt» — 09:00"
    assert make_speakable("") == ""


def test_quiet_streams_bridges_missing_stderr(monkeypatch):
    """Live-Fund 2026-07-09: unter pythonw ist stderr None - openwakewords
    tqdm-Download crashte damit ('Wake-Word-Modell nicht ladbar'). Der
    Kontextmanager ueberbrueckt fehlende Streams und stellt sie wieder her."""
    import sys

    from hotkey_channel import _quiet_streams

    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "stdout", None)
    with _quiet_streams():
        assert sys.stderr is not None and sys.stdout is not None
        sys.stderr.write("tqdm darf schreiben")  # darf nicht werfen
    assert sys.stderr is None and sys.stdout is None  # sauber restauriert


# --- Wake-Word (ADR-044) ------------------------------------------------------


class FakeStream:
    """Mikrofonstream-Ersatz: liefert vorbereitete (frames, score)-Paare.
    numpy-Arrays wie sounddevice sie liefert."""

    def __init__(self, frames):
        import numpy as np

        self._frames = [np.full((1280, 1), amplitude, dtype=np.int16) for amplitude in frames]
        self._i = 0

    def read(self, n):
        if self._i >= len(self._frames):
            raise StopIteration("keine Frames mehr")
        frame = self._frames[self._i]
        self._i += 1
        return frame, False


def _wake_listener(channel, scores):
    """Listener mit injiziertem Scorer: gibt der Reihe nach `scores` zurueck."""
    from hotkey_channel import WakeWordListener

    it = iter(scores)
    return WakeWordListener(channel, scorer=lambda frame: next(it, 0.0))


def test_process_audio_notifies_transcript_listener():
    """PO-Wunsch 10.07.2026: Zuruf-/Hotkey-Gespraeche erscheinen als
    Mitschrift im Browser-UI - Transkript UND gesprochene Antwort."""
    runtime = MagicMock()

    def fake_submit(text, reply_callback, plan_filter=None, allow_async=False, confirmer=None, source=""):
        reply_callback("Notiert, Sir.")

    runtime.submit.side_effect = fake_submit
    channel = _channel(runtime=runtime)
    notes = []
    channel.transcript_listener = lambda role, text: notes.append((role, text))

    channel.process_audio(b"PCM")

    assert notes == [("user", "erinnere mich an den Test"), ("jarvis", "Notiert, Sir.")]
    channel._raw_speak.assert_called_once()  # gesprochen wird weiterhin


def test_speak_notifies_orb_states_spricht_then_bereit():
    """PO-Wunsch 10.07.2026: der Orb macht was, wenn Jarvis redet - speak()
    meldet spricht -> bereit (auch bei TTS-Fehler zurueck auf bereit)."""
    channel = _channel()
    states = []
    channel.state_listener = states.append

    channel.speak("Hallo, Sir.")
    assert states == ["spricht", "bereit"]

    channel._raw_speak.side_effect = RuntimeError("TTS kaputt")
    states.clear()
    try:
        channel.speak("Noch einmal.")
    except RuntimeError:
        pass
    assert states == ["spricht", "bereit"]  # finally raeumt immer auf


def test_process_audio_emits_arbeitet_state():
    runtime = MagicMock()
    runtime.submit.side_effect = (
        lambda text, reply_callback, plan_filter=None, allow_async=False, confirmer=None, source="": reply_callback("Ok.")
    )
    channel = _channel(runtime=runtime)
    states = []
    channel.state_listener = states.append

    channel.process_audio(b"PCM")

    # arbeitet (Verarbeitung) -> spricht/bereit (Antwort via speak)
    assert states == ["arbeitet", "spricht", "bereit"]


def test_wake_flow_emits_hoert_state(monkeypatch):
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    states = []
    channel.state_listener = states.append
    from hotkey_channel import WakeWordListener

    scores = iter([0.1, 0.9])
    listener = WakeWordListener(channel, scorer=lambda f: next(scores, 0.0), reset=MagicMock())
    listener._await_reply_finished = lambda timeout=0: False  # kein Konversationsfenster im Test
    stream = FakeStream([500, 500] + [0] * 5 + [800] * 10 + [0] * 25)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    assert "hoert" in states  # Aufnahme nach dem Wake-Word sichtbar


def test_process_audio_logs_latency_numbers_only(caplog):
    """Messinstrument der Latenz-Scheibe (PO-Befund 2026-07-10): Dauern je
    Stufe landen im Log - aber NUR Zahlen/Laengen, nie Gespraechsinhalte."""
    import logging

    runtime = MagicMock()
    runtime.submit.side_effect = (
        lambda text, reply_callback, plan_filter=None, allow_async=False, confirmer=None, source="": reply_callback("Geheime Antwort")
    )
    channel = _channel(transcriber=FakeTranscriber("geheime frage"), runtime=runtime)

    with caplog.at_level(logging.INFO, logger="jarvis.runtime.hotkey"):
        channel.process_audio(b"PCM")

    latency = [r.message for r in caplog.records if r.message.startswith("Latenz:")]
    assert len(latency) == 1
    assert "Transkription" in latency[0] and "Verarbeitung" in latency[0]
    assert "geheime" not in latency[0].lower()  # Inhalte bleiben draussen


def test_process_audio_survives_broken_transcript_listener():
    """Die Mitschrift ist Beiwerk - ein kaputter Listener darf weder
    Verarbeitung noch Sprachausgabe stoeren."""
    runtime = MagicMock()
    runtime.submit.side_effect = (
        lambda text, reply_callback, plan_filter=None, allow_async=False, confirmer=None, source="": reply_callback("Ok.")
    )
    channel = _channel(runtime=runtime)
    channel.transcript_listener = lambda role, text: (_ for _ in ()).throw(RuntimeError("UI weg"))

    channel.process_audio(b"PCM")  # darf nicht werfen

    runtime.submit.assert_called_once()
    channel._raw_speak.assert_called_once()


def test_wake_word_triggers_shared_pipeline(monkeypatch):
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    reset = MagicMock()
    from hotkey_channel import WakeWordListener

    scores = iter([0.1, 0.9])
    listener = WakeWordListener(channel, scorer=lambda f: next(scores, 0.0), reset=reset)
    listener._await_reply_finished = lambda timeout=0: False  # kein Konversationsfenster im Test
    # Nach dem Trigger: kurzer stiller Vorlauf, dann Sprache, dann Stille.
    stream = FakeStream([500, 500] + [0] * 5 + [800] * 10 + [0] * 25)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass  # Frames aufgebraucht = Loop-Ende im Test

    channel.process_audio.assert_called_once()
    audio = channel.process_audio.call_args.args[0]
    assert isinstance(audio, bytes) and len(audio) > 0
    reset.assert_called()  # Modell-Puffer geleert (gegen Endlos-Schleife)


def test_wake_records_quiet_speaker_via_calibrated_threshold(monkeypatch):
    """Live-Fund 2026-07-09 (2. Runde): feste Schwelle 300 verpasste leise
    Sprecher - die Frage nach dem Wake wurde als 'keine Sprache' verworfen.
    Jetzt kalibriert sich die Schwelle am Pegel des Wake-Words selbst."""
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    from hotkey_channel import WakeWordListener

    scores = iter([0.1, 0.9])
    listener = WakeWordListener(channel, scorer=lambda f: next(scores, 0.0), reset=MagicMock())
    listener._await_reply_finished = lambda timeout=0: False  # kein Konversationsfenster im Test
    # Leises "Hey Jarvis" (Pegel 200) -> Schwelle ~60; die Frage (Pegel 150)
    # laege unter der alten Konstante 300, wird jetzt aber erkannt.
    stream = FakeStream([200, 200] + [0] * 5 + [150] * 10 + [0] * 25)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    channel.process_audio.assert_called_once()


def test_wake_floor_never_exceeds_half_the_voice_level(monkeypatch):
    """Live-Fund 2026-07-10: Wake-Word kam mit Pegel ~61, die Frage mit
    Spitzenpegel 59 - die starre Untergrenze 60 verwarf sie wortlos. Die
    Untergrenze liegt jetzt nie ueber der Haelfte des gehoerten Stimmpegels:
    wer leise weckt, darf auch leise fragen."""
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    from hotkey_channel import WakeWordListener

    scores = iter([0.1, 0.9])
    listener = WakeWordListener(channel, scorer=lambda f: next(scores, 0.0), reset=MagicMock())
    listener._await_reply_finished = lambda timeout=0: False
    # Leises Wake-Word (61) -> Schwelle ~30 statt starrer 60; Frage (59) zaehlt.
    stream = FakeStream([61, 61] + [0] * 5 + [59] * 10 + [0] * 25)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    channel.process_audio.assert_called_once()


def test_announce_plays_preroll_plus_ack_and_logs(monkeypatch, caplog):
    """Live-Fund 2026-07-10: eine Wake-Bestaetigung blieb stumm und das Log
    schwieg dazu. Jetzt: Vorlauf + Variante werden gespielt und sichtbar
    (INFO) protokolliert - Stummbleiben ist kein Raetselraten mehr."""
    import logging

    played: list[bytes] = []
    monkeypatch.setattr(hotkey_channel, "_play_wav_bytes", played.append)
    channel = _channel()
    channel._wake_acks = [b"RIFF-fake-ack"]
    from hotkey_channel import WakeWordListener

    listener = WakeWordListener(channel, scorer=lambda f: 0.0)
    with caplog.at_level(logging.INFO, logger="jarvis.runtime.hotkey"):
        listener._announce()

    assert played == [hotkey_channel._WAKE_PREROLL, b"RIFF-fake-ack"]
    assert any("Wake-Bestaetigung abgespielt" in r.message for r in caplog.records)
    assert not channel._speaking.is_set()  # Selbstschutz-Fenster wieder zu


def test_wake_preroll_is_long_enough_for_standby_devices():
    """700 ms Stille-Vorlauf (Live-Fund 2026-07-10: 300 ms reichten nicht -
    kurze Bestaetigung wurde nach Geraete-Standby komplett verschluckt)."""
    with wave.open(io.BytesIO(hotkey_channel._WAKE_PREROLL)) as w:
        seconds = w.getnframes() / w.getframerate()
    assert seconds >= 0.7


def test_conversation_window_allows_followup_without_wake_word(monkeypatch):
    """Nutzungslauf-Befund 2026-07-10: 'Hey Jarvis' vor JEDEM Satz stoert den
    Konversationsfluss. Nach der gesprochenen Antwort bleibt ein Anschluss-
    Fenster offen - die naechste Frage geht OHNE Wake-Word in die Pipeline."""
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    from hotkey_channel import WakeWordListener

    scores = iter([0.9])
    listener = WakeWordListener(channel, scorer=lambda f: next(scores, 0.0), reset=MagicMock())
    listener._await_reply_finished = lambda timeout=0: True  # Antwort "kam"
    # Wake-Frame + erste Frage + Stille | Anschlussfrage + Stille | nur Stille
    stream = FakeStream(
        [500] + [800] * 10 + [0] * 25          # Runde 1 (mit Wake-Word)
        + [700] * 10 + [0] * 25                # Anschlussfrage (OHNE Wake-Word)
        + [0] * 80                             # Schweigen -> Fenster schliesst
    )

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    assert channel.process_audio.call_count == 2  # beide Runden verarbeitet


def test_conversation_window_closes_without_reply(monkeypatch):
    """Kommt keine gesprochene Antwort (z. B. Fehler), faellt der Lauscher
    direkt in den Wake-Modus zurueck - kein haengendes Fenster."""
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    from hotkey_channel import WakeWordListener

    scores = iter([0.9])
    listener = WakeWordListener(channel, scorer=lambda f: next(scores, 0.0), reset=MagicMock())
    listener._await_reply_finished = lambda timeout=0: False  # keine Antwort
    stream = FakeStream([500] + [800] * 10 + [0] * 25)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    assert channel.process_audio.call_count == 1  # nur die Wake-Runde


def test_await_reply_finished_tracks_speaking_window():
    from hotkey_channel import WakeWordListener

    channel = _channel()
    listener = WakeWordListener(channel, scorer=lambda f: 0.0)

    # Antwort beginnt nach 0.15 s und dauert 0.2 s -> True
    def speak_soon():
        import time as t

        t.sleep(0.15)
        channel._speaking.set()
        t.sleep(0.2)
        channel._speaking.clear()

    thread = threading.Thread(target=speak_soon, daemon=True)
    thread.start()
    assert listener._await_reply_finished(timeout=3.0) is True
    thread.join()

    # Keine Antwort innerhalb des Zeitfensters -> False
    assert listener._await_reply_finished(timeout=0.2) is False


def test_wake_without_speech_is_discarded_silently(monkeypatch):
    """Live-Fund 2026-07-09: Wake ohne Anschlussfrage (Fehltrigger) wird
    still verworfen - kein process_audio, keine genervte Ansage."""
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    reset = MagicMock()
    from hotkey_channel import WakeWordListener

    scores = iter([0.9])
    listener = WakeWordListener(channel, scorer=lambda f: next(scores, 0.0), reset=reset)
    stream = FakeStream([500] + [0] * 60)  # nach dem Wake: nur Stille

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    channel.process_audio.assert_not_called()
    reset.assert_called()


def test_wake_word_below_threshold_never_triggers(monkeypatch):
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    listener = _wake_listener(channel, scores=[0.1, 0.3, 0.49, 0.2])
    stream = FakeStream([500] * 4)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    channel.process_audio.assert_not_called()


def test_wake_word_muted_while_jarvis_speaks(monkeypatch):
    """Selbstschutz (ADR-044): waehrend der TTS-Wiedergabe zaehlt kein Score -
    Jarvis weckt sich nicht mit der eigenen Stimme."""
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    channel._speaking.set()  # Jarvis "spricht"
    listener = _wake_listener(channel, scores=[0.99, 0.99, 0.99])
    stream = FakeStream([500] * 3)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    channel.process_audio.assert_not_called()


def test_wake_announce_plays_cached_ack_and_mutes_listening(monkeypatch):
    """PO-Wunsch 2026-07-09: statt Piepton ein gesprochenes 'Ja, Sir?' -
    gecacht, und waehrend der Wiedergabe lauscht das Wake-Word nicht."""
    from hotkey_channel import WakeWordListener

    played = []
    speaking_during = []
    beeps = []
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: beeps.append(start))

    channel = _channel()
    channel._wake_acks = [b"WAV-BYTES"]
    monkeypatch.setattr(
        hotkey_channel,
        "_play_wav_bytes",
        lambda data: (played.append(data), speaking_during.append(channel._speaking.is_set())),
    )

    WakeWordListener(channel, scorer=lambda f: 0.0)._announce()

    # Aufweck-Vorlauf (Stille) VOR der Bestaetigung - Live-Befund 2026-07-10:
    # Audiogeraete im Standby verzerren sonst den ersten Ton zu Rauschen.
    assert len(played) == 2
    assert played[0] == hotkey_channel._WAKE_PREROLL
    assert played[0].startswith(b"RIFF")
    assert played[1] == b"WAV-BYTES"
    assert speaking_during == [True, True]  # stumm geschaltet waehrend allem
    assert not channel._speaking.is_set()   # danach wieder frei
    assert beeps == []                      # kein Piepton


def test_silence_wav_is_valid_and_short():
    import io
    import wave

    data = hotkey_channel._silence_wav(300)
    with wave.open(io.BytesIO(data), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        duration = wav.getnframes() / wav.getframerate()
    assert 0.25 <= duration <= 0.35
    assert max(data[44:]) == 0  # wirklich still


def test_wake_announce_falls_back_to_beep_without_ack(monkeypatch):
    from hotkey_channel import WakeWordListener

    beeps = []
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: beeps.append(start))
    channel = _channel()  # keine Wake-Bestaetigungen gecacht

    WakeWordListener(channel, scorer=lambda f: 0.0)._announce()

    assert beeps == [True]


def test_wake_word_start_refuses_without_package(monkeypatch):
    from hotkey_channel import WakeWordListener

    monkeypatch.setattr(hotkey_channel, "_openwakeword", None)
    listener = WakeWordListener(_channel())
    assert listener.start() is False


def test_channel_without_wake_flag_starts_no_listener(monkeypatch):
    """wake_word=False (Default): kein Dauer-Lauscher - Privacy-by-default."""
    channel = HotkeyChannel(
        runtime=MagicMock(), transcriber=MagicMock(), speak=MagicMock(), wake_word=False
    )
    assert channel._wake_word_enabled is False
    assert channel._wake_listener is None


def test_speak_sets_and_clears_speaking_flag():
    seen = []
    channel = HotkeyChannel(
        runtime=MagicMock(),
        transcriber=MagicMock(),
        speak=lambda text: seen.append(channel._speaking.is_set()),
    )
    channel.speak("Hallo")
    assert seen == [True]              # waehrend der Ausgabe gesetzt
    assert not channel._speaking.is_set()  # danach wieder frei


def test_to_wav_produces_valid_mono_16k():
    data = _to_wav(b"\x00\x01" * 160)
    with wave.open(io.BytesIO(data), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == SAMPLE_RATE
        assert w.getsampwidth() == 2


def test_noise_level_wake_trigger_is_discarded_silently(monkeypatch):
    """2. Live-Fund 2026-07-10 ("er hoert staendig zu"): Fehl-Trigger bei
    Stimmpegel ~21 (= Grundrauschen) kalibrierte Schwelle 11 - UNTER dem
    Rauschen; das Anschluss-Fenster schloss nie. Trigger unterm
    Rausch-Minimum werden jetzt still verworfen: keine Bestaetigung,
    keine Aufnahme, keine Verarbeitung."""
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    channel._wake_acks = [b"RIFF-fake"]
    played = []
    monkeypatch.setattr(hotkey_channel, "_play_wav_bytes", played.append)
    from hotkey_channel import WakeWordListener

    scores = iter([0.1, 0.63])
    listener = WakeWordListener(channel, scorer=lambda f: next(scores, 0.0), reset=MagicMock())
    listener._await_reply_finished = lambda timeout=0: False
    # "Wake" bei Pegel 21 (Rauschen), danach weiter Rauschen.
    stream = FakeStream([21, 21] + [18] * 15)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    channel.process_audio.assert_not_called()
    assert played == []  # kein "Ja, Sir?" aus dem Nichts


def test_quiet_but_real_wake_still_works_above_noise_floor(monkeypatch):
    """Gegenprobe: der leise-Sprecher-Fix von mittags (Wake 61 / Frage 59)
    bleibt erhalten - Schwelle jetzt ~30 statt 60, aber nie unter 30."""
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    from hotkey_channel import WakeWordListener

    scores = iter([0.1, 0.9])
    listener = WakeWordListener(channel, scorer=lambda f: next(scores, 0.0), reset=MagicMock())
    listener._await_reply_finished = lambda timeout=0: False
    stream = FakeStream([61, 61] + [0] * 5 + [59] * 10 + [0] * 25)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    channel.process_audio.assert_called_once()
