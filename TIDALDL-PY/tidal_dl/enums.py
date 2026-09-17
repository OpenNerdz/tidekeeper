#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   enums.py
@Time    :   2020/08/08
@Author  :   Yaronzz
@Version :   3.0
@Contact :   yaronhuang@foxmail.com
@Desc    :
'''
from enum import Enum


class AudioQuality(Enum):
    Normal = 0
    High = 1
    HiFi = 2
    Master = 3
    Max = 4
    Atmos = 5


AUDIO_QUALITY_ORDER = (
    AudioQuality.Atmos, AudioQuality.Max, AudioQuality.HiFi,
    AudioQuality.High, AudioQuality.Normal,
)


def audio_quality_fallbacks(quality):
    """Order current qualities without reintroducing retired MQA requests."""
    if quality == AudioQuality.Master:
        return [quality] + audio_quality_fallbacks(AudioQuality.HiFi)
    if quality not in AUDIO_QUALITY_ORDER:
        return [quality]
    return list(AUDIO_QUALITY_ORDER[AUDIO_QUALITY_ORDER.index(quality):])


def playback_quality_priority(qualities):
    """Migrate legacy Master to FLAC, preserving explicit fallback order."""
    qualities = list(qualities)
    priority = list(dict.fromkeys(
        AudioQuality.Max if item == AudioQuality.Master else item for item in qualities
    ))
    if qualities == [AudioQuality.Master]:
        # MQA replacements may only be CD quality. Keep this migration lossless.
        priority.append(AudioQuality.HiFi)
    return priority


class VideoQuality(Enum):
    P240 = 240
    P360 = 360
    P480 = 480
    P720 = 720
    P1080 = 1080


class Type(Enum):
    Album = 0
    Track = 1
    Video = 2
    Playlist = 3
    Artist = 4
    Mix = 5
    Null = 6
