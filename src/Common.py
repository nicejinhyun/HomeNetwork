import datetime
import threading
from functools import partial
from enum import IntEnum, auto, unique

def checkArgumentType(obj, arg):
    if type(obj) == arg:
        return True
    if arg == object:
        return True
    if arg in obj.__class__.__bases__:
        return True
    return False


class Callback(object):
    _args = None

    def __init__(self, *args):
        self._args = args
        self._callbacks = list()

    def connect(self, callback):
        if callback not in self._callbacks:
            self._callbacks.append(callback)
    
    def disconnect(self, callback=None):
        if callback is None:
            self._callbacks.clear()
        else:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def emit(self, *args):
        if len(self._callbacks) == 0:
            return
        if len(args) != len(self._args):
            raise Exception('Callback::Argument Length Mismatch')
        arglen = len(args)
        if arglen > 0:
            validTypes = [checkArgumentType(args[i], self._args[i]) for i in range(arglen)]
            if sum(validTypes) != arglen:
                raise Exception('Callback::Argument Type Mismatch (Definition: {}, Call: {})'.format(self._args, args))
        for callback in self._callbacks:
            callback(*args)


def timestampToString(timestamp: datetime.datetime):
    h = timestamp.hour
    m = timestamp.minute
    s = timestamp.second
    us = timestamp.microsecond
    return '%02d:%02d:%02d.%06d' % (h, m, s, us)


def getCurTimeStr():
    return '<%s>' % timestampToString(datetime.datetime.now())


def writeLog(strMsg: str, obj: object = None):
    strTime = getCurTimeStr()
    if obj is not None:
        if isinstance(obj, threading.Thread):
            if obj.ident is not None:
                strObj = ' [%s (0x%X)]' % (type(obj).__name__, obj.ident)
            else:
                strObj = ' [%s (0x%X)]' % (type(obj).__name__, id(obj))
        else:
            strObj = ' [%s (0x%X)]' % (type(obj).__name__, id(obj))
    else:
        strObj = ''

    msg = strTime + strObj + ' ' + strMsg
    print(msg)


def prettifyPacket(packet: bytearray) -> str:
    return ' '.join(['%02X' % x for x in packet])


class bind(partial):
    # https://stackoverflow.com/questions/7811247/how-to-fill-specific-positional-arguments-with-partial-in-python
    """
    An improved version of partial which accepts Ellipsis (...) as a placeholder
    """
    def __call__(self, *args, **keywords):
        keywords = {**self.keywords, **keywords}
        iargs = iter(args)
        args = (next(iargs) if arg is ... else arg for arg in self.args)
        return self.func(*args, *iargs, **keywords)


@unique
class DeviceType(IntEnum):
    UNKNOWN = 0
    LIGHT = auto()
    OUTLET = auto()
    THERMOSTAT = auto()
    AIRCONDITIONER = auto()
    GASVALVE = auto()
    VENTILATOR = auto()
    ELEVATOR = auto()
    SUBPHONE = auto()
    HEMS = auto()
    BATCHOFFSWITCH = auto()
    DOORLOCK = auto()


@unique
class HEMSDevType(IntEnum):
    Unknown = 0
    Electricity = 1  # 전기
    Water = 2  # 수도
    Gas = 3  # 가스
    HotWater = 4  # 온수
    Heating = 5  # 난방
    Reserved = 10  # ?


@unique
class HEMSCategory(IntEnum):
    Unknown = 0
    History = 1  # 우리집 사용량 이력 (3달간, 단위: kWh/L/MWh)
    OtherAverage = 2  # 동일평수 평균 사용량 이력 (3달간, 단위: kWh/L/MWh)
    Fee = 3  # 요금 이력 (3달간, 단위: 천원)
    CO2 = 4  # CO2 배출량 이력 (3달간, 단위: kg)
    Target = 5  # 목표량
    Current = 7  # 현재 실시간 사용량 

