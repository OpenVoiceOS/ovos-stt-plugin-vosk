from os.path import isdir
import json
from vosk import Model as KaldiModel, KaldiRecognizer
from queue import Queue
import numpy as np
from mycroft.util.log import LOG
from mycroft.stt import STT, StreamThread, StreamingSTT


class VoskKaldiSTT(STT):
    def __init__(self):
        super().__init__()
        model_path = self.config.get("model_folder")
        if not model_path or not isdir(model_path):
            LOG.error("You need to provide a valid model folder")
            LOG.info(
                "download a model from https://alphacephei.com/vosk/models")
            raise FileNotFoundError
        self.kaldi = KaldiRecognizer(KaldiModel(model_path), 16000)

    def execute(self, audio, language=None):
        self.kaldi.AcceptWaveform(audio.get_wav_data())
        res = self.kaldi.FinalResult()
        res = json.loads(res)
        return res["text"]


class VoskKaldiStreamThread(StreamThread):
    def __init__(self, queue, lang, kaldi, verbose=True):
        super().__init__(queue, lang)
        self.kaldi = kaldi
        self.verbose = verbose
        self.previous_partial = ""

    def handle_audio_stream(self, audio, language):
        for a in audio:
            data = np.frombuffer(a, np.int16)
            if self.kaldi.AcceptWaveform(data):
                res = self.kaldi.Result()
                res = json.loads(res)
                self.text = res["text"]
            else:
                res = self.kaldi.PartialResult()
                res = json.loads(res)
                self.text = res["partial"]
        if self.verbose:
            if self.previous_partial != self.text:
                LOG.info("Partial Transcription: " + self.text)
        self.previous_partial = self.text

        return self.text

    def finalize(self):
        if self.previous_partial:
            self.kaldi.FinalResult()
            self.previous_partial = ""


class VoskKaldiStreamingSTT(StreamingSTT, VoskKaldiSTT):

    def __init__(self):
        super().__init__()
        self.verbose = self.config.get("verbose", False)

    def create_streaming_thread(self):
        self.queue = Queue()
        return VoskKaldiStreamThread(
            self.queue, self.lang, self.kaldi, self.verbose
        )

    def stream_stop(self):
        if self.stream is not None:
            self.stream.finalize()
        return super().stream_stop()
