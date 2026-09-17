#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File    :  apiKey.py
@Date    :  2021/11/30
@Author  :  Yaronzz
@Version :  3.0
@Contact :  yaronhuang@foxmail.com
@Desc    :
"""
# IDs are persisted in profiles. Never renumber surviving clients when removing
# retired entries: doing so silently switches clients and invalidates logins.
__API_KEYS__ = {
    1: {
        "platform": "Fire TV (legacy)",
        "formats": "Legacy alternative; playback availability varies",
        "clientId": "7m7Ap0JC9j1cOM3n",
        "clientSecret": "vRAdA108tlvkJpTsGZS8rGZ7xTlbJ0qaZ2K9saEzsgY=",
        "from": "Dniel97 (https://github.com/Dniel97/RedSea/blob/4ba02b88cee33aeb735725cb854be6c66ff372d4/config/settings.example.py#L68)",
    },
    4: {
        "platform": "Tidal TV",
        "formats": "Normal/High/HiFi",
        "clientId": "4N3n6Q1x95LL5K7p",
        "clientSecret": "oKOXfJW371cX6xaZ0PyhgGNBdNLlBZd4AKKYougMjik=",
        "from": "np3ir/tiddl-elvigilante (TV device flow)",
    },
}
DEFAULT_API_KEY_INDEX = 4
__ERROR_KEY__ = {
    'platform': 'None',
    'formats': '',
    'clientId': '',
    'clientSecret': '',
}


def getItem(index: int):
    return __API_KEYS__.get(index, __ERROR_KEY__).copy()


def isItemValid(index: int):
    return index in __API_KEYS__


def getItems():
    """Return selectable clients with stable IDs, not their list positions."""
    return [dict(item, index=index) for index, item in __API_KEYS__.items()]


def getLimitIndexs():
    return [str(index) for index in __API_KEYS__]


def getDefaultIndex():
    return DEFAULT_API_KEY_INDEX
