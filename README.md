## Description

This plugin adds [Vosk](https://alphacephei.com/vosk/) speech-to-text support to OpenVoiceOS. It transcribes audio with a local Kaldi model, either after recording finishes or in real time as you speak.

## Install

`pip install ovos-stt-plugin-vosk`

Get official models from [alphacephei](https://alphacephei.com/vosk/models).

## Configuration

Give the plugin a Kaldi model. Point `model` at a local folder or a direct download URL.

```json
  "stt": {
    "module": "ovos-stt-plugin-vosk",
    "ovos-stt-plugin-vosk": {
        "model": "/path/to/unzipped/model/folder"
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

`ovos-stt-plugin-vosk` runs regular STT. Transcription happens after recording finishes.

`ovos-stt-plugin-vosk-streaming` runs streaming STT. Transcription happens in real time.

`verbose` prints partial transcriptions.

`model` sets the full path or direct download URL for the model.

`lang` is optional. If you do not set `model`, the plugin downloads a default small model for this language, if one exists.

## Docker

Use this plugin together with [ovos-stt-http-server](https://github.com/OpenVoiceOS/ovos-stt-http-server).

```bash
docker run -p 8080:8080 ghcr.io/openvoiceos/vosk-stt-http-server:master
```
