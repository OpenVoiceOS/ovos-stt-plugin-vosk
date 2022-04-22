FROM debian:buster-slim

RUN apt-get update && \
  apt-get install -y git python3 python3-dev python3-pip curl build-essential

# taken from https://github.com/alphacep/vosk-server/blob/master/docker
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        bzip2 \
        unzip \
        xz-utils \
        g++ \
        make \
        cmake \
        python3-websockets \
        python3-setuptools \
        python3-wheel \
        python3-cffi \
        zlib1g-dev \
        automake \
        autoconf \
        libtool \
        pkg-config \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN \
    git clone -b vosk --single-branch https://github.com/alphacep/kaldi /opt/kaldi \
    && cd /opt/kaldi/tools \
    && sed -i 's:status=0:exit 0:g' extras/check_dependencies.sh \
    && sed -i 's:--enable-ngram-fsts:--enable-ngram-fsts --disable-bin:g' Makefile \
    && make -j $(nproc) openfst cub \
    && if [ "x$KALDI_MKL" != "x1" ] ; then \
          extras/install_openblas_clapack.sh; \
       else \
          extras/install_mkl.sh; \
       fi \
    \
    && cd /opt/kaldi/src \
    && if [ "x$KALDI_MKL" != "x1" ] ; then \
          ./configure --mathlib=OPENBLAS_CLAPACK --shared; \
       else \
          ./configure --mathlib=MKL --shared; \
       fi \
    && sed -i 's:-msse -msse2:-msse -msse2:g' kaldi.mk \
    && sed -i 's: -O1 : -O3 :g' kaldi.mk \
    && make -j $(nproc) online2 lm rnnlm \
    \
    && git clone https://github.com/alphacep/vosk-api /opt/vosk-api \
    && cd /opt/vosk-api/src \
    && KALDI_MKL=$KALDI_MKL KALDI_ROOT=/opt/kaldi make -j $(nproc) \
    && cd /opt/vosk-api/python \
    && python3 ./setup.py install

RUN pip3 install ovos-stt-http-server==0.0.2a1

COPY . /tmp/ovos-stt-plugin-vosk
RUN pip3 install /tmp/ovos-stt-plugin-vosk

ENTRYPOINT ovos-stt-server --engine ovos-stt-plugin-vosk