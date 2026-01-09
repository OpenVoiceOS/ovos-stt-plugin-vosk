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
from ovos_utils.network_utils import is_connected_http
from ovos_utils.xdg_utils import xdg_data_home
from ovos_plugin_manager.utils.audio import AudioData, AudioFile
from typing import Optional
from vosk import Model as KaldiModel, KaldiRecognizer

_BASE_URL = "https://alphacephei.com/vosk/models"
LANG2MODEL = {
    "en": "vosk-model-small-en-us-0.15.zip",
    "en-in": "vosk-model-small-en-in-0.4.zip",
    "cn": "vosk-model-small-cn-0.3.zip",
    "ru": "vosk-model-small-ru-0.15.zip",
    "fr": "vosk-model-small-fr-pguyot-0.3.zip",
    "de": "vosk-model-small-de-0.15.zip",
    "es": "vosk-model-small-es-0.3.zip",
    "pt": "vosk-model-small-pt-0.3.zip",
    "gr": "vosk-model-el-gr-0.7.zip",
    "tr": "vosk-model-small-tr-0.3.zip",
    "vn": "vosk-model-small-vn-0.3.zip",
    "it": "vosk-model-small-it-0.22.zip",
    "nl": "vosk-model-nl-spraakherkenning-0.6-lgraph.zip",
    "ca": "vosk-model-small-ca-0.4.zip",
    "ar": "vosk-model-ar-mgb2-0.4.zip",
    "fa": "vosk-model-small-fa-0.5.zip",
    "tl": "vosk-model-tl-ph-generic-0.6.zip"
}
LANG2BIGMODEL = {
    "en": "vosk-model-en-us-aspire-0.2.zip",
    "en-in": "vosk-model-en-in-0.4.zip",
    "cn": "vosk-model-cn-0.1.zip",
    "ru": "vosk-model-ru-0.10.zip",
    "fr": "kaldi-generic-fr-tdnn_f-r20191016.tar.xz",
    "de": "vosk-model-de-0.6.zip",
    "nl": "vosk-model-nl-spraakherkenning-0.6.zip",
    "fa": "vosk-model-fa-0.5.zip",
    "it": "vosk-model-it-0.22.zip"

}
MODEL2URL = {
    m: f"{_BASE_URL}/{m}"
    for m in list(LANG2MODEL.values()) + list(LANG2BIGMODEL.values())
}
MODEL2URL["kaldi-generic-fr-tdnn_f-r20191016.tar.xz"] = "https://github.com/pguyot/zamia-speech/releases/download/20190930/kaldi-generic-fr-tdnn_f-r20191016.tar.xz"


class ModelContainer:
    def __init__(self, sample_rate: int = 16000):
        """
        Initialize a ModelContainer managing Vosk/Kaldi models and recognizers.

        Creates empty mappings for loaded engine instances and model paths, and sets the audio sample rate used when converting AudioData and when constructing recognizers.

        Parameters:
            sample_rate (int): Audio sample rate in hertz used for audio conversion and recognizer initialization. Default is 16000.
        """
        self.engines = {}
        self.models = {}
        self.sample_rate = sample_rate

    def get_engine(self, lang):
        """
        Get the Kaldi recognizer for the specified language, ensuring the language model is loaded.

        Parameters:
            lang (str): Language code (region suffix allowed, e.g. "en-US"); the region is stripped and only the base language is used.

        Returns:
            KaldiRecognizer: The Kaldi engine configured for the normalized language.

        Raises:
            ValueError: If the language is not supported or its model cannot be resolved/loaded.
        """
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
        """
        Feed a chunk of audio to the recognizer for the specified language.

        If `audio` is an AudioData instance it is converted to WAV bytes using the container's configured sample rate before being sent to the recognizer. This updates the recognizer's internal state (partial/final results) for the given language.

        Parameters:
            audio: AudioData or bytes-like object
                Audio to process. If an AudioData object is provided, it will be converted to WAV at self.sample_rate.
            lang: str
                Language code or model key identifying which recognizer/engine to use.

        Returns:
            bool: `True` if processing this audio produced a final recognition result, `False` otherwise.
        """
        engine = self.get_engine(lang)
        if isinstance(audio, AudioData):
            audio = audio.get_wav_data(self.sample_rate)
        return engine.AcceptWaveform(audio)

    def enable_limited_vocabulary(self, words, lang):
        """
        Enable limited-vocabulary recognition for a given language.

        Sets the recognizer for the specified language to accept only the provided vocabulary, using the configured model and sample rate.

        Parameters:
            words (Sequence[str] or dict): The vocabulary or grammar to restrict recognition to. Can be a list of words or a JSON-serializable grammar structure.
            lang (str): Language code identifying which loaded model/recognizer to replace.
        """
        model_path = self.models[lang]
        self.engines[lang] = KaldiRecognizer(KaldiModel(model_path), self.sample_rate, json.dumps(words))

    def enable_full_vocabulary(self, lang=None):
        """
        Enable full-vocabulary speech recognition for the specified language.

        Initializes and stores a Kaldi recognizer for the given language using the container's configured sample rate.

        Parameters:
            lang (str): Language code whose model has been loaded and should be used to create the recognizer.
        """
        model_path = self.models[lang]
        self.engines[lang] = KaldiRecognizer(KaldiModel(model_path), self.sample_rate)

    def load_model(self, model_path, lang):
        """
        Load a Kaldi model for the given language and initialize its recognizer.

        The language code is normalized to its base (e.g., "en-US" -> "en") and stored with the model path.
        If a valid model_path is provided, a KaldiRecognizer is created for that language using the instance's sample_rate.
        Raises FileNotFoundError if model_path is not provided or falsy.

        Parameters:
            model_path (str): Filesystem path to the Kaldi model directory.
            lang (str): Language code; only the primary subtag (before '-') is used.
        """
        lang = lang.split("-")[0].lower()
        self.models[lang] = model_path
        if model_path:
            self.engines[lang] = KaldiRecognizer(KaldiModel(model_path), self.sample_rate)
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
        """
        Ensure a Vosk model is present locally by downloading and extracting it to the user's XDG data directory if it does not already exist.

        If the model archive is not present, this function waits for HTTP connectivity, downloads the archive (supports .zip and tar formats), and extracts it to XDG_DATA_HOME/vosk/<model_name>.

        Returns:
            model_path (str): Filesystem path to the extracted local model directory under XDG_DATA_HOME/vosk.
        """
        folder = join(xdg_data_home(), 'vosk')
        name = url.split("/")[-1].rsplit(".", 1)[0]
        model_path = join(folder, name)
        if not exists(model_path):
            while not is_connected_http():
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
    def lang2modelurl(lang: str):
        """
        Resolve a language code to the corresponding Vosk model download URL.

        Parameters:
        	lang (str): Language code (e.g., "en" or "en-US"); regional variants are normalized to their base language.

        Returns:
        	model_url (str): The full download URL for the model corresponding to the resolved language.

        Raises:
        	ValueError: If the language is not supported.
        """
        lang_norm = lang.lower()
        lang_norm = lang_norm if lang_norm in LANG2MODEL else lang_norm.split("-")[0]
        model_id = LANG2MODEL.get(lang_norm)
        if model_id:
            return MODEL2URL[model_id]
        raise ValueError(f"unsupported language: {lang}")


class VoskKaldiSTT(STT):
    def __init__(self, *args, **kwargs):
        """
        Initialize the Vosk STT instance and prepare its model container.

        Creates a ModelContainer, determines which model to use from configuration (supports legacy `model_folder` and `model` keys), and ensures a recognizer is loaded. If a model id is configured it is resolved to a URL when recognized as a known identifier, downloaded when it is an HTTP URL, and then loaded from the local path. If no model is configured, loads the default model for the instance language. Sets the instance to verbose mode.

        Raises:
            ValueError: If a configured model identifier/path cannot be resolved to an existing local model.
        """
        super().__init__(*args, **kwargs)
        # model_folder for backwards compat
        model_id = self.config.get("model_folder") or self.config.get("model")
        self.model = ModelContainer()
        if model_id:
            if model_id in MODEL2URL:
                LOG.info(f"Requested model_id: {model_id}")
                model_id = MODEL2URL[model_id]

            if model_id.startswith("http"):
                LOG.debug(f"Requested model_url: {model_id}")
                model_id = ModelContainer.download_model(model_id)

            if os.path.exists(model_id):
                LOG.info(f"Loading local model: {model_id}")
                self.model.load_model(model_id, self.lang)
            else:
                raise ValueError(f"Invalid model: {model_id}")
        else:
            LOG.info(f"Loading default model for '{self.lang}'")
            self.model.load_language(self.lang)
        self.verbose = True

    @classproperty
    def available_languages(cls) -> set:
        """
        Return the set of language codes supported by this STT implementation.

        Returns:
            set: Supported language codes (the keys from LANG2MODEL).
        """
        return set(LANG2MODEL.keys())

    def load_language(self, lang):
        """
        Ensure the speech recognition model for the specified language is downloaded and initialized.

        Parameters:
            lang (str): Language identifier or code (e.g., "en", "fr") to load.
        """
        self.model.load_language(lang)

    def unload_language(self, lang):
        self.model.unload_language(lang)

    def enable_limited_vocabulary(self, words, lang):
        self.model.enable_limited_vocabulary(words, lang or self.lang)

    def enable_full_vocabulary(self, lang=None):
        """
        Enable the full vocabulary recognizer for the given language or the instance's current language.

        Parameters:
            lang (str | None): Optional language code to enable; if omitted, uses the instance's configured language.
        """
        self.model.enable_full_vocabulary(lang or self.lang)

    def execute(self, audio: AudioData, language: Optional[str] = None):
        """
        Transcribes the provided audio using the configured model and language.

        Parameters:
            audio (AudioData): Audio input to be processed.
            language (Optional[str]): Language code to use for transcription; if omitted, the instance's current language is used.

        Returns:
            transcription (str): Final recognized text for the processed audio.
        """
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
    Download a ZIP archive from a URL and extract its contents into a target folder.

    If zip_filename is provided, download into that path; otherwise a temporary file is used.
    The target folder is created if it does not exist. If skill_folder_name is set,
    the function renames the extracted archive's top-level directory to that name.
    Parameters:
        zip_url (str): URL of the ZIP file to download.
        folder (str): Directory to extract archive contents into; will be created if missing.
        zip_filename (str): Path to save the downloaded ZIP. If empty, a temporary file is used.
        skill_folder_name (str): If provided, rename the extracted top-level folder to this name.
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


VoskSTTConfig = {
    lang: [{"model": model_id,
            "lang": lang,
            "meta": {
                "priority": 40,
                "display_name": model_id.replace(".zip", ""),
                "offline": True}
            }]
    for lang, model_id in LANG2MODEL.items()
}
for lang, model_id in LANG2BIGMODEL.items():
    VoskSTTConfig[lang].append({"model": model_id,
                                "lang": lang,
                                "meta": {
                                    "priority": 70,
                                    "display_name": model_id.replace(".zip", ""),
                                    "offline": True}
                                })

if __name__ == "__main__":
    b = VoskKaldiSTT({"lang": "en", "model": "vosk-model-small-en-us-0.15.zip"})

    eu = "/home/miro/PycharmProjects/ovos-stt-plugin-vosk/jfk.wav"
    with AudioFile(eu) as source:
        audio = source.read()

    a = b.execute(audio, language="en")
    print(a)