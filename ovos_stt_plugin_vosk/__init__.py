from os.path import isdir
import json
from vosk import Model as KaldiModel, KaldiRecognizer
from queue import Queue
import numpy as np
from ovos_utils.log import LOG
from ovos_plugin_manager.templates.stt import STT, StreamThread, StreamingSTT
from ovos_skill_installer import download_extract_zip, download_extract_tar
from os.path import join, exists, isdir
from ovos_utils.xdg_utils import xdg_data_home
from ovos_utils.file_utils import read_vocab_file, resolve_resource_file, resolve_ovos_resource_file


class VoskKaldiSTT(STT):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # model_folder for backwards compat
        self.model_path = self.config.get("model_folder") or self.config.get("model")
        if not self.model_path and self.lang:
            self.model_path = self.download_language(self.lang)
        if not self.model_path or not isdir(self.model_path):
            LOG.error("You need to provide a valid model path or url")
            LOG.info(
                "download a model from https://alphacephei.com/vosk/models")
            raise FileNotFoundError

        self.engines = {
            self.lang: KaldiRecognizer(KaldiModel(self.model_path), 16000)
        }
        self.limited_voc_engines = {}
        self.limited = False

    def download_language(self, lang=None):
        lang = lang or self.lang
        lang = lang.split("-")[0].lower()
        model_path = self.lang2modelurl(lang)
        if model_path and model_path.startswith("http"):
            model_path = self.download_model(model_path)
        return model_path

    def load_language(self, lang=None):
        lang = lang or self.lang
        lang = lang.split("-")[0].lower()
        if lang in self.engines or lang in self.limited_voc_engines:
            return
        model_path = self.download_language(lang)
        if model_path:
            self.engines[lang] = KaldiRecognizer(KaldiModel(model_path), 16000)
        else:
            LOG.error(f"No default model available for {lang}")
            raise FileNotFoundError

    def unload_language(self, lang=None):
        lang = lang or self.lang
        if lang in self.engines:
            del self.engines[lang]
            self.engines.pop(lang)
        if lang in self.limited_voc_engines:
            del self.limited_voc_engines[lang]
            self.limited_voc_engines.pop(lang)

    def enable_full_vocabulary(self, lang=None):
        """ enable default transcription mode """
        lang = lang or self.lang
        self.limited = False
        if lang in self.limited_voc_engines:
            self.limited_voc_engines.pop(lang)
            self.engines[lang] = KaldiRecognizer(KaldiModel(model_path), 16000)

    def enable_limited_vocabulary(self, words, lang=None, permanent=True):
        """
        enable limited vocabulary mode
        will only consider pre defined .voc files
        """
        lang = lang or self.lang
        if lang == self.lang:
            model_path = self.model_path
        else:
            model_path = self.lang2modelurl(lang)
        if model_path:
            self.limited_voc_engines[lang] = KaldiRecognizer(KaldiModel(model_path),
                                                             16000, json.dumps(words))
            if permanent:
                del self.engines[lang]
                self.engines[lang] = self.limited_voc_engines[lang]
            self.limited = True

    @staticmethod
    def download_model(url):
        folder = join(xdg_data_home(), 'vosk')
        name = url.split("/")[-1].split(".")[0]
        model_path = join(folder, name)
        if not exists(model_path):
            LOG.info(f"Downloading model for vosk {url}")
            LOG.info("this might take a while")
            if url.endswith(".zip"):
                download_extract_zip(url, folder=folder, skill_folder_name=name)
            else:
                download_extract_tar(url, folder=folder, skill_folder_name=name)
            LOG.info(f"Model downloaded to {model_path}")

        return model_path

    @staticmethod
    def lang2modelurl(lang, small=True):
        lang2url = {
            "en": "http://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
            "en-in": "http://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip",
            "cn": "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.3.zip",
            "ru": "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.15.zip",
            "fr": "https://alphacephei.com/vosk/models/vosk-model-small-fr-pguyot-0.3.zip",
            "de": "https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip",
            "es": "https://alphacephei.com/vosk/models/vosk-model-small-es-0.3.zip",
            "pt": "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip",
            "gr": "https://alphacephei.com/vosk/models/vosk-model-el-gr-0.7.zip",
            "tr": "https://alphacephei.com/vosk/models/vosk-model-small-tr-0.3.zip",
            "vn": "https://alphacephei.com/vosk/models/vosk-model-small-vn-0.3.zip",
            "it": "https://alphacephei.com/vosk/models/vosk-model-small-it-0.4.zip",
            "nl": "https://alphacephei.com/vosk/models/vosk-model-nl-spraakherkenning-0.6-lgraph.zip",
            "ca": "https://alphacephei.com/vosk/models/vosk-model-small-ca-0.4.zip",
            "ar": "https://alphacephei.com/vosk/models/vosk-model-ar-mgb2-0.4.zip",
            "fa": "https://alphacephei.com/vosk/models/vosk-model-small-fa-0.5.zip",
            "tl": "https://alphacephei.com/vosk/models/vosk-model-tl-ph-generic-0.6.zip"
        }
        biglang2url = {
            "en": "https://alphacephei.com/vosk/models/vosk-model-en-us-aspire-0.2.zip",
            "en-in": "http://alphacephei.com/vosk/models/vosk-model-en-in-0.4.zip",
            "cn": "https://alphacephei.com/vosk/models/vosk-model-cn-0.1.zip",
            "ru": "https://alphacephei.com/vosk/models/vosk-model-ru-0.10.zip",
            "fr": "https://github.com/pguyot/zamia-speech/releases/download/20190930/kaldi-generic-fr-tdnn_f-r20191016.tar.xz",
            "de": "https://alphacephei.com/vosk/models/vosk-model-de-0.6.zip",
            "nl": "https://alphacephei.com/vosk/models/vosk-model-nl-spraakherkenning-0.6.zip",
            "fa": "https://alphacephei.com/vosk/models/vosk-model-fa-0.5.zip"

        }
        if not small:
            lang2url.update(biglang2url)
        lang = lang.lower()
        if lang in lang2url:
            return lang2url[lang]
        lang = lang.split("-")[0]
        return lang2url.get(lang)

    def execute(self, audio, language=None):
        # load a new model on the fly if needed
        lang = language or self.lang
        self.load_language(lang)

        # if limited vocabulary mode is enabled use that model instead
        if self.limited:
            engine = self.limited_voc_engines.get(lang) or self.engines[lang]
        else:
            engine = self.engines[lang]

        # transcribe
        engine.AcceptWaveform(audio.get_wav_data())
        res = engine.FinalResult()
        res = json.loads(res)
        return res["text"]

    def shutdown(self):
        for lang in set(self.engines.keys()) + \
                    set(self.limited_voc_engines.keys()):
            self.unload_language(lang)


class VoskKaldiStreamThread(StreamThread):
    def __init__(self, queue, lang, kaldi, verbose=True):
        super().__init__(queue, lang)
        self.kaldi = kaldi
        self.verbose = verbose
        self.previous_partial = ""
        self.running = True

    def handle_audio_stream(self, audio, language):
        if self.running:
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
        self.running = False
        if self.previous_partial:
            if self.verbose:
                LOG.info("Finalizing stream")
            self.text = self.kaldi.FinalResult()
            self.previous_partial = ""
        text = self.text
        self.text = ""
        return text


class VoskKaldiStreamingSTT(StreamingSTT, VoskKaldiSTT):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.verbose = self.config.get("verbose", False)

    def create_streaming_thread(self):
        self.queue = Queue()
        return VoskKaldiStreamThread(
            self.queue, self.lang, self.kaldi, self.verbose
        )
