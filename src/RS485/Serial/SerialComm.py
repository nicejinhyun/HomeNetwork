import queue
import serial
# import serial.rs485
import datetime
from typing import Union
from SerialThreads import *


class SerialComm:
    _name: str = 'SerialComm'
    _serial: serial.Serial
    _threadSend: Union[ThreadSend, None] = None
    _threadRecv: Union[ThreadReceive, None] = None
    _threadCheck: Union[ThreadCheckRecvQueue, None] = None