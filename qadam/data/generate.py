# -*- coding: utf-8 -*-
"""Генерация синтетического корпуса ответов по компетенции «Лидерские способности».

Зачем синтетика: обезличенные реальные оценки заказчик открывает только на этапе
внедрения. До тех пор корпус порождается из опубликованной
рубрики BARS.

ГЛАВНОЕ ПРАВИЛО ГЕНЕРАЦИИ:
в порождающий промпт передаются ТОЛЬКО дословные формулировки индикаторов нужного
уровня. Слова «слабый», «сильный», «хороший кандидат» в промпт не попадают — иначе
метка станет пересказом суждения модели, а не свойством текста. Для LLM-бэкенда это
проверяется автоматически (``assert_no_judgment_words``), для шаблонного бэкенда
обеспечено конструкцией: содержательные блоки привязаны к id индикаторов.

Два бэкенда:

* ``template`` — оффлайновый, детерминированный при фиксированном seed. Собирает
  ответ из содержательных блоков, привязанных к индикаторам уровня, и отдельно
  накладывает поверхностный стиль. Разделение «содержание / обёртка» здесь
  архитектурное: именно оно даёт корректные «шумовые» примеры и контрфактические
  пары, где факты сохраняются дословно.
* ``llm`` — Anthropic API. Нужен ANTHROPIC_API_KEY.

Запуск:
    python -m qadam.data.generate                     # весь корпус, шаблонный бэкенд
    python -m qadam.data.generate --backend llm
    python -m qadam.data.generate --blind-sample 90   # файл для слепой ручной разметки
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Literal

from qadam.data.rubric import (
    ATOLA_ORDER,
    LEVELS,
    AtolaElement,
    Level,
    indicator_texts,
)

SEED = 20260910

DATA_DIR = Path(__file__).resolve().parent
CORPUS_DIR = DATA_DIR / "corpus"
COUNTERFACTUAL_DIR = DATA_DIR / "counterfactual"

CORPUS_FILE = CORPUS_DIR / "leadership.jsonl"
CORPUS_META_FILE = CORPUS_DIR / "meta.json"
PAIRS_FILE = COUNTERFACTUAL_DIR / "leadership_pairs.jsonl"
BLIND_FILE = CORPUS_DIR / "blind_sample.jsonl"

Lang = Literal["ru", "kk", "mixed"]
Style = Literal["colloquial", "bureaucratic", "polished", "errors"]
LengthGrade = Literal["short", "medium", "long"]

LANGS: tuple[Lang, ...] = ("ru", "kk", "mixed")
STYLES: tuple[Style, ...] = ("colloquial", "bureaucratic", "polished", "errors")
LENGTHS: tuple[LengthGrade, ...] = ("short", "medium", "long")
SETTLEMENTS = ("city", "village")
SCHOOL_TYPES = ("strong", "ordinary")
GENDERS = ("m", "f")

#: Дополнительный «сегмент» сверх пяти элементов ATOLA: работа с конфликтом.
#: Индикатор lead.strong.3 «распределяет задачи, поддерживает, решает конфликты».
Segment = Literal["action", "thinking", "conflict", "outcome", "learnings", "application"]
SEGMENT_ORDER: tuple[Segment, ...] = (
    "action",
    "thinking",
    "conflict",
    "outcome",
    "learnings",
    "application",
)


# --------------------------------------------------------------------------- #
# Домены историй. Факты одинаковы для всех уровней — различается то, насколько
# конкретно кандидат их излагает. Фоновых признаков (село/город, школа) здесь
# нет намеренно: они задаются отдельно и только в одном предложении, чтобы
# контрфактическая пара отличалась ровно этим предложением.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Domain:
    key: str
    topic_nom: str
    topic_acc: str
    vague: str
    role: str
    team: str
    problem: str
    timeframe: str
    metric: str          # шаблон с {before} и {after}
    soft: str            # тот же результат без чисел
    conflict: str
    mistake: str
    lesson: str
    application: str
    before: int
    after: int
    # казахские формы
    topic_nom_kk: str
    topic_acc_kk: str
    vague_kk: str
    role_kk: str
    team_kk: str
    problem_kk: str
    timeframe_kk: str
    metric_kk: str
    soft_kk: str
    conflict_kk: str
    mistake_kk: str
    lesson_kk: str
    application_kk: str


DOMAINS: tuple[Domain, ...] = (
    Domain(
        key="school",
        topic_nom="дебатный клуб",
        topic_acc="дебатный клуб",
        vague="общественной работе в школе",
        role="капитаном команды",
        team="семь одноклассников",
        problem="в школе никто не решался выступать перед залом",
        timeframe="за полгода",
        metric="участников клуба стало {after} вместо {before}",
        soft="на занятия стало ходить больше ребят",
        conflict="двое участников поссорились из-за того, кто выступает первым",
        mistake="первый турнир мы провалили, потому что я готовил речи за всех сам",
        lesson="что задачи надо раздавать сразу, а не тянуть всё на себе",
        application="через год, когда я собирал команду на школьную конференцию, я с первого дня расписал, кто за что отвечает",
        before=5,
        after=24,
        topic_nom_kk="дебат клубы",
        topic_acc_kk="дебат клубын",
        vague_kk="мектептегі қоғамдық жұмысқа",
        role_kk="команда капитаны",
        team_kk="жеті сыныптасымды",
        problem_kk="мектепте ешкім жиналыс алдында сөйлеуге батылы бармайтын",
        timeframe_kk="жарты жыл",
        metric_kk="клуб қатысушысы {before}-тен {after}-ке дейін өсті",
        soft_kk="сабаққа көбірек бала келе бастады",
        conflict_kk="екі қатысушы кім бірінші сөйлейтіні үшін ұрысып қалды",
        mistake_kk="бірінші турнирде жеңілдік, себебі сөздерді бәріне өзім жазып бердім",
        lesson_kk="тапсырманы бірден бөліп беру керек екенін",
        application_kk="бір жылдан кейін мектеп конференциясына топ жинағанда, бірінші күннен бастап кім не істейтінін жазып қойдым",
    ),
    Domain(
        key="family",
        topic_nom="график подготовки для младших",
        topic_acc="график подготовки для младших",
        vague="домашних делах",
        role="ответственным за учёбу младших",
        team="двух младших сестёр",
        problem="мама уехала на вахту и младшие перестали делать домашние задания",
        timeframe="за три месяца",
        metric="оценки младших по математике поднялись с {before} до {after}",
        soft="учиться младшие стали получше",
        conflict="сёстры каждый вечер спорили, кому первой садиться за уроки",
        mistake="сначала я просто проверял дневники и злился, толку от этого не было",
        lesson="что нужен понятный порядок, а не контроль по настроению",
        application="когда осенью младшая пошла в новую школу, мы сразу составили такой же график на неделю",
        before=3,
        after=4,
        topic_nom_kk="кішілерге арналған дайындық кестесі",
        topic_acc_kk="дайындық кестесін",
        vague_kk="үй жұмыстарына",
        role_kk="кішілердің оқуына жауапты",
        team_kk="екі кіші қарындасымды",
        problem_kk="анам жұмысқа кетті де, кішілер үй жұмысын істеуді қойды",
        timeframe_kk="үш ай",
        metric_kk="кішілердің математикадан бағасы {before}-тен {after}-ке көтерілді",
        soft_kk="кішілер жақсырақ оқи бастады",
        conflict_kk="қарындастарым кім бірінші сабақ оқитыны үшін таласатын",
        mistake_kk="әуелі күнделікті тексеріп, ұрсып қана жүрдім, оның пайдасы болмады",
        lesson_kk="көңіл-күймен бақылау емес, түсінікті тәртіп керек екенін",
        application_kk="күзде кішісі жаңа мектепке барғанда, бірден сондай апталық кесте құрдық",
    ),
    Domain(
        key="volunteering",
        topic_nom="сбор корма для приюта",
        topic_acc="сбор корма для приюта",
        vague="волонтёрских акциях",
        role="координатором сбора",
        team="двенадцать ребят из параллели",
        problem="приют рядом нуждался в помощи, но никто не брался это организовать",
        timeframe="за две недели",
        metric="мы собрали {after} килограммов корма вместо запланированных {before}",
        soft="корм в приют мы всё-таки привезли",
        conflict="двое ребят обиделись, что их поставили разбирать пакеты, а не выступать",
        mistake="в первый день я не проверил, кто вообще придёт, и половина пунктов осталась без людей",
        lesson="что список ответственных надо подтверждать накануне, а не надеяться на обещания",
        application="на следующем сборе к Наурызу я обзвонил всех вечером перед началом и подтвердил каждого",
        before=40,
        after=150,
        topic_nom_kk="баспанаға жем жинау акциясы",
        topic_acc_kk="жем жинау акциясын",
        vague_kk="еріктілер акцияларына",
        role_kk="жинау үйлестірушісі",
        team_kk="параллель сыныптан он екі баланы",
        problem_kk="жанымыздағы баспана көмек сұрады, бірақ ешкім ұйымдастыруға кіріспеді",
        timeframe_kk="екі апта",
        metric_kk="жоспарланған {before} келінің орнына {after} келі жем жинадық",
        soft_kk="жемді баспанаға әйтеуір жеткіздік",
        conflict_kk="екі бала пакет реттеуге қойылғанына өкпелеп қалды",
        mistake_kk="бірінші күні кім келетінін тексермедім, жинау орындарының жартысы бос қалды",
        lesson_kk="жауаптылар тізімін алдын ала растау керек екенін",
        application_kk="келесі Наурыз акциясында басталуға дейін кешке бәріне қоңырау шалып, растап алдым",
    ),
    Domain(
        key="work",
        topic_nom="новый график смен в кафе",
        topic_acc="новый график смен в кафе",
        vague="работе в кафе",
        role="старшим по смене",
        team="четверых официантов",
        problem="в вечерние часы заказы стояли по двадцать минут и гости уходили",
        timeframe="за месяц",
        metric="средний чек в мою смену вырос с {before} до {after} тысяч тенге",
        soft="жаловаться гости стали меньше",
        conflict="двое официантов не хотели выходить в одну смену",
        mistake="сначала я поставил всех новичков на один вечер и получил самый провальный день месяца",
        lesson="что новичка надо ставить только рядом с опытным",
        application="когда летом набрали ещё двоих, я сразу расписал их по опытным сменам",
        before=3,
        after=5,
        topic_nom_kk="дәмханадағы жаңа ауысым кестесі",
        topic_acc_kk="жаңа ауысым кестесін",
        vague_kk="дәмханадағы жұмысқа",
        role_kk="ауысым басшысы",
        team_kk="төрт даяшыны",
        problem_kk="кешкі уақытта тапсырыс жиырма минут тұрып қалатын, қонақтар кетіп қалатын",
        timeframe_kk="бір ай",
        metric_kk="менің ауысымымдағы орташа чек {before} мыңнан {after} мың теңгеге өсті",
        soft_kk="қонақтар аз шағымдана бастады",
        conflict_kk="екі даяшы бір ауысымда жұмыс істегісі болмады",
        mistake_kk="алғашында жаңа қызметкерлердің бәрін бір кешке қойып, айдың ең сәтсіз күнін алдым",
        lesson_kk="жаңа қызметкерді тек тәжірибелінің қасына қою керек екенін",
        application_kk="жазда екі адам алғанда, оларды бірден тәжірибелі ауысымдарға жаздым",
    ),
    Domain(
        key="own_project",
        topic_nom="телеграм-канал с разборами задач ЕНТ",
        topic_acc="телеграм-канал с разборами задач ЕНТ",
        vague="своих проектах",
        role="редактором канала",
        team="трёх ребят из школы",
        problem="у нас не было ни репетиторов, ни нормальных разборов заданий",
        timeframe="за четыре месяца",
        metric="подписчиков канала стало {after} вместо {before}",
        soft="читателей стало заметно больше",
        conflict="один из ребят хотел ставить рекламу, а я был против",
        mistake="две недели я публиковал всё сам и почти забросил канал из-за учёбы",
        lesson="что расписание публикаций надо делить на нескольких человек",
        application="школьную газету мы потом сразу поделили: у каждого свой день выпуска",
        before=60,
        after=900,
        topic_nom_kk="ҰБТ есептерін талдайтын телеграм арна",
        topic_acc_kk="телеграм арнаны",
        vague_kk="өз жобаларыма",
        role_kk="арна редакторы",
        team_kk="мектептен үш баланы",
        problem_kk="бізде репетитор да, дұрыс талдау да болмады",
        timeframe_kk="төрт ай",
        metric_kk="арнаның жазылушысы {before}-тен {after}-ке дейін өсті",
        soft_kk="оқырман айтарлықтай көбейді",
        conflict_kk="балалардың бірі жарнама қойғысы келді, мен қарсы болдым",
        mistake_kk="екі апта бойы бәрін өзім жариялап, оқуға бола арнаны тастай жаздадым",
        lesson_kk="жариялау кестесін бірнеше адамға бөлу керек екенін",
        application_kk="мектеп газетін кейін бірден бөлдік: әркімнің өз шығатын күні болды",
    ),
    Domain(
        key="sports",
        topic_nom="школьная команда по волейболу",
        topic_acc="школьную команду по волейболу",
        vague="спортивной жизни школы",
        role="капитаном команды",
        team="восьмерых ребят",
        problem="тренер уехал, и команда перестала собираться на тренировки",
        timeframe="за сезон",
        metric="команда поднялась с {before} места на {after} в городской лиге",
        soft="на тренировки снова стали приходить",
        conflict="двое игроков спорили за место в основе",
        mistake="перед первым матчем я не распределил, кто отвечает за форму, и мы вышли без номеров",
        lesson="что перед каждым выездом нужен список ответственных",
        application="на спартакиаду я заранее закрепил за каждым свою задачу",
        before=9,
        after=3,
        topic_nom_kk="мектептің волейбол командасы",
        topic_acc_kk="волейбол командасын",
        vague_kk="мектептің спорттық өміріне",
        role_kk="команда капитаны",
        team_kk="сегіз баланы",
        problem_kk="жаттықтырушы кетіп қалды, команда жаттығуға жиналуды қойды",
        timeframe_kk="бір маусым",
        metric_kk="команда қалалық лигада {before} орыннан {after} орынға көтерілді",
        soft_kk="жаттығуға қайта келе бастады",
        conflict_kk="екі ойыншы негізгі құрамдағы орын үшін таласты",
        mistake_kk="бірінші матч алдында форма үшін кім жауапты екенін бөлмедім, нөмірсіз шықтық",
        lesson_kk="әр сапар алдында жауаптылар тізімі керек екенін",
        application_kk="спартакиадаға әркімге өз тапсырмасын алдын ала бекітіп қойдым",
    ),
)

DOMAIN_BY_KEY = {d.key: d for d in DOMAINS}


# --------------------------------------------------------------------------- #
# Содержательные блоки. Каждый привязан к индикатору BARS того уровня, который
# он реализует, — это и есть источник метки. Никаких оценочных слов в тексте
# блоков нет: уровень выражен тем, ЧТО кандидат сообщает (конкретика, личный
# вклад, результат, перенос вывода), а не тем, как это названо.
# --------------------------------------------------------------------------- #

#: level -> segment -> [(indicator_id, template)]
BLOCKS_RU: dict[Level, dict[Segment, tuple[tuple[str, str], ...]]] = {
    "weak": {
        "action": (
            ("lead.weak.1", "Я часто участвую в {vague}, помогаю там, где нужно."),
            ("lead.weak.3", "Если в классе что-то организуют, я обычно не остаюсь в стороне."),
            ("lead.weak.5", "Про {topic_acc} могу сказать, что мы занимались этим все вместе."),
        ),
        "thinking": (
            ("lead.weak.1", "Считаю, что лидер должен быть примером для других, поэтому стараюсь так себя и вести."),
            ("lead.weak.2", "Я думаю, главное — быть ответственным и не подводить людей."),
            ("lead.weak.2", "Особо не задумывался, делал как принято."),
        ),
        "outcome": (
            ("lead.weak.1", "В итоге всё прошло нормально, все остались довольны."),
            ("lead.weak.5", "Результат был хороший, {soft}."),
            ("lead.weak.4", "Получилось неплохо, хотя точных цифр я не назову."),
        ),
        "learnings": (
            ("lead.weak.1", "Понял, что надо быть активнее."),
            ("lead.weak.1", "Вынес для себя, что важно уметь работать в коллективе."),
        ),
        "application": (
            ("lead.weak.1", "Стараюсь применять это всегда и во всём."),
            ("lead.weak.1", "Думаю, это пригодится мне в любой ситуации."),
        ),
    },
    "normal": {
        "action": (
            ("lead.normal.3", "Когда {problem}, мне предложили этим заняться, и я согласился."),
            ("lead.normal.2", "Я отвечал за {topic_acc}: собирал ребят и напоминал про встречи."),
            ("lead.normal.3", "Мне поручили организовать {topic_acc}, потому что больше было некому, и я взялся."),
        ),
        "thinking": (
            ("lead.normal.2", "Я решил начать с расписания: без него половина просто не приходила."),
            ("lead.normal.4", "Подумал, что проще договориться через классного руководителя, чем собирать всех по одному."),
            ("lead.normal.4", "Действовал по ситуации: где-то просил помочь, где-то делал сам."),
        ),
        "outcome": (
            ("lead.normal.5", "{soft_cap}, и {tf} мы всё-таки продержались."),
            ("lead.normal.1", "Получилось так: {soft}."),
            ("lead.normal.5", "В итоге {soft}, а дальше этим занялся уже кто-то другой."),
        ),
        "conflict": (
            ("lead.normal.4", "Когда {conflict}, я просто попросил их не ссориться, а дальше как-то само улеглось."),
        ),
        "learnings": (
            ("lead.normal.4", "Понял, что без напоминаний половина ребят забывает про свои задачи."),
            ("lead.normal.4", "Для себя вынес, что договариваться надо заранее."),
        ),
        "application": (
            ("lead.normal.1", "Потом я так же собирал ребят на субботник, правда уже без расписания."),
            ("lead.normal.1", "Позже пробовал повторить это ещё раз, но получилось хуже."),
        ),
    },
    "strong": {
        "action": (
            ("lead.strong.2", "{tf_cap} я собрал {team} и запустил {topic_acc}: составил расписание, распределил роли и договорился с администрацией о помещении."),
            ("lead.strong.3", "Я стал {role} и первым делом разделил задачи: кто ищет материал, кто отвечает за сроки, кто говорит с людьми."),
            ("lead.strong.2", "Я сам предложил {topic_acc}, набрал {team} и взял на себя всё, что касалось сроков."),
        ),
        "thinking": (
            ("lead.strong.1", "Я выбрал такой порядок, потому что {problem}: сначала надо было убрать причину, а не следствие."),
            ("lead.strong.1", "Я исходил из того, что людей держит не энтузиазм, а понятный график и видимый результат."),
        ),
        "conflict": (
            ("lead.strong.3", "Когда {conflict}, я не стал решать за них: посадил обоих рядом, и мы договорились о порядке на месяц вперёд."),
            ("lead.strong.3", "{conflict_cap} — я разобрал это с ними отдельно и закрепил договорённость в общем чате."),
        ),
        "outcome": (
            ("lead.strong.5", "{hard_cap}."),
            ("lead.strong.5", "{hard_cap}, и этот порядок работает до сих пор."),
        ),
        "learnings": (
            ("lead.strong.4", "{mistake_cap} — тогда я понял, {lesson}."),
        ),
        "application": (
            ("lead.strong.5", "{application_cap}."),
            ("lead.strong.5", "{application_cap}, и на этот раз обошлось без срывов."),
        ),
    },
}

BLOCKS_KK: dict[Level, dict[Segment, tuple[tuple[str, str], ...]]] = {
    "weak": {
        "action": (
            ("lead.weak.1", "Мен {vague_kk} үнемі қатысамын, көмек керек жерде көмектесемін."),
            ("lead.weak.3", "Сыныпта бірдеңе ұйымдастырылса, мен де қалыс қалмаймын."),
        ),
        "thinking": (
            ("lead.weak.2", "Менің ойымша, көшбасшы басқаларға үлгі болуы керек."),
            ("lead.weak.2", "Аса ойланбадым, бәрі істегендей істедім."),
        ),
        "outcome": (
            ("lead.weak.1", "Нәтижесінде бәрі жақсы өтті, бәрі риза болды."),
            ("lead.weak.4", "Жаман болмады, бірақ нақты санын айта алмаймын."),
        ),
        "learnings": (
            ("lead.weak.1", "Белсендірек болу керек екенін түсіндім."),
        ),
        "application": (
            ("lead.weak.1", "Мұны әрдайым қолдануға тырысамын."),
        ),
    },
    "normal": {
        "action": (
            ("lead.normal.3", "Маған {topic_acc_kk} ұйымдастыруды тапсырды, мен келістім."),
            ("lead.normal.2", "Мен {topic_acc_kk} ұйымдастыруға жауапты болдым: балаларды жинап, жиналыс туралы ескертіп жүрдім."),
        ),
        "thinking": (
            ("lead.normal.2", "Кестеден бастауды шештім: онсыз жартысы келмейтін."),
            ("lead.normal.4", "Жағдайға қарап істедім: бірде көмек сұрадым, бірде өзім жасадым."),
        ),
        "outcome": (
            ("lead.normal.5", "{soft_kk_cap}, {tf_kk} осылай жүрдік."),
            ("lead.normal.1", "Нәтижесі мынадай болды: {soft_kk}."),
        ),
        "conflict": (
            ("lead.normal.4", "{conflict_kk_cap} — мен оларға ұрыспауды сұрадым, кейін өзі реттелді."),
        ),
        "learnings": (
            ("lead.normal.4", "Ескертпесе, көбі өз тапсырмасын ұмытып кететінін түсіндім."),
        ),
        "application": (
            ("lead.normal.1", "Кейін сенбілікке де осылай жинадым, бірақ кестесіз."),
        ),
    },
    "strong": {
        "action": (
            ("lead.strong.2", "{tf_kk_cap} ішінде мен {team_kk} жинап, {topic_acc_kk} іске қостым: кесте құрдым, рөлдерді бөлдім, әкімшіліктен бөлме сұрап алдым."),
            ("lead.strong.3", "Мен {role_kk} болдым және бірінші кезекте тапсырманы бөлдім: кім материал іздейді, кім мерзімге жауапты, кім адамдармен сөйлеседі."),
        ),
        "thinking": (
            ("lead.strong.1", "Мен адамдарды ынта емес, түсінікті кесте мен көрінетін нәтиже ұстайды деп есептедім."),
            ("lead.strong.1", "Осылай істедім, себебі {problem_kk}: алдымен себебін жою керек еді."),
        ),
        "conflict": (
            ("lead.strong.3", "{conflict_kk_cap} — екеуін қатар отырғызып, бір айға келісіп алдық."),
        ),
        "outcome": (
            ("lead.strong.5", "{hard_kk_cap}."),
            ("lead.strong.5", "{hard_kk_cap}, бұл тәртіп әлі де жұмыс істеп тұр."),
        ),
        "learnings": (
            ("lead.strong.4", "{mistake_kk_cap} — сол кезде {lesson_kk} түсіндім."),
        ),
        "application": (
            ("lead.strong.5", "{application_kk_cap}."),
        ),
    },
}

#: Фоновое предложение. Единственное место, где вообще упоминаются регион и школа.
BACKGROUND_RU = {
    ("city", "strong"): "Я учусь в городской школе с сильной подготовкой, у нас есть все кружки.",
    ("city", "ordinary"): "Я учусь в обычной городской школе.",
    ("village", "strong"): "Я учусь в сельской школе, но учителя у нас сильные.",
    ("village", "ordinary"): "Я учусь в сельской школе, кружков и репетиторов у нас нет.",
}
BACKGROUND_KK = {
    ("city", "strong"): "Мен қалалық мектепте оқимын, дайындығы күшті, барлық үйірме бар.",
    ("city", "ordinary"): "Мен қарапайым қалалық мектепте оқимын.",
    ("village", "strong"): "Мен ауылдық мектепте оқимын, бірақ мұғалімдеріміз күшті.",
    ("village", "ordinary"): "Мен ауылдық мектепте оқимын, бізде үйірме де, репетитор да жоқ.",
}

#: Наполнитель без содержания. Отдельно от блоков: он не несёт индикаторов и нужен
#: для длинных ответов и для «воды в обёртке».
FILLER_RU = (
    "Для меня лидерство — это в первую очередь ответственность.",
    "Я убеждён, что любую задачу можно решить, если подходить к ней системно.",
    "Мне кажется, важно уметь слышать других и находить общий язык.",
    "Считаю, что настоящий лидер растёт вместе со своей командой.",
    "Развитие себя и окружающих я считаю приоритетом.",
    "Умение брать на себя инициативу — то качество, которое я в себе развиваю.",
)
FILLER_KK = (
    "Мен үшін көшбасшылық — ең алдымен жауапкершілік.",
    "Кез келген істі жүйелі шешуге болады деп сенемін.",
    "Басқаны тыңдай білу маңызды деп ойлаймын.",
)


# --------------------------------------------------------------------------- #
# Рендеринг: содержание -> текст
# --------------------------------------------------------------------------- #

def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _facts(d: Domain) -> dict[str, str]:
    hard = f"{d.timeframe} {d.metric.format(before=d.before, after=d.after)}"
    hard_kk = f"{d.timeframe_kk} ішінде {d.metric_kk.format(before=d.before, after=d.after)}"
    return {
        "vague": d.vague,
        "topic_nom": d.topic_nom,
        "topic_acc": d.topic_acc,
        "role": d.role,
        "team": d.team,
        "problem": d.problem,
        "tf": d.timeframe,
        "tf_cap": _cap(d.timeframe),
        "soft": d.soft,
        "soft_cap": _cap(d.soft),
        "hard": hard,
        "hard_cap": _cap(hard),
        "conflict": d.conflict,
        "conflict_cap": _cap(d.conflict),
        "mistake": d.mistake,
        "mistake_cap": _cap(d.mistake),
        "lesson": d.lesson,
        "application": d.application,
        "application_cap": _cap(d.application),
        "vague_kk": d.vague_kk,
        "topic_nom_kk": d.topic_nom_kk,
        "topic_acc_kk": d.topic_acc_kk,
        "role_kk": d.role_kk,
        "team_kk": d.team_kk,
        "problem_kk": d.problem_kk,
        "tf_kk": d.timeframe_kk,
        "tf_kk_cap": _cap(d.timeframe_kk),
        "soft_kk": d.soft_kk,
        "soft_kk_cap": _cap(d.soft_kk),
        "hard_kk": hard_kk,
        "hard_kk_cap": _cap(hard_kk),
        "conflict_kk": d.conflict_kk,
        "conflict_kk_cap": _cap(d.conflict_kk),
        "mistake_kk": d.mistake_kk,
        "mistake_kk_cap": _cap(d.mistake_kk),
        "lesson_kk": d.lesson_kk,
        "application_kk": d.application_kk,
        "application_kk_cap": _cap(d.application_kk),
    }


#: Прошедшее время в русском обязано согласовываться с родом говорящего.
#: Род — фоновый признак: он никогда не входит в модель и проверяется
#: контрфактическими парами.
_FEM_IRREGULAR = {
    "был": "была",
    "помог": "помогла",
    "вышел": "вышла",
    "убеждён": "убеждена",
    "вынес": "вынесла",
    "вёл": "вела",
    "сам": "сама",
}
_MASC_VERBS = (
    "взял взялся выбрал готовил действовал делал договорился забросил задумывался "
    "закрепил запустил злился исходил набрал напоминал обзвонил организовал отвечал "
    "подтвердил подумал получил понял попросил посадил поставил предложил применил "
    "пробовал проверил проверял просил публиковал разделил разобрал расписал "
    "распределил решил собирал собрал согласился составил стал участвовал"
).split()


def _fem_form(word: str) -> str:
    if word in _FEM_IRREGULAR:
        return _FEM_IRREGULAR[word]
    if word.endswith("лся"):
        return word[:-3] + "лась"
    if word.endswith("л"):
        return word + "а"
    return word


_FEM_MAP = {w: _fem_form(w) for w in _MASC_VERBS}
_FEM_MAP.update(_FEM_IRREGULAR)
_FEM_RE = re.compile(r"\b(" + "|".join(sorted(_FEM_MAP, key=len, reverse=True)) + r")\b",
                     re.IGNORECASE)


def _fem_sub(match: re.Match) -> str:
    word = match.group(1)
    form = _FEM_MAP[word.lower()]
    return form[:1].upper() + form[1:] if word[:1].isupper() else form


def feminize(text: str) -> str:
    """Переводит формы прошедшего времени в женский род.

    Заглавная буква сохраняется: «Понял» -> «Поняла».
    """
    return _FEM_RE.sub(_fem_sub, text)


_COLLOQUIAL_OPENERS = ("Ну, ", "Короче, ", "В общем, ", "Вот, ")
_BUREAU_OPENERS = ("В рамках данной работы ", "Следует отметить, что ", "В связи с этим ")
_POLISHED_OPENERS = ("Прежде всего, ", "Кроме того, ", "Помимо этого, ", "Таким образом, ")
_BUREAU_CLOSER = "Считаю данный опыт полезным для дальнейшей деятельности."
_POLISHED_CLOSER = "Этот опыт для меня — важная точка роста."

_OPENERS_KK = {
    "colloquial": ("Иә, ", "Жалпы, ", "Сөйтіп, "),
    "bureaucratic": ("Осыған байланысты ", "Айта кету керек, "),
    "polished": ("Ең алдымен, ", "Сонымен қатар, ", "Осылайша, "),
}
_CLOSERS_KK = {
    "bureaucratic": "Бұл тәжірибені алдағы жұмысқа пайдалы деп санаймын.",
    "polished": "Бұл тәжірибе мен үшін маңызды өсу нүктесі болды.",
}

_TYPO_VOWELS = "аеиоуыэюя"


def _typo(word: str, rng: random.Random) -> str:
    """Опечатка в одном слове. Цифры не трогаем: факты должны сохраняться."""
    if any(ch.isdigit() for ch in word) or len(word) < 5:
        return word
    kind = rng.randrange(3)
    pos = rng.randrange(1, len(word) - 1)
    if kind == 0 and word[pos].lower() in _TYPO_VOWELS:
        return word[:pos] + word[pos + 1:]
    if kind == 1:
        return word[:pos] + word[pos] + word[pos:]
    return word[:pos] + word[pos + 1] + word[pos] + word[pos + 2:]


def apply_style(items: list[tuple[str, str]], style: Style,
                rng: random.Random, main_lang: str = "ru") -> list[str]:
    """Накладывает поверхностный стиль, не меняя факты.

    ``items`` — пары (язык предложения, предложение): связки подбираются на языке
    самого предложения, иначе в смешанных ответах получается «Следует отметить,
    что мен...».

    Стиль сознательно отделён от содержания: «шумовые» примеры и контрфактические
    пары по «отполированности» получаются подстановкой другого стиля к тому же
    содержанию.
    """
    out = [text for _, text in items]
    langs = [lang for lang, _ in items]

    def openers(lang: str) -> tuple[str, ...]:
        if lang == "kk":
            return _OPENERS_KK.get(style, ())
        return {"colloquial": _COLLOQUIAL_OPENERS,
                "bureaucratic": _BUREAU_OPENERS,
                "polished": _POLISHED_OPENERS}.get(style, ())

    if style in ("colloquial", "bureaucratic", "polished"):
        threshold = {"colloquial": 0.4, "bureaucratic": 0.45, "polished": 0.5}[style]
        for i in range(1, len(out)):
            bank = openers(langs[i])
            if bank and rng.random() < threshold:
                out[i] = rng.choice(bank) + _lower_first(out[i])
        if style == "colloquial":
            out = [t.replace(", поэтому", ", так что") for t in out]
        elif style == "bureaucratic":
            out.append(_CLOSERS_KK["bureaucratic"] if main_lang == "kk" else _BUREAU_CLOSER)
        else:
            out.append(_CLOSERS_KK["polished"] if main_lang == "kk" else _POLISHED_CLOSER)
    elif style == "errors":
        styled = []
        for i, text in enumerate(out):
            words = [_typo(w, rng) if rng.random() < 0.18 else w for w in text.split(" ")]
            text = " ".join(words).replace("ё", "е")
            if rng.random() < 0.4:
                text = text.replace(",", "", 1)
            if i > 0 and rng.random() < 0.35:
                text = _lower_first(text)
            styled.append(text)
        out = styled
    return out


@dataclass(frozen=True)
class ContentPlan:
    """Содержание ответа: уровень, домен, набор смысловых блоков.

    Не содержит ни языка, ни стиля, ни фоновых признаков — только то, что
    кандидат сообщает. Именно это разделение делает контрфактические пары
    честными: у пары один и тот же ContentPlan.
    """

    #: Уровень-метка: тот, которому соответствует большинство блоков.
    level: Level
    domain_key: str
    #: (сегмент, номер варианта блока, уровень блока)
    blocks: tuple[tuple[Segment, int, Level], ...]
    fillers: tuple[int, ...] = ()

    @property
    def domain(self) -> Domain:
        return DOMAIN_BY_KEY[self.domain_key]

    def indicator_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for seg, idx, level in self.blocks:
            bank = BLOCKS_RU[level][seg]
            ids.append(bank[idx % len(bank)][0])
        return tuple(dict.fromkeys(ids))

    def atola_plan(self) -> tuple[Segment, ...]:
        return tuple(dict.fromkeys(seg for seg, _, _ in self.blocks))

    def block_levels(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for _, _, level in self.blocks:
            out[level] = out.get(level, 0) + 1
        return out

    def mixed_from(self) -> Level | None:
        other = [lv for lv in self.block_levels() if lv != self.level]
        return other[0] if other else None


@dataclass(frozen=True)
class RenderConfig:
    """Поверхностные и фоновые условия. В модель не попадают никогда."""

    lang: Lang = "ru"
    style: Style = "polished"
    settlement: str = "city"
    school_type: str = "ordinary"
    gender: str = "m"
    with_background: bool = True

    def replace(self, **kw) -> "RenderConfig":
        data = asdict(self)
        data.update(kw)
        return RenderConfig(**data)


#: Вероятность появления сегмента по уровням. Пересечение намеренное: если бы
#: слабый ответ никогда не содержал Outcome, покрытие ATOLA отделяло бы уровни
#: идеально, и модель училась бы на артефакте генератора.
SEGMENT_PROBS: dict[Level, dict[Segment, float]] = {
    "weak": {"action": 1.0, "thinking": 0.55, "conflict": 0.0, "outcome": 0.45,
             "learnings": 0.35, "application": 0.10},
    "normal": {"action": 1.0, "thinking": 0.75, "conflict": 0.15, "outcome": 0.90,
               "learnings": 0.60, "application": 0.30},
    "strong": {"action": 1.0, "thinking": 0.90, "conflict": 0.50, "outcome": 1.0,
               "learnings": 0.90, "application": 0.85},
}
TARGET_BLOCKS: dict[LengthGrade, int] = {"short": 3, "medium": 5, "long": 7}
DROP_ORDER: tuple[Segment, ...] = ("conflict", "thinking", "learnings", "application", "outcome")


#: Соседние уровни. Подмешивать можно только соседей: «слабо» и «высоко»
#: в одном ответе — это не неоднозначность, а несогласованная разметка.
ADJACENT: dict[Level, tuple[Level, ...]] = {
    "weak": ("normal",),
    "normal": ("weak", "strong"),
    "strong": ("normal",),
}


def build_plan(level: Level, domain: Domain, length: LengthGrade,
               rng: random.Random, mix_from: Level | None = None) -> ContentPlan:
    probs = SEGMENT_PROBS[level]
    bank = BLOCKS_RU[level]
    chosen = [s for s in SEGMENT_ORDER
              if s in bank and (s == "action" or rng.random() < probs[s])]
    target = TARGET_BLOCKS[length]

    for seg in DROP_ORDER:
        if len(chosen) <= target:
            break
        if seg in chosen:
            chosen.remove(seg)

    blocks = [(seg, 0, level) for seg in chosen]
    # добираем длину другими вариантами тех же сегментов — но только теми,
    # которые в банке действительно есть, иначе ответ начинает повторяться
    priority = ("action", "thinking", "learnings", "application", "conflict", "outcome")
    extras = [(seg, i, level) for i in (1, 2) for seg in priority
              if seg in chosen and i < len(bank[seg])]
    for extra in extras:
        if len(blocks) >= target:
            break
        blocks.append(extra)
    if mix_from:
        blocks = _mix_levels(blocks, level, mix_from, rng)
    blocks.sort(key=lambda b: (SEGMENT_ORDER.index(b[0]), b[1]))

    shortfall = max(0, target - len(blocks))
    n_fill = min({"short": 0, "medium": 1, "long": 2}[length] + shortfall, len(FILLER_RU))
    fillers = tuple(rng.sample(range(len(FILLER_RU)), n_fill))
    return ContentPlan(level=level, domain_key=domain.key, blocks=tuple(blocks),
                       fillers=fillers)


def _mix_levels(blocks: list[tuple[Segment, int, Level]], level: Level,
                mix_from: Level, rng: random.Random) -> list[tuple[Segment, int, Level]]:
    """Часть блоков берётся с соседнего уровня.

    Зачем: в реальном интервью ответ редко ложится в один уровень целиком.
    Кандидат описывает результат по-взрослому и тут же уходит в общие слова.
    Если корпус состоит только из «чистых» ответов, любая модель показывает
    идеальную метрику — и эта метрика ничего не значит.

    Метка остаётся исходной: большинство блоков — с базового уровня. Это ровно
    то правило, по которому уровень ставит человек, — по преобладанию
    наблюдаемых индикаторов.
    """
    donor = BLOCKS_RU[mix_from]
    k = max(1, len(blocks) // 3)
    swappable = [i for i, (seg, _, _) in enumerate(blocks) if seg in donor]
    rng.shuffle(swappable)
    for i in swappable[:k]:
        seg = blocks[i][0]
        blocks[i] = (seg, 0, mix_from)
    # иногда добавляем сегмент, которого на базовом уровне не было
    absent = [seg for seg in donor if seg not in {b[0] for b in blocks}]
    if absent and rng.random() < 0.5:
        blocks.append((rng.choice(absent), 0, mix_from))
    return blocks


def render(plan: ContentPlan, cfg: RenderConfig, rng: random.Random) -> str:
    facts = _facts(plan.domain)
    main_lang = "kk" if cfg.lang == "kk" else "ru"
    items: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(lang: str, sentence: str, position: int | None = None) -> None:
        if sentence in seen:      # дословный повтор — признак бедности шаблонов, не текста
            return
        seen.add(sentence)
        items.insert(position, (lang, sentence)) if position is not None \
            else items.append((lang, sentence))

    if cfg.with_background:
        key = (cfg.settlement, cfg.school_type)
        add(main_lang, (BACKGROUND_KK if main_lang == "kk" else BACKGROUND_RU)[key])

    kk_positions: set[int] = set()
    if cfg.lang == "mixed" and plan.blocks:
        n_kk = max(1, len(plan.blocks) // 3)
        kk_positions = set(rng.sample(range(len(plan.blocks)), n_kk))

    for pos, (seg, idx, block_level) in enumerate(plan.blocks):
        lang = "ru"
        bank = None
        if cfg.lang == "kk" or pos in kk_positions:
            bank = BLOCKS_KK[block_level].get(seg)
            lang = "kk"
        if not bank:                      # в казахском банке вариантов меньше
            bank, lang = BLOCKS_RU[block_level][seg], "ru"
        _, template = bank[idx % len(bank)]
        add(lang, template.format(**facts))

    pool = FILLER_KK if main_lang == "kk" else FILLER_RU
    for f_idx in plan.fillers:
        position = rng.randrange(1, len(items) + 1) if len(items) > 1 else len(items)
        add(main_lang, pool[f_idx % len(pool)], position)

    sentences = apply_style(items, cfg.style, rng, main_lang)
    text = " ".join(sentences).strip()
    if cfg.gender == "f":
        text = feminize(text)
    return text


# --------------------------------------------------------------------------- #
# Сборка корпуса
# --------------------------------------------------------------------------- #

def _balanced(values: Iterable, n: int, rng: random.Random) -> list:
    """Список длины n с примерно равным числом каждого значения, в случайном порядке."""
    values = list(values)
    out = (values * (n // len(values) + 1))[:n]
    rng.shuffle(out)
    return out


def _row(row_id: str, text: str, level: Level, plan: ContentPlan,
         cfg: RenderConfig, length: LengthGrade, noise: str | None,
         origin: str, seed: int) -> dict:
    return {
        "id": row_id,
        "competency": "leadership",
        "text": text,
        "level": level,
        "variation_meta": {
            "domain": plan.domain_key,
            "length": length,
            "style": cfg.style,
            "language": cfg.lang,
            "settlement": cfg.settlement,
            "school_type": cfg.school_type,
            "gender": cfg.gender,
            "noise": noise,
            "mix": plan.mixed_from(),
            "block_levels": plan.block_levels(),
            "atola_plan": list(plan.atola_plan()),
            "indicator_ids": list(plan.indicator_ids()),
            "origin": origin,
            "seed": seed,
        },
    }


def build_corpus(per_level: int = 40, seed: int = SEED) -> list[dict]:
    """120 ответов: по 40 на уровень, с балансом по всем осям вариаций."""
    rng = random.Random(seed)
    rows: list[dict] = []
    for level in LEVELS:
        domains = _balanced([d.key for d in DOMAINS], per_level, rng)
        styles = _balanced(STYLES, per_level, rng)
        lengths = _balanced(LENGTHS, per_level, rng)
        langs = _balanced(LANGS, per_level, rng)
        settlements = _balanced(SETTLEMENTS, per_level, rng)
        schools = _balanced(SCHOOL_TYPES, per_level, rng)
        genders = _balanced(GENDERS, per_level, rng)
        mixes = _balanced([True, True, False, False, False, False, False],
                          per_level, rng)
        for i in range(per_level):
            domain = DOMAIN_BY_KEY[domains[i]]
            length = lengths[i]
            mix_from = rng.choice(ADJACENT[level]) if mixes[i] else None
            plan = build_plan(level, domain, length, rng, mix_from)
            cfg = RenderConfig(lang=langs[i], style=styles[i], settlement=settlements[i],
                               school_type=schools[i], gender=genders[i])
            text = render(plan, cfg, random.Random(rng.randrange(10 ** 9)))
            rows.append(_row(f"lead-{level}-{i:02d}", text, level, plan, cfg,
                             length, None, "template", seed))
    return rows


#: «Шумовые» примеры: содержание одного уровня в обёртке другого.
#: Самые важные стресс-примеры корпуса.
NOISE_PLANS: dict[str, tuple[tuple[Segment, int, Level], ...]] = {
    "polished_weak": (("action", 0, "weak"), ("thinking", 0, "weak"),
                      ("outcome", 1, "weak"), ("learnings", 1, "weak")),
    "rough_strong": (("action", 0, "strong"), ("outcome", 0, "strong"),
                     ("learnings", 0, "strong"), ("application", 0, "strong")),
}


def build_noise(n: int = 20, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed + 1)
    rows: list[dict] = []
    half = n // 2
    for i in range(n):
        noise = "polished_weak" if i < half else "rough_strong"
        level: Level = "weak" if noise == "polished_weak" else "strong"
        domain = DOMAINS[i % len(DOMAINS)]
        if noise == "polished_weak":
            plan = ContentPlan(level, domain.key, NOISE_PLANS[noise], fillers=(0, 2, 4))
            cfg = RenderConfig(lang="ru", style="polished",
                               settlement=SETTLEMENTS[i % 2], school_type="strong",
                               gender=GENDERS[i % 2])
            length: LengthGrade = "long"
        else:
            plan = ContentPlan(level, domain.key, NOISE_PLANS[noise], fillers=())
            cfg = RenderConfig(lang="ru" if i % 3 else "mixed",
                               style="errors" if i % 2 else "colloquial",
                               settlement=SETTLEMENTS[(i + 1) % 2], school_type="ordinary",
                               gender=GENDERS[i % 2])
            length = "short"
        text = render(plan, cfg, random.Random(seed + 100 + i))
        rows.append(_row(f"lead-noise-{i:02d}", text, level, plan, cfg,
                         length, noise, "template", seed))
    return rows


#: Фоновые признаки, по которым строятся контрфактические пары.
CF_ATTRIBUTES = ("settlement", "language", "polish", "gender")


def _cf_configs(attribute: str, base: RenderConfig) -> tuple[RenderConfig, RenderConfig]:
    if attribute == "settlement":
        return base.replace(settlement="village"), base.replace(settlement="city")
    if attribute == "language":
        return base.replace(lang="ru"), base.replace(lang="kk")
    if attribute == "polish":
        return base.replace(style="errors"), base.replace(style="polished")
    if attribute == "gender":
        return base.replace(gender="m"), base.replace(gender="f")
    raise ValueError(attribute)


_DIGITS_RE = re.compile(r"\d+")


def digits(text: str) -> list[str]:
    return _DIGITS_RE.findall(text)


def same_facts(a: str, b: str) -> bool:
    """Числа в двух текстах совпадают как множество.

    Порядок упоминания может отличаться: в казахском шаблоне «вместо
    запланированных 40 собрали 150» естественно звучит в обратном порядке.
    """
    return sorted(digits(a)) == sorted(digits(b))


def build_pairs(n_per_attribute: int = 10, seed: int = SEED) -> list[dict]:
    """Контрфактические пары: один и тот же ContentPlan, разный фоновый признак.

    Факты сохраняются по построению — оба текста рендерятся из одного плана,
    с одним и тем же зерном генератора. Числа сверяются дополнительно.
    """
    rng = random.Random(seed + 2)
    rows: list[dict] = []
    for attribute in CF_ATTRIBUTES:
        for i in range(n_per_attribute):
            level = LEVELS[i % len(LEVELS)]
            domain = DOMAINS[(i + CF_ATTRIBUTES.index(attribute)) % len(DOMAINS)]
            length = LENGTHS[i % len(LENGTHS)]
            plan = build_plan(level, domain, length, rng)
            base = RenderConfig(lang="ru", style="polished", settlement="city",
                                school_type="ordinary", gender="m")
            cfg_a, cfg_b = _cf_configs(attribute, base)
            pair_seed = rng.randrange(10 ** 9)
            text_a = render(plan, cfg_a, random.Random(pair_seed))
            text_b = render(plan, cfg_b, random.Random(pair_seed))
            if not same_facts(text_a, text_b):
                raise AssertionError(
                    f"контрфактическая пара изменила числа: {attribute} #{i}")
            rows.append({
                "pair_id": f"cf-{attribute}-{i:02d}",
                "attribute": attribute,
                "competency": "leadership",
                "level": level,
                "domain": domain.key,
                "length": length,
                "a": {"text": text_a, "value": asdict(cfg_a)},
                "b": {"text": text_b, "value": asdict(cfg_b)},
                "atola_plan": list(plan.atola_plan()),
                "origin": "template",
            })
    return rows


# --------------------------------------------------------------------------- #
# Наборы для тестов устойчивости
# --------------------------------------------------------------------------- #

def _variant_shifted(plan: ContentPlan) -> ContentPlan:
    """Тот же план другими формулировками: у каждого блока берётся иной вариант."""
    shifted = []
    for seg, idx, level in plan.blocks:
        bank = BLOCKS_RU[level][seg]
        shifted.append((seg, (idx + 1) % len(bank), level))
    return ContentPlan(plan.level, plan.domain_key, tuple(shifted), plan.fillers)


def _without_outcome(plan: ContentPlan) -> ContentPlan:
    """Тот же ответ без Outcome и Application."""
    kept = tuple(b for b in plan.blocks if b[0] not in ("outcome", "application"))
    return ContentPlan(plan.level, plan.domain_key, kept, plan.fillers)


def build_robustness_sets(n: int = 30, seed: int = SEED) -> dict[str, list[dict]]:
    """Три набора пар: перефраз, ИИ-полировка, усечение.

    Все три строятся из одного ContentPlan, поэтому «содержание сохранено»
    здесь не обещание, а свойство конструкции.
    """
    rng = random.Random(seed + 4)
    out: dict[str, list[dict]] = {"paraphrase": [], "polish": [], "truncation": []}
    for i in range(n):
        level = LEVELS[i % len(LEVELS)]
        domain = DOMAINS[i % len(DOMAINS)]
        length = LENGTHS[(i // 2) % len(LENGTHS)]
        plan = build_plan(level, domain, length, rng)
        base = RenderConfig(lang="ru", style="colloquial", settlement="city",
                            school_type="ordinary", gender=GENDERS[i % 2])
        pair_seed = rng.randrange(10 ** 9)

        original = render(plan, base, random.Random(pair_seed))
        out["paraphrase"].append({
            "id": f"rb-paraphrase-{i:02d}", "level": level,
            "a": original,
            "b": render(_variant_shifted(plan), base, random.Random(pair_seed)),
        })
        out["polish"].append({
            "id": f"rb-polish-{i:02d}", "level": level,
            "a": render(plan, base.replace(style="errors"), random.Random(pair_seed)),
            "b": render(plan, base.replace(style="polished"), random.Random(pair_seed)),
        })
        out["truncation"].append({
            "id": f"rb-truncation-{i:02d}", "level": level,
            "a": original,
            "b": render(_without_outcome(plan), base, random.Random(pair_seed)),
        })
    return out


# --------------------------------------------------------------------------- #
# LLM-бэкенд
# --------------------------------------------------------------------------- #

GEN_MODEL = os.environ.get("QADAM_GEN_MODEL", "claude-sonnet-5")

#: Слова, которых не должно быть в промпте генерации ни при каких условиях.
FORBIDDEN_IN_PROMPT = (
    "слаб", "сильн", "хорош", "плох", "высок", "низк", "лучш", "худш",
    "балл", "оцен", "уровень", "weak", "strong", "level", "score",
)


def assert_no_judgment_words(prompt: str) -> None:
    """Промпт генерации не должен содержать оценочных слов.

    Иначе метка перестаёт быть свойством текста и становится пересказом
    суждения модели.
    """
    low = prompt.lower()
    found = [w for w in FORBIDDEN_IN_PROMPT if w in low]
    if found:
        raise ValueError(f"в промпт генерации попали оценочные слова: {found}")


_STYLE_HINT = {
    "colloquial": "разговорная речь, как в устном рассказе",
    "bureaucratic": "канцелярские обороты, официальные формулировки",
    "polished": "гладкая отредактированная речь, аккуратные связки",
    "errors": "речь с ошибками и опечатками, без запятых местами",
}
_LENGTH_HINT = {"short": "2-3 предложения", "medium": "5-6 предложений",
                "long": "9-11 предложений"}
_LANG_HINT = {"ru": "по-русски", "kk": "по-казахски",
              "mixed": "по-русски с двумя фразами на казахском"}
_PLACE_HINT = {"city": "городская школа", "village": "школа в селе"}
_SCHOOL_HINT = {"strong": "школа с углублённой подготовкой", "ordinary": "обычная школа"}


def build_generation_prompt(level: Level, domain: Domain, length: LengthGrade,
                            cfg: RenderConfig) -> str:
    """Промпт порождения. В него уходят только формулировки индикаторов уровня."""
    behaviours = "\n".join(f"- {t}" for t in indicator_texts(level))
    prompt = f"""Напиши ответ абитуриента на вопрос интервью: «Расскажите о случае, когда вы вели за собой других».

Пиши от первого лица, как говорит семнадцатилетний абитуриент. Ответ должен
описывать поведение ровно так, как перечислено ниже, и не добавлять поведения,
которого в списке нет:

{behaviours}

Условия рассказа:
- история из области: {domain.topic_nom}
- объём: {_LENGTH_HINT[length]}
- манера речи: {_STYLE_HINT[cfg.style]}
- язык: {_LANG_HINT[cfg.lang]}
- контекст: {_PLACE_HINT[cfg.settlement]}, {_SCHOOL_HINT[cfg.school_type]}
- род говорящего: {"мужской" if cfg.gender == "m" else "женский"}

Не пиши ничего про себя как про кандидата в третьем лице, не рассуждай о качествах
абитуриента вообще, не добавляй заголовков. Верни только JSON: {{"text": "<ответ>"}}"""
    assert_no_judgment_words(prompt)
    return prompt


def _llm_client():
    import anthropic  # локальный импорт: оффлайновый бэкенд не требует SDK

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "нужен ANTHROPIC_API_KEY для --backend llm; "
            "шаблонный бэкенд работает без ключа")
    return anthropic.Anthropic()


def _llm_json(client, prompt: str, temperature: float, max_tokens: int = 1200) -> dict:
    resp = client.messages.create(
        model=GEN_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"LLM вернула не JSON: {raw[:200]}")
    return json.loads(raw[start:end + 1])


def build_corpus_llm(per_level: int = 40, seed: int = SEED,
                     limit: int | None = None) -> list[dict]:
    """Тот же план вариаций, но текст порождает LLM."""
    client = _llm_client()
    rng = random.Random(seed)
    rows: list[dict] = []
    for level in LEVELS:
        domains = _balanced([d.key for d in DOMAINS], per_level, rng)
        styles = _balanced(STYLES, per_level, rng)
        lengths = _balanced(LENGTHS, per_level, rng)
        langs = _balanced(LANGS, per_level, rng)
        settlements = _balanced(SETTLEMENTS, per_level, rng)
        schools = _balanced(SCHOOL_TYPES, per_level, rng)
        genders = _balanced(GENDERS, per_level, rng)
        for i in range(per_level if limit is None else min(limit, per_level)):
            domain = DOMAIN_BY_KEY[domains[i]]
            length = lengths[i]
            cfg = RenderConfig(lang=langs[i], style=styles[i], settlement=settlements[i],
                               school_type=schools[i], gender=genders[i])
            prompt = build_generation_prompt(level, domain, length, cfg)
            text = _llm_json(client, prompt, temperature=1.0)["text"].strip()
            plan = build_plan(level, domain, length, random.Random(seed + i))
            row = _row(f"lead-{level}-{i:02d}", text, level, plan, cfg,
                       length, None, "llm", seed)
            row["variation_meta"]["atola_plan"] = []       # плана нет: текст писала LLM
            row["variation_meta"]["indicator_ids"] = list(indicator_texts(level))
            rows.append(row)
    return rows


_CF_REWRITE = {
    "settlement": "перенеси историю из городской школы в сельскую, изменив только упоминания места и школы",
    "language": "переведи текст на казахский, сохранив все числа и порядок предложений",
    "polish": "аккуратно выправь речь: убери опечатки и разговорные вставки, ничего не добавляя",
    "gender": "измени род говорящего на женский, изменив только формы слов",
}


def llm_counterfactual(text: str, attribute: str) -> str | None:
    """Переписывание одного фонового признака с проверкой сохранения чисел.

    Возвращает None, если LLM изменила факты — тогда пара строится рендером плана.
    """
    client = _llm_client()
    prompt = (
        f"Ниже ответ абитуриента. Задача: {_CF_REWRITE[attribute]}.\n"
        "Все факты, числа, имена, сроки и структура рассказа обязаны сохраниться "
        "дословно. Не добавляй и не убирай ни одного факта.\n\n"
        f"ТЕКСТ:\n{text}\n\nВерни только JSON: {{\"text\": \"<переписанный ответ>\"}}"
    )
    out = _llm_json(client, prompt, temperature=0.0)["text"].strip()
    return out if same_facts(out, text) else None


# --------------------------------------------------------------------------- #
# Ввод-вывод и CLI
# --------------------------------------------------------------------------- #

def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_blind_sample(rows: list[dict], n: int, seed: int = SEED) -> list[dict]:
    """Файл для слепой ручной разметки.

    Метка не записывается: размечающий не должен видеть уровень генератора.
    """
    rng = random.Random(seed + 3)
    sample = rng.sample(rows, min(n, len(rows)))
    return [{"id": r["id"], "text": r["text"], "level_manual": None} for r in sample]


def corpus_meta(rows: list[dict], pairs: list[dict], backend: str, seed: int) -> dict:
    def dist(key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in rows:
            v = str(r["variation_meta"].get(key))
            out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items()))

    return {
        "competency": "leadership",
        "backend": backend,
        "seed": seed,
        "n_answers": len(rows),
        "n_noise": sum(1 for r in rows if r["variation_meta"]["noise"]),
        "n_pairs": len(pairs),
        "levels": {lv: sum(1 for r in rows if r["level"] == lv) for lv in LEVELS},
        "distribution": {k: dist(k) for k in
                         ("domain", "length", "style", "language", "settlement",
                          "school_type", "gender", "noise")},
        "pairs_by_attribute": {a: sum(1 for p in pairs if p["attribute"] == a)
                               for a in CF_ATTRIBUTES},
        "rule": ("в промпт генерации передаются только формулировки индикаторов "
                 "нужного уровня; оценочные слова запрещены и проверяются"),
        "source_rubric": "published AI Leader ID BARS example",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Генерация корпуса «Лидерские способности»")
    ap.add_argument("--backend", choices=("template", "llm"), default="template")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--per-level", type=int, default=40)
    ap.add_argument("--noise", type=int, default=20)
    ap.add_argument("--pairs-per-attribute", type=int, default=10)
    ap.add_argument("--blind-sample", type=int, default=90,
                    help="сколько ответов выгрузить для слепой ручной разметки")
    ap.add_argument("--limit", type=int, default=None,
                    help="ограничить число ответов на уровень (для проверки llm-бэкенда)")
    ap.add_argument("--print-samples", type=int, default=0)
    args = ap.parse_args(argv)

    if args.backend == "llm":
        rows = build_corpus_llm(args.per_level, args.seed, args.limit)
    else:
        rows = build_corpus(args.per_level, args.seed)
    rows += build_noise(args.noise, args.seed)
    pairs = build_pairs(args.pairs_per_attribute, args.seed)

    write_jsonl(CORPUS_FILE, rows)
    write_jsonl(PAIRS_FILE, pairs)
    meta = corpus_meta(rows, pairs, args.backend, args.seed)
    CORPUS_META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    if args.blind_sample:
        write_jsonl(BLIND_FILE, build_blind_sample(rows, args.blind_sample, args.seed))

    print(f"корпус:  {len(rows):3d} ответов -> {CORPUS_FILE.relative_to(Path.cwd())}"
          if CORPUS_FILE.is_relative_to(Path.cwd()) else f"корпус: {len(rows)} ответов")
    for lv in LEVELS:
        n = meta["levels"][lv]
        print(f"   {lv:<7} {n}")
    print(f"шумовые: {meta['n_noise']:3d} "
          f"({', '.join(f'{k}={v}' for k, v in meta['distribution']['noise'].items() if k != 'None')})")
    print(f"пары:    {len(pairs):3d} -> {PAIRS_FILE.name} "
          f"({', '.join(f'{k}={v}' for k, v in meta['pairs_by_attribute'].items())})")
    print(f"слепая разметка: {args.blind_sample} -> {BLIND_FILE.name}")

    for row in rows[:args.print_samples]:
        vm = row["variation_meta"]
        print(f"\n--- {row['id']} [{row['level']}] "
              f"{vm['domain']}/{vm['length']}/{vm['style']}/{vm['language']}/"
              f"{vm['settlement']}/{vm['gender']}\n{row['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
