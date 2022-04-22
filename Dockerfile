FROM alphacep/kaldi-vosk-server

RUN pip3 install ovos-stt-http-server==0.0.2a1

COPY . /tmp/ovos-stt-plugin-vosk
RUN pip3 install /tmp/ovos-stt-plugin-vosk

ENTRYPOINT ovos-stt-server --engine ovos-stt-plugin-vosk