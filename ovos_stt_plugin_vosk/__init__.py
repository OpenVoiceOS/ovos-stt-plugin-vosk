import json
import os
import shutil
import tarfile
import zipfile
from os import makedirs
from os.path import join, isdir, exists
from queue import Queue
from tempfile import mkstemp
from time import sleep

import requests
from ovos_plugin_manager.templates.stt import STT, StreamThread, StreamingSTT
from ovos_utils import classproperty
from ovos_utils.log import LOG
from ovos_utils.network_utils import is_connected
from ovos_utils.xdg_utils import xdg_data_home
from speech_recognition import AudioData
from vosk import Model as KaldiModel, KaldiRecognizer

_lang2url = {
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
    "it": "https://alphacephei.com/vosk/models/vosk-model-small-it-0.22.zip",
    "nl": "https://alphacephei.com/vosk/models/vosk-model-nl-spraakherkenning-0.6-lgraph.zip",
    "ca": "https://alphacephei.com/vosk/models/vosk-model-small-ca-0.4.zip",
    "ar": "https://alphacephei.com/vosk/models/vosk-model-ar-mgb2-0.4.zip",
    "fa": "https://alphacephei.com/vosk/models/vosk-model-small-fa-0.5.zip",
    "tl": "https://alphacephei.com/vosk/models/vosk-model-tl-ph-generic-0.6.zip"
}
_biglang2url = {
    "en": "https://alphacephei.com/vosk/models/vosk-model-en-us-aspire-0.2.zip",
    "en-in": "http://alphacephei.com/vosk/models/vosk-model-en-in-0.4.zip",
    "cn": "https://alphacephei.com/vosk/models/vosk-model-cn-0.1.zip",
    "ru": "https://alphacephei.com/vosk/models/vosk-model-ru-0.10.zip",
    "fr": "https://github.com/pguyot/zamia-speech/releases/download/20190930/kaldi-generic-fr-tdnn_f-r20191016.tar.xz",
    "de": "https://alphacephei.com/vosk/models/vosk-model-de-0.6.zip",
    "nl": "https://alphacephei.com/vosk/models/vosk-model-nl-spraakherkenning-0.6.zip",
    "fa": "https://alphacephei.com/vosk/models/vosk-model-fa-0.5.zip",
    "it": "https://alphacephei.com/vosk/models/vosk-model-it-0.22.zip"

}

VoskSTTConfig = {
    lang: [{"model": url,
            "lang": lang,
            "meta": {
                "priority": 40,
                "display_name": url.split("/")[-1].replace(".zip", "") + " (Small)",
                "offline": True}
            }]
    for lang, url in _lang2url.items()
}
for lang, url in _biglang2url.items():
    VoskSTTConfig[lang].append({"model": url,
                                "lang": lang,
                                "meta": {
                                    "priority": 70,
                                    "display_name": url.split("/")[-1].replace(".zip", "") + " (Large)",
                                    "offline": True}
                                })


class ModelContainer:
    def __init__(self):
        self.engines = {}
        self.models = {}

    def get_engine(self, lang):
        lang = lang.split("-")[0].lower()
        self.load_language(lang)
        return self.engines[lang]

    def get_partial_transcription(self, lang):
        engine = self.get_engine(lang)
        res = engine.PartialResult()
        return json.loads(res)["partial"]

    def get_final_transcription(self, lang):
        engine = self.get_engine(lang)
        res = engine.FinalResult()
        return json.loads(res)["text"]

    def process_audio(self, audio, lang):
        engine = self.get_engine(lang)
        if isinstance(audio, AudioData):
            audio = audio.get_wav_data()
        return engine.AcceptWaveform(audio)

    def enable_limited_vocabulary(self, words, lang):
        """
        enable limited vocabulary mode
        will only consider pre defined .voc files
        """
        model_path = self.models[lang]
        self.engines[lang] = KaldiRecognizer(
            KaldiModel(model_path), 16000, json.dumps(words))

    def enable_full_vocabulary(self, lang=None):
        """ enable default transcription mode """
        model_path = self.models[lang]
        self.engines[lang] = KaldiRecognizer(
            KaldiModel(model_path), 16000)

    def load_model(self, model_path, lang):
        lang = lang.split("-")[0].lower()
        self.models[lang] = model_path
        if model_path:
            self.engines[lang] = KaldiRecognizer(KaldiModel(model_path), 16000)
        else:
            raise FileNotFoundError

    def load_language(self, lang):
        lang = lang.split("-")[0].lower()
        if lang in self.engines:
            return
        model_path = self.download_language(lang)
        self.load_model(model_path, lang)

    def unload_language(self, lang):
        if lang in self.engines:
            del self.engines[lang]
            self.engines.pop(lang)

    @staticmethod
    def download_language(lang):
        lang = lang.split("-")[0].lower()
        model_path = ModelContainer.lang2modelurl(lang)
        if model_path and model_path.startswith("http"):
            model_path = ModelContainer.download_model(model_path)
        return model_path

    @staticmethod
    def download_model(url):
        folder = join(xdg_data_home(), 'vosk')
        name = url.split("/")[-1].rsplit(".", 1)[0]
        model_path = join(folder, name)
        if not exists(model_path):
            while not is_connected():
                LOG.info("Waiting for internet in order to download vosk language model")
                # waiting for wifi setup most likely
                sleep(10)
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
        if not small:
            _lang2url.update(_biglang2url)
        lang = lang.lower()
        if lang in _lang2url:
            return _lang2url[lang]
        lang = lang.split("-")[0]
        return _lang2url.get(lang)


class VoskKaldiSTT(STT):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # model_folder for backwards compat
        model_path = self.config.get("model_folder") or self.config.get("model")

        self.model = ModelContainer()
        if model_path:
            if model_path.startswith("http"):
                model_path = ModelContainer.download_model(model_path)
            self.model.load_model(model_path, self.lang)
        else:
            self.model.load_language(self.lang)
        self.verbose = True

    @classproperty
    def available_languages(cls) -> set:
        """Return languages supported by this TTS implementation in this state
        This property should be overridden by the derived class to advertise
        what languages that engine supports.
        Returns:
            set: supported languages
        """
        return set(VoskSTTConfig.keys())

    def load_language(self, lang):
        self.model.load_language(lang)

    def unload_language(self, lang):
        self.model.unload_language(lang)

    def enable_limited_vocabulary(self, words, lang):
        self.model.enable_limited_vocabulary(words, lang or self.lang)

    def enable_full_vocabulary(self, lang=None):
        self.model.enable_full_vocabulary(lang or self.lang)

    def execute(self, audio, language=None):
        lang = language or self.lang
        self.model.process_audio(audio, lang)
        return self.model.get_final_transcription(lang)


class VoskKaldiStreamThread(StreamThread):
    def __init__(self, queue, lang, model, verbose=True):
        super().__init__(queue, lang)
        self.model = model
        self.verbose = verbose
        self.previous_partial = ""
        self.running = True

    def handle_audio_stream(self, audio, language):
        lang = language or self.language
        if self.running:
            for a in audio:
                self.model.process_audio(a, lang)
                self.text = self.model.get_partial_transcription(lang)
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
            self.text = self.model.get_final_transcription(self.language)
            self.previous_partial = ""
        text = str(self.text)
        self.text = ""
        return text


class VoskKaldiStreamingSTT(StreamingSTT, VoskKaldiSTT):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.verbose = self.config.get("verbose", False)

    def create_streaming_thread(self):
        self.queue = Queue()
        return VoskKaldiStreamThread(
            self.queue, self.lang, self.model, self.verbose
        )

    @classproperty
    def available_languages(cls) -> set:
        """Return languages supported by this TTS implementation in this state
        This property should be overridden by the derived class to advertise
        what languages that engine supports.
        Returns:
            set: supported languages
        """
        return set(VoskSTTConfig.keys())


def download(url, file=None, session=None):
    """
    Pass file as a filename, open file object, or None to return the request bytes

    Args:
        url (str): URL of file to download
        file (Union[str, io, None]): One of the following:
             - Filename of output file
             - File opened in binary write mode
             - None: Return raw bytes instead

    Returns:
        Union[bytes, None]: Bytes of file if file is None
    """

    if isinstance(file, str):
        file = open(file, 'wb')
    try:
        if session:
            content = session.get(url).content
        else:
            content = requests.get(url).content
        if file:
            file.write(content)
        else:
            return content
    finally:
        if file:
            file.close()


def download_extract_tar(tar_url, folder, tar_filename='',
                         skill_folder_name=None, session=None):
    """
    Download and extract the tar at the url to the given folder

    Args:
        tar_url (str): URL of tar file to download
        folder (str): Location of parent directory to extract to. Doesn't have to exist
        tar_filename (str): Location to download tar. Default is to a temp file
        skill_folder_name (str): rename extracted skill folder to this
    """
    try:
        makedirs(folder)
    except OSError:
        if not isdir(folder):
            raise
    if not tar_filename:
        fd, tar_filename = mkstemp('.tar.gz')
        download(tar_url, os.fdopen(fd, 'wb'), session=session)
    else:
        download(tar_url, tar_filename, session=session)

    with tarfile.open(tar_filename) as tar:
        tar.extractall(path=folder)

    if skill_folder_name:
        with tarfile.open(tar_filename) as tar:
            for p in tar.getnames():
                original_folder = p.split("/")[0]
                break
        original_folder = join(folder, original_folder)
        final_folder = join(folder, skill_folder_name)
        shutil.move(original_folder, final_folder)


def download_extract_zip(zip_url, folder, zip_filename="",
                         skill_folder_name=None, session=None):
    """
   Download and extract the zip at the url to the given folder

   Args:
       zip_url (str): URL of zip file to download
       folder (str): Location of parent directory to extract to. Doesn't have to exist
       zip_filename (str): Location to download zip. Default is to a temp file
       skill_folder_name (str): rename extracted skill folder to this
   """
    try:
        makedirs(folder)
    except OSError:
        if not isdir(folder):
            raise
    if not zip_filename:
        fd, zip_filename = mkstemp('.tar.gz')
        download(zip_url, os.fdopen(fd, 'wb'), session=session)
    else:
        download(zip_url, zip_filename, session=session)

    with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
        zip_ref.extractall(folder)

    if skill_folder_name:
        with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
            for p in zip_ref.namelist():
                original_folder = p.split("/")[0]
                break

        original_folder = join(folder, original_folder)
        final_folder = join(folder, skill_folder_name)
        shutil.move(original_folder, final_folder)
