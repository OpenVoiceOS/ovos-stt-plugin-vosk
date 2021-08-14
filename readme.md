## Description

Mycroft STT plugin for [Vosk](https://alphacephei.com/vosk/)

## Install

`pip install ovos-stt-plugin-vosk`

You can download official models from [alphacephei](https://alphacephei.com/vosk/models)


## Configuration

You need to download a kaldi model or provide a direct download url

```json
  "stt": {
    "module": "ovos-stt-plugin-vosk",
    "ovos-stt-plugin-vosk": {
        "model": "path/to/model/folder"
    }
  }
 
```

### Advanced configuration


```json
  "stt": {
    "module": "ovos-stt-plugin-vosk-streaming",
    "ovos-stt-plugin-vosk-streaming": {
        "model": "http://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "verbose": true
    },
    "ovos-stt-plugin-vosk": {
        "model": "http://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    }
  }
 
```


`ovos-stt-plugin-vosk` - regular STT, transcription happens after recording finishes

`ovos-stt-plugin-vosk-streaming` - streaming STT, transcription happens real time

`verbose` - print partial transcriptions

`model` - full path or direct download url for model

`lang` - optional, if `model` not provided will download default small model (if it exists)