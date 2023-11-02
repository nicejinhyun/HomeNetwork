import os
import time
import json
import queue
import psutil
import traceback
import psutil
from functools import partial
from typing import List, Union
from collections import OrderedDict
import paho.mqtt.client as mqtt
import xml.etree.ElementTree as ET
import multiprocessing

from Devices import *
from RS485 import *
from Common import *
from Threads import *

CURPATH = os.path.dirname(os.path.abspath(__file__))  # {$PROJECT}/include/
PROJPATH = os.path.dirname(CURPATH)  # {$PROJECT}/

class RS485Info:
    rs485: RS485Comm = None
    config: RS485Config = None
    parser: PacketParser = None
    index: int = 0

    def __init__(self, rs485: RS485Comm, config: RS485Config, parser: PacketParser, index: int):
        self.rs485 = rs485
        self.config = config
        self.parser = parser
        self.index = index

    def __repr__(self) -> str:
        repr_txt = f'<{self.parser.name}({self.__class__.__name__} at {hex(id(self))})'
        repr_txt += f' Index: {self.index}'
        repr_txt += '>'
        return repr_txt

    def release(self):
        if self.rs485 is not None:
            self.rs485.release()
        if self.parser is not None:
            self.parser.release()

class Home:
    name: str = 'Home'
    device_list: List[Device]

    thread_cmd_queue: Union[ThreadCommandQueue, None] = None
    thread_parse_result_queue: Union[ThreadParseResultQueue, None] = None
#    thread_timer: Union[ThreadTimer, None] = None
    queue_command: queue.Queue
    queue_parse_result: queue.Queue

    mqtt_client: mqtt.Client
    mqtt_host: str = '127.0.0.1'
    mqtt_port: int = 1883
    mqtt_is_connected: bool = False
    enable_mqtt_console_log: bool = True
    verbose_mqtt_regular_publish: dict

    rs485_info_list: List[RS485Info]
    rs485_reconnect_limit: int = 60

    def __init__(self, name: str = 'Home'):
        self.name = name
        self.device_list = list()
        self.queue_command = queue.Queue()
        self.queue_parse_result = queue.Queue()
        self.rs485_info_list = list()
        self.parser_mapping = {
            DeviceType.LIGHT: 0,
            DeviceType.OUTLET: 0,
            DeviceType.GASVALVE: 0,
            DeviceType.THERMOSTAT: 0,
            DeviceType.VENTILATOR: 0,
            DeviceType.AIRCONDITIONER: 0,
            DeviceType.ELEVATOR: 0,
            DeviceType.SUBPHONE: 0,
            DeviceType.BATCHOFFSWITCH: 0,
            DeviceType.HEMS: 0,
        }
        self.initialize()

    def initialize(self):
        self.initMQTT()
        self.loadConfig()
        self.initDevices()

        self.startThreadCommandQueue()
        self.startThreadParseResultQueue()

        try:
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
        except Exception as e:
            writeLog('MQTT Connection Error: {}'.format(e), self)
        self.mqtt_client.loop_start()

        writeLog(f'Initialized <{self.name}>', self)

    def initMQTT(self):
        self.mqtt_client = mqtt.Client(client_id="CentralPark")
        self.mqtt_client.on_connect = self.onMqttClientConnect
        self.mqtt_client.on_disconnect = self.onMqttClientDisconnect
        self.mqtt_client.on_subscribe = self.onMqttClientSubscribe
        self.mqtt_client.on_unsubscribe = self.onMqttClientUnsubscribe
        self.mqtt_client.on_publish = self.onMqttClientPublish
        self.mqtt_client.on_message = self.onMqttClientMessage
        self.mqtt_client.on_log = self.onMqttClientLog

    def loadConfig(self):
        if not os.path.isfile('options.json'):
            return
        with open('options.json') as jsonFile:
            jsonData = json.load(jsonFile)

            commType = jsonData['RS485']['type']

            cfg = RS485Config()
            cfg.enable = True
            cfg.comm_type = RS485HwType(RS485HwType.Socket)
            cfg.socket_ipaddr = jsonData['Socket']['server']
            cfg.socket_port = jsonData['Socket']['port']
            cfg.check_connection = 1
            rs485 = RS485Comm(f'RS485-Main')
            parser = PacketParser(rs485, 'Main', 0, ParserType.REGULAR)
            parser.setBufferSize(64)
            parser.sig_parse_result.connect(lambda x: self.queue_parse_result.put(x))
            self.rs485_info_list.append(RS485Info(rs485, cfg, parser, 0))
            writeLog(f"Create RS485 Instance (name: Main)")

            username = jsonData['Mqtt']['username']
            password = jsonData['Mqtt']['password']
            self.mqtt_host = jsonData['Mqtt']['server']
            self.mqtt_port = jsonData['Mqtt']['port']
            self.mqtt_client.username_pw_set(username, password)
            self.enable_mqtt_console_log = True

            self.verbose_mqtt_regular_publish = dict()
            self.verbose_mqtt_regular_publish['enable'] = True
            self.verbose_mqtt_regular_publish['interval'] = 100

            self.parser_mapping[DeviceType.LIGHT] = 0
            self.parser_mapping[DeviceType.OUTLET] = 0
            self.parser_mapping[DeviceType.GASVALVE] = 0
            self.parser_mapping[DeviceType.THERMOSTAT] = 0
            self.parser_mapping[DeviceType.VENTILATOR] = 0
            self.parser_mapping[DeviceType.AIRCONDITIONER] = 0
            self.parser_mapping[DeviceType.ELEVATOR] = 0
            self.parser_mapping[DeviceType.SUBPHONE] = 0
            self.parser_mapping[DeviceType.BATCHOFFSWITCH] = 0
            self.parser_mapping[DeviceType.HEMS] = 0

            for deviceName, _ in jsonData['Devices'].items():
                items = jsonData[deviceName]
                for item in items:
                    device: Device = None
                    name = item['name']
                    index = item['index']
                    room = item['room']
                    if deviceName == 'Light':
                        device = Light(name, index, room)
                    elif deviceName == 'Thermostat':
                        device = Thermostat(name, index, room)
                        range_min = item.get('range_min')
                        range_max = item.get('range_max')
                        device.setTemperatureRange(range_min, range_max)
                    elif deviceName == 'Airconditioner':
                        device = AirConditioner(name, index, room)
                        range_min = item.get('range_min')
                        range_max = item.get('range_max')
                        device.setTemperatureRange(range_min, range_max)
                    elif deviceName == 'GasValve':
                        device = GasValve(name, index, room)
                    elif deviceName == 'Ventilator':
                        device = Ventilator(name, index, room)
                    elif deviceName == 'Elevator':
                        device = Elevator(name, index, room)
                    elif deviceName == 'Batchoffsw':
                        device = BatchOffSwitch(name, index, room)
                    elif deviceName == 'HEMS':
                        device = HEMS(name, index, room)
                 
                    if device is not None:
                        if self.findDevice(device.getType(), device.getIndex(), device.getRoomIndex()) is None:
                            self.device_list.append(device)
                        else:
                            writeLog(f"Already Exist! {str(device)}", self)

    def initDevices(self):
        for dev in self.device_list:
            dev.setMqttClient(self.mqtt_client)
            dev.sig_set_state.connect(partial(self.onDeviceSetState, dev))

    def release(self):       
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        del self.mqtt_client

        for elem in self.rs485_info_list:
            elem.release()
        for dev in self.device_list:
            dev.release()

        writeLog(f'Released', self)

    def initRS485Connection(self):
        for elem in self.rs485_info_list:
            cfg = elem.config
            rs485 = elem.rs485
            name = elem.parser.name
            try:
                if cfg.enable:
                    rs485.setType(cfg.comm_type)
                    if cfg.comm_type == RS485HwType.Serial:
                        port, baud = cfg.serial_port, cfg.serial_baud
                        databit, parity, stopbits = cfg.serial_databit, cfg.serial_parity, cfg.serial_stopbits
                        rs485.connect(port, baud, bytesize=databit, parity=parity, stopbits=stopbits)
                    elif cfg.comm_type == RS485HwType.Socket:
                        ipaddr, port = cfg.socket_ipaddr, cfg.socket_port
                        rs485.connect(ipaddr, port)
                else:
                    writeLog(f"rs485 '{name}' is disabled", self)
            except Exception as e:
                writeLog(f"Failed to initialize '{name}' rs485 connection ({e})", self)
                continue

    def startThreadCommandQueue(self):
        if self.thread_cmd_queue is None:
            self.thread_cmd_queue = ThreadCommandQueue(self.queue_command)
            self.thread_cmd_queue.sig_terminated.connect(self.onThreadCommandQueueTerminated)
            self.thread_cmd_queue.daemon = True
            self.thread_cmd_queue.start()

    def stopThreadCommandQueue(self):
        if self.thread_cmd_queue is not None:
            self.thread_cmd_queue.stop()

    def onThreadCommandQueueTerminated(self):
        del self.thread_cmd_queue
        self.thread_cmd_queue = None

    def startThreadParseResultQueue(self):
        if self.thread_parse_result_queue is None:
            self.thread_parse_result_queue = ThreadParseResultQueue(self.queue_parse_result)
            self.thread_parse_result_queue.sig_get.connect(self.handlePacketParseResult)
            self.thread_parse_result_queue.sig_terminated.connect(self.onThreadParseResultQueueTerminated)
            self.thread_parse_result_queue.daemon = True
            self.thread_parse_result_queue.start()
    
    def stopThreadParseResultQueue(self):
        if self.thread_parse_result_queue is not None:
            self.thread_parse_result_queue.stop()

    def onThreadParseResultQueueTerminated(self):
        del self.thread_parse_result_queue
        self.thread_parse_result_queue = None

    def command(self, **kwargs):
        try:
            dev: Device = kwargs['device']
            dev_type: DeviceType = dev.getType()
            index = self.parser_mapping.get(dev_type)
            info: RS485Info = self.rs485_info_list[index]
            kwargs['parser'] = info.parser
        except Exception as e:
            writeLog('command Exception::{}'.format(e), self)
        self.queue_command.put(kwargs)

    def onDeviceSetState(self, dev: Device, state: int):
        if isinstance(dev, AirConditioner):
            self.command(
                device=dev,
                category='active',
                target=state
            )
        elif isinstance(dev, Thermostat):
            self.command(
                device=dev,
                category='state',
                target='HEAT' if state else 'OFF'
            )

    def startMqttSubscribe(self):
        self.mqtt_client.subscribe('home/command/system')
        for dev in self.device_list:
            self.mqtt_client.subscribe(dev.mqtt_subscribe_topic)

    def onMqttClientConnect(self, _, userdata, flags, rc):
        if self.enable_mqtt_console_log:
            writeLog('Mqtt Client Connected: {}, {}, {}'.format(userdata, flags, rc), self)
        """
        0: Connection successful
        1: Connection refused - incorrect protocol version
        2: Connection refused - invalid client identifier
        3: Connection refused - server unavailable
        4: Connection refused - bad username or password
        5: Connection refused - not authorised
        """
        if rc == 0:
            self.mqtt_is_connected = True
            self.startMqttSubscribe()
        else:
            self.mqtt_is_connected = False

    def onMqttClientDisconnect(self, _, userdata, rc):
        self.mqtt_is_connected = False
        if self.enable_mqtt_console_log:
            writeLog('Mqtt Client Disconnected: {}, {}'.format(userdata, rc), self)

    def onMqttClientPublish(self, _, userdata, mid):
        if self.enable_mqtt_console_log:
            writeLog('Mqtt Client Publish: {}, {}'.format(userdata, mid), self)

    def onMqttClientMessage(self, _, userdata, message):
        """
        Homebridge Publish, App Subscribe
        사용자에 의한 명령 MQTT 토픽 핸들링
        """
        try:
            if self.enable_mqtt_console_log:
                writeLog('Mqtt Client Message: {}, {}'.format(userdata, message), self)
            topic = message.topic
            msg_dict = json.loads(message.payload.decode("utf-8"))
            writeLog(f'MQTT Message: {topic}: {msg_dict}', self)
            if 'command/system' in topic:
                self.onMqttCommandSystem(topic, msg_dict)
            if 'command/light' in topic:
                self.onMqttCommandLight(topic, msg_dict)
            if 'command/outlet' in topic:
                self.onMqttCommandOutlet(topic, msg_dict)
            if 'command/gasvalve' in topic:
                self.onMqttCommandGasvalve(topic, msg_dict)
            if 'command/thermostat' in topic:
                self.onMqttCommandThermostat(topic, msg_dict)
            if 'command/ventilator' in topic:
                self.onMqttCommandVentilator(topic, msg_dict)
            if 'command/airconditioner' in topic:
                self.onMqttCommandAirconditioner(topic, msg_dict)
            if 'command/elevator' in topic:
                self.onMqttCommandElevator(topic, msg_dict)
            if 'command/subphone' in topic:
                self.onMqttCommandSubPhone(topic, msg_dict)
            if 'command/thinq' in topic:
                self.onMqttCommandThinq(topic, msg_dict)
            if 'command/batchoffsw' in topic:
                self.onMqttCommandBatchOffSwitch(topic, msg_dict)
            """
            if 'command/doorlock' in topic:
                self.onMqttCommandDookLock(topic, msg_dict)
            """
        except Exception as e:
            writeLog(f"onMqttClientMessage Exception ({e}).. topic='{message.topic}', payload='{message.payload}'", self)

    def onMqttClientLog(self, _, userdata, level, buf):
        if self.enable_mqtt_console_log:
            writeLog('Mqtt Client Log: {}, {}, {}'.format(userdata, level, buf), self)

    def onMqttClientSubscribe(self, _, userdata, mid, granted_qos):
        if self.enable_mqtt_console_log:
            writeLog('Mqtt Client Subscribe: {}, {}, {}'.format(userdata, mid, granted_qos), self)

    def onMqttClientUnsubscribe(self, _, userdata, mid):
        if self.enable_mqtt_console_log:
            writeLog('Mqtt Client Unsubscribe: {}, {}'.format(userdata, mid), self)

    def onMqttCommandSystem(self, _: str, message: dict):
        if 'query_all' in message.keys():
            writeLog('Got query all command', self)
            self.publish_all()
        if 'restart' in message.keys():
            writeLog('Got restart command', self)
            self.restart()
        if 'reboot' in message.keys():
            os.system('sudo reboot')
        if 'publish_interval' in message.keys():
            try:
                interval = message['publish_interval']
                self.thread_timer.setMqttPublishInterval(interval)
            except Exception:
                pass
        if 'send_packet' in message.keys():
            try:
                idx = message.get('index')
                packet_str = message.get('packet')
                packet = bytearray([int(x, 16) for x in packet_str.split(' ')])
                self.rs485_info_list[idx].rs485.sendData(packet)
            except Exception:
                pass
        if 'clear_console' in message.keys():
            os.system('clear')

    def onMqttCommandLight(self, topic: str, message: dict):
        splt = topic.split('/')
        try:
            room_idx = int(splt[-2])
            dev_idx = int(splt[-1])
        except Exception as e:
            writeLog(f'onMqttCommandLight::topic template error ({e}, {topic})', self)
            room_idx, dev_idx = 0, 0
        device = self.findDevice(DeviceType.LIGHT, dev_idx, room_idx)
        if device is not None:
            if 'state' in message.keys():
                self.command(
                    device=device,
                    category='state',
                    target=message['state']
                )

    def onMqttCommandOutlet(self, topic: str, message: dict):
        splt = topic.split('/')
        try:
            room_idx = int(splt[-2])
            dev_idx = int(splt[-1])
        except Exception as e:
            writeLog(f'onMqttCommandOutlet::topic template error ({e}, {topic})', self)
            room_idx, dev_idx = 0, 0
        device = self.findDevice(DeviceType.OUTLET, dev_idx, room_idx)
        if device is not None:
            if 'state' in message.keys():
                self.command(
                    device=device,
                    category='state',
                    target=message['state']
                )

    def onMqttCommandGasvalve(self, topic: str, message: dict):
        splt = topic.split('/')
        try:
            room_idx = int(splt[-2])
            dev_idx = int(splt[-1])
        except Exception as e:
            writeLog(f'onMqttCommandGasvalve::topic template error ({e}, {topic})', self)
            room_idx, dev_idx = 0, 0
        device = self.findDevice(DeviceType.GASVALVE, dev_idx, room_idx)
        if device is not None:
            if 'state' in message.keys():
                self.command(
                    device=device,
                    category='state',
                    target=message['state']
                )

    def onMqttCommandThermostat(self, topic: str, message: dict):
        splt = topic.split('/')
        try:
            room_idx = int(splt[-2])
            dev_idx = int(splt[-1])
        except Exception as e:
            writeLog(f'onMqttCommandThermostat::topic template error ({e}, {topic})', self)
            room_idx, dev_idx = 0, 0
        device = self.findDevice(DeviceType.THERMOSTAT, dev_idx, room_idx)
        if device is not None:
            if 'state' in message.keys():
                self.command(
                    device=device,
                    category='state',
                    target=message['state']
                )
            if 'targetTemperature' in message.keys():
                self.command(
                    device=device,
                    category='temperature',
                    target=message['targetTemperature']
                )
            if 'timer' in message.keys():
                if message['timer']:
                    device.startTimerOnOff()
                else:
                    device.stopTimerOnOff()

    def onMqttCommandVentilator(self, topic: str, message: dict):
        splt = topic.split('/')
        try:
            room_idx = int(splt[-2])
            dev_idx = int(splt[-1])
        except Exception as e:
            writeLog(f'onMqttCommandVentilator::topic template error ({e}, {topic})', self)
            room_idx, dev_idx = 0, 0
        device = self.findDevice(DeviceType.VENTILATOR, dev_idx, room_idx)
        if device is not None:
            if 'state' in message.keys():
                self.command(
                    device=device,
                    category='state',
                    target=message['state']
                )
            if 'rotationspeed' in message.keys():
                if device.state == 1:
                    # 전원이 켜져있을 경우에만 풍량설정 가능하도록..
                    # 최초 전원 ON시 풍량 '약'으로 설정!
                    self.command(
                        device=device,
                        category='rotationspeed',
                        target=message['rotationspeed']
                    )

    def onMqttCommandAirconditioner(self, topic: str, message: dict):
        splt = topic.split('/')
        try:
            room_idx = int(splt[-2])
            dev_idx = int(splt[-1])
        except Exception as e:
            writeLog(f'onMqttCommandAirconditioner::topic template error ({e}, {topic})', self)
            room_idx, dev_idx = 0, 0
        device = self.findDevice(DeviceType.AIRCONDITIONER, dev_idx, room_idx)
        if device is not None:
            if 'active' in message.keys():
                self.command(
                    device=device,
                    category='active',
                    target=message['active']
                )
            if 'targetTemperature' in message.keys():
                self.command(
                    device=device,
                    category='temperature',
                    target=message['targetTemperature']
                )
            if 'rotationspeed' in message.keys():
                self.command(
                    device=device,
                    category='rotationspeed',
                    target=message['rotationspeed']
                )
            if 'rotationspeed_name' in message.keys():  # for HA
                speed_dict = {'Max': 100, 'Medium': 75, 'Min': 50, 'Auto': 25}
                target = speed_dict[message['rotationspeed_name']]
                self.command(
                    device=device,
                    category='rotationspeed',
                    target=target
                )
            if 'timer' in message.keys():
                if message['timer']:
                    device.startTimerOnOff()
                else:
                    device.stopTimerOnOff()

    def onMqttCommandElevator(self, topic: str, message: dict):
        splt = topic.split('/')
        try:
            room_idx = int(splt[-2])
            dev_idx = int(splt[-1])
        except Exception as e:
            writeLog(f'onMqttCommandElevator::topic template error ({e}, {topic})', self)
            room_idx, dev_idx = 0, 0
        device = self.findDevice(DeviceType.ELEVATOR, dev_idx, room_idx)
        if device is not None:
            if 'state' in message.keys():
                self.command(
                    device=device,
                    category='state',
                    target=message['state']
                )
    
    def onMqttCommandSubPhone(self, topic: str, message: dict):
        splt = topic.split('/')
        try:
            room_idx = int(splt[-2])
            dev_idx = int(splt[-1])
        except Exception as e:
            writeLog(f'onMqttCommandSubPhone::topic template error ({e}, {topic})', self)
            room_idx, dev_idx = 0, 0
        device = self.findDevice(DeviceType.SUBPHONE, dev_idx, room_idx)
        if device is not None:
            if 'streaming_state' in message.keys():
                self.command(
                    device=device,
                    category='streaming',
                    target=message['streaming_state']
                )
            if 'doorlock_state' in message.keys():
                self.command(
                    device=device,
                    category='doorlock',
                    target=message['doorlock_state']
                )

    def onMqttCommandThinq(self, _: str, message: dict):
        if self.thinq is None:
            return
        if 'restart' in message.keys():
            self.thinq.restart()
            return
        if 'log_mqtt_message' in message.keys():
            self.thinq.setEnableLogMqttMessage(bool(int(message.get('log_mqtt_message'))))

    def onMqttCommandBatchOffSwitch(self, topic: str, message: dict):
        splt = topic.split('/')
        try:
            room_idx = int(splt[-2])
            dev_idx = int(splt[-1])
        except Exception as e:
            writeLog(f'onMqttCommandBatchOffSwitch::topic template error ({e}, {topic})', self)
            room_idx, dev_idx = 0, 0
        device = self.findDevice(DeviceType.BATCHOFFSWITCH, dev_idx, room_idx)
        if device is not None:
            if 'state' in message.keys():
                self.command(
                    device=device,
                    category='state',
                    target=message['state']
                )

    def publish_all(self):
        for dev in self.device_list:
            try:
                dev.publishMQTT()
            except ValueError as e:
                writeLog(f'{e}: {dev}, {dev.mqtt_publish_topic}', self)

    def handlePacketParseResult(self, result: dict):
        self.updateDeviceState(result)

    def findDevice(self, dev_type: DeviceType, index: int, room_index: int) -> Device:
        find = list(filter(lambda x: 
            x.getType() == dev_type and x.getIndex() == index and x.getRoomIndex() == room_index, 
            self.device_list))
        if len(find) == 1:
            return find[0]
        return None    

    def findDevices(self, dev_type: DeviceType) -> List[Device]:
        return list(filter(lambda x: x.getType() == dev_type, self.device_list))

    def updateDeviceState(self, result: dict):
        try:
            dev_type: DeviceType = result.get('device')
            dev_idx: int = result.get('index')
            if dev_idx is None:
                dev_idx = 0
            room_idx: int = result.get('room_index')
            if room_idx is None:
                room_idx = 0
            device = self.findDevice(dev_type, dev_idx, room_idx)
            if device is None:
                writeLog(f'updateDeviceState::Device is not registered ({dev_type.name}, idx={dev_idx}, room={room_idx})', self)
                return
            
            if dev_type in [DeviceType.LIGHT, DeviceType.OUTLET, DeviceType.GASVALVE, DeviceType.BATCHOFFSWITCH]:
                state = result.get('state')
                device.updateState(state)
            elif dev_type is DeviceType.THERMOSTAT:
                state = result.get('state')
                temp_current = result.get('temp_current')
                temp_config = result.get('temp_config')
                device.updateState(
                    state, 
                    temp_current=temp_current, 
                    temp_config=temp_config
                )
            elif dev_type is DeviceType.AIRCONDITIONER:
                state = result.get('state')
                temp_current = result.get('temp_current')
                temp_config = result.get('temp_config')
                mode = result.get('mode')
                rotation_speed = result.get('rotation_speed')
                device.updateState(
                    state,
                    temp_current=temp_current, 
                    temp_config=temp_config,
                    mode=mode,
                    rotation_speed=rotation_speed
                )
            elif dev_type is DeviceType.VENTILATOR:
                state = result.get('state')
                rotation_speed = result.get('rotation_speed')
                device.updateState(state, rotation_speed=rotation_speed)
            elif dev_type is DeviceType.ELEVATOR:
                state = result.get('state')
                device.updateState(
                    state, 
                    data_type=result.get('data_type'),
                    ev_dev_idx=result.get('ev_dev_idx'),
                    direction=result.get('direction'),
                    floor=result.get('floor')
                )
            elif dev_type is DeviceType.SUBPHONE:
                device.updateState(
                    0, 
                    ringing_front=result.get('ringing_front'),
                    ringing_communal=result.get('ringing_communal'),
                    streaming=result.get('streaming'),
                    doorlock=result.get('doorlock')
                )
            elif dev_type is DeviceType.HEMS:
                result.pop('device')
                device.updateState(
                    0,
                    monitor_data=result
                )
            elif dev_type is DeviceType.DOORLOCK:
                pass
        except Exception as e:
            writeLog('updateDeviceState::Exception::{} ({})'.format(e, result), self)

    def joinThread(self):
        for elem in self.rs485_info_list:
            rs485 = elem.rs485
            rs485.joinThread()

        return False

home_: Union[Home, None] = None

def get_home(name: str = '') -> Home:
    global home_
    if home_ is None:
        home_ = Home(name=name)
    return home_

if __name__ == "__main__":
    keepAlive = True
    home_obj = get_home('CentralPark')
    home_obj.initRS485Connection()

    while keepAlive:
        keepAlive = False
        if not home_obj.joinThread():
            writeLog('[Error] Connection lost... reconnect after 1 min')
            time.sleep(60)
            keepAlive = True