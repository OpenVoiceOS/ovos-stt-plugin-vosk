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
        self.model = KaldiModel(model_path)

    def execute(self, audio, language=None):
        kaldi = KaldiRecognizer(self.model, 16000)
        kaldi.AcceptWaveform(audio.get_wav_data())
        res = kaldi.FinalResult()
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


class VoskKaldiStreamingSTT(StreamingSTT, VoskKaldiSTT):

    def __init__(self):
        super().__init__()
        self.verbose = self.config.get("verbose", True)

    def create_streaming_thread(self):
        self.queue = Queue()
        kaldi = KaldiRecognizer(self.model, 16000)
        return VoskKaldiStreamThread(
            self.queue, self.lang, kaldi, self.verbose
        )
