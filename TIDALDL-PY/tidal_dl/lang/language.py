#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   language.py
@Time    :   2020/08/19
@Author  :   Yaronzz
@Version :   1.0
@Contact :   yaronhuang@foxmail.com
@Desc    :
'''

from .arabic import LangArabic
from .chinese import LangChinese
from .croatian import LangCroatian
from .czech import LangCzech
from .danish import LangDanish
from .dutch import LangDutch
from .english import LangEnglish
from .filipino import LangFilipino
from .french import LangFrench
from .german import LangGerman
from .hungarian import LangHungarian
from .italian import LangItalian
from .norwegian import LangNorwegian
from .polish import LangPolish
from .portuguese import LangPortuguese
from .russian import LangRussian
from .spanish import LangSpanish
from .turkish import LangTurkish
from .ukrainian import LangUkrainian
from .vietnamese import LangVietnamese
from .korean import LangKorean
from .japanese import LangJapanese

_ALL_LANGUAGE_ = [
    ['English', LangEnglish()],
    ['中文', LangChinese()],
    ['Turkish', LangTurkish()],
    ['Italian', LangItalian()],
    ['Czech', LangCzech()],
    ['Arabic', LangArabic()],
    ['Russian', LangRussian()],
    ['Filipino', LangFilipino()],
    ['Croatian', LangCroatian()],
    ['Spanish', LangSpanish()],
    ['Portuguese', LangPortuguese()],
    ['Ukrainian', LangUkrainian()],
    ['Vietnamese', LangVietnamese()],
    ['French', LangFrench()],
    ['German', LangGerman()],
    ['Danish', LangDanish()],
    ['Hungarian', LangHungarian()],
    ['Korean', LangKorean()],
    ['Japanese', LangJapanese()],
    ['Dutch', LangDutch()],
    ['Polish', LangPolish()],
    ['Norwegian', LangNorwegian()],
]

class Language(object):
    def __init__(self) -> None:
        self.select = LangEnglish()

    def __toInt__(self, str):
        try:
            return int(str)
        except (TypeError, ValueError):
            return 0

    def setLang(self, index):
        index = self.__toInt__(index)
        if index >= 0 and index < len(_ALL_LANGUAGE_):
            self.select = _ALL_LANGUAGE_[index][1]
        else:
            self.select = LangEnglish()

    def getLangName(self, index):
        index = self.__toInt__(index)
        if index >= 0 and index < len(_ALL_LANGUAGE_):
            return _ALL_LANGUAGE_[index][0]
        return ""

    def getLangChoicePrint(self):
        array = []
        index = 0
        while True:
            name = self.getLangName(index)
            if name == "":
                break
            array.append('\'' + str(index) + '\'-' + name)
            index += 1
        return ','.join(array)


LANG = Language()
