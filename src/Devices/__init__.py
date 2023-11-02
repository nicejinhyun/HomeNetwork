import os
import sys
CURPATH = os.path.dirname(os.path.abspath(__file__))
sys.path.extend([CURPATH])
sys.path = list(set(sys.path))
del CURPATH

from Device import Device
from Light import Light
from Thermostat import Thermostat
from AirConditioner import AirConditioner
from GasValve import GasValve
from Ventilator import Ventilator
from Elevator import Elevator
from BatchOffSwitch import BatchOffSwitch
from HEMS import HEMS