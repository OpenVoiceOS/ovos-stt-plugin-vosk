#!/usr/bin/env python3
from setuptools import setup

PLUGIN_ENTRY_POINT = (
    'ovos-stt-plugin-vosk = ovos_stt_plugin_vosk:VoskKaldiSTT',
    'ovos-stt-plugin-vosk-streaming = ovos_stt_plugin_vosk:VoskKaldiStreamingSTT'
)

setup(
    name='ovos-stt-plugin-vosk',
    version='0.1.1',
    description='A vosk stt plugin for mycroft',
    url='https://github.com/OpenVoiceOS/ovos-stt-plugin-vosk',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    packages=['ovos_stt_plugin_vosk'],
    install_requires=["numpy",
                      "vosk",
                      "ovos-plugin-manager>=0.0.1a9",
                      "ovos_skill_installer"],
    zip_safe=True,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Text Processing :: Linguistic',
        'License :: OSI Approved :: Apache Software License',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.0',
        'Programming Language :: Python :: 3.1',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    keywords='mycroft ovos plugin stt',
    entry_points={'mycroft.plugin.stt': PLUGIN_ENTRY_POINT}
)
