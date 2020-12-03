## Description

Mycroft STT plugin for [Vosk](https://alphacephei.com/vosk/)

The "plugins" are pip install-able modules that provide new STT engines for mycroft

more info in the [docs](https://mycroft-ai.gitbook.io/docs/mycroft-technologies/mycroft-core/plugins)


## Install

`mycroft-pip install mycroft_stt_plugin_vosk`

You can download official models from [alphacephei](https://alphacephei.com/vosk/models)

Models for Iberian Languages can be found [here](https://github.com/JarbasIberianLanguageResources/iberian-vosk) 

## Configuration

You need to download a kaldi model, none is included in this package by default

```json
  "stt": {
    "module": "vosk_stt_plug",
    "vosk_stt_plug": {
        "model": "path/to/model/folder"
    }
  }
 
```

### Advanced configuration


```json
  "stt": {
    "module": "vosk_streaming_stt_plug",
    "vosk_streaming_stt_plug": {
        "model": "path/to/model/folder",
        "verbose": true
    },
    "vosk_stt_plug": {
        "model": "path/to/model/folder"
    }
  }
 
```


`vosk_stt_plug` - regular STT, transcription happens after recording finishes

`vosk_streaming_stt_plug` - streaming STT, transcription happens real time

`verbose` - print partial transcriptions