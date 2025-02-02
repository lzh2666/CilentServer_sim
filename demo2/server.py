import socket
import time
import json
import threading
import hashlib


# 服务器类
class Server:
    # ---------------------上位机初始化----------------------
    def __init__(self, host='127.0.0.1', port=12345):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.clients = []
        self.alarm_active = False
        self.last_sensor_data = {}
        self.private_massage_checksum = 0

    # --------------------------上位机开机----------------------------
    def start(self):
        self.dialog_server('start_server_success', self.host, self.port)
        # print(f"【启动】服务器启动，监听 {self.host}:{self.port}...")
        while True:
            client_socket, client_address = self.server_socket.accept()
            self.dialog_server('start_server_failure', client_address)
            # print(f"【启动】新客户端连接：{client_address}")
            self.clients.append(client_socket)
            # 多线程
            # client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
            # client_thread.start()
            self.handle_client(client_socket)

    # ------------------------校验方法-------------------------
    def compute_checksum(self, data):
        """计算数据的校验和（使用MD5）"""
        # return hashlib.md5(data.encode('utf-8')).hexdigest()
        if isinstance(data, dict):
            data = json.dumps(data)
        return hashlib.md5(data.encode('utf-8')).hexdigest()

    def extract_data_and_checksum(self, message):
        """提取数据和校验和"""
        if "|" in message:
            data, checksum = message.rsplit("|", 1)
            data = json.loads(data)
            return data, checksum
        return {}, ""

    # -----------------------接收处理下位机数据-------------------
    def handle_client(self, client_socket):
        while True:
            try:
                data = client_socket.recv(1024)
                if not data:
                    break

                # 接收并校验下位机数据
                message = data.decode('utf-8')
                self.dialog_server('receive_data_success', message)
                # print(f"【接收】收到下位机数据: {message}")
                sensor_data, received_checksum = self.extract_data_and_checksum(message)
                computed_checksum = self.compute_checksum(sensor_data)

                # 进一步检查校验信息
                if self.private_massage_checksum == computed_checksum or computed_checksum == '\"':
                    self.dialog_server(1)
                    # print("【校验】数据曾校验！读取下一个下位机数据！")
                    # re_send_message = json.dumps({"status": 'next_message', "message": "Send next message!"})
                    # self.compute_checksum(re_send_message)
                    self.send_command_to_client('next_message', True)
                    break

                elif received_checksum != computed_checksum:
                    self.dialog_server(2)
                    # print("【校验】数据校验失败！请求下位机重新发送数据！")
                    # re_send_message = json.dumps({"status": 'resend', "message": "Resend message!"})
                    # self.compute_checksum(re_send_message)
                    self.send_command_to_client('resend', True)
                    continue

                if received_checksum == computed_checksum:
                    self.private_massage_checksum = computed_checksum
                    self.dialog_server(3)
                    # print("【校验】数据校验成功！执行数据处理程序！")

                    # 数据分析
                    self.process_sensor_data(sensor_data)

                    # 发送确认报文
                    if self.alarm_active is True:
                        print('【发送】数据分析/指令发送完毕！等待下位机手动输入解除报警指令...')
                        # self.send_command_to_client('wait_alarm_message', True)
                        continue
                    elif self.alarm_active is False:
                        self.send_command_to_client('success', True)
                        # self.alarm_active = False
                        print('【发送】数据分析/指令发送完毕！等待接收下一组信息...')
                        print('---------------------------------------------------')


            except Exception as e:
                self.dialog_server('process_data_error', e)
                # print(f"【处理】处理客户端数据时出错: {e}")
                break

        client_socket.close()

    # ------------------------数据处理-------------------------
    def process_sensor_data(self, sensor_data):
        """处理下位机上传的传感器数据"""
        if 'alarm_message' in sensor_data:
            # self.send_command_to_client('success', True)
            self.alarm_active = False
            print('【发送】警报已解除！')
            # print('---------------------------------------------------')

        elif sensor_data['fan1'] == 0 and sensor_data['fan2'] == 0:
            self.dialog_server(11)
            # print("【报警】报警：主备风机都关闭！")
            self.alarm_active = True
            self.send_command_to_client('alarm', True)

        elif sensor_data['methane'] > 5.0:
            self.dialog_server(12)
            # print("【报警】甲烷浓度过高，断电开采设备！")
            self.send_command_to_client('cut_power', True)

        # 检查温度和氧气浓度是否需要开启风机
        elif sensor_data['temperature'] > 60 or sensor_data['oxygen'] < 18:
            self.dialog_server(13)
            # print("【警告】温度过高或氧气浓度过低，开启主备风机！")
            self.send_command_to_client('fan', 'both_on')

        # 时间同步
        elif abs(time.time() - sensor_data['timestamp']) > 2:
            self.dialog_server(14)
            # print("【警告】时间误差过大，要求下位机校时！")
            self.send_command_to_client('sync_time', True)



    # -------------------------下发指令--------------------
    def send_command_to_client(self, command, value):
        """发送指令到下位机"""
        for client in self.clients:
            command_data = json.dumps({command: value})
            checksum = self.compute_checksum(command_data)
            message = f"{command_data}|{checksum}"
            client.send(message.encode('utf-8'))





    # ----------------------------日志反馈------------------------
    def dialog_server(self, message_type, A=None, B=None):
        if message_type == 'start_server_success':
            print(f"【启动】服务器启动，监听 {A}:{B}...")
        elif message_type == 'start_server_failure':
            print(f"【启动】新客户端连接：{A}")
        elif message_type == 'receive_data_success':
            print(f"【接收】收到下位机数据: {A}")
        elif message_type == 1:
            print("【校验】数据曾校验！读取下一个下位机数据！")
        elif message_type == 2:
            print("【校验】数据校验失败！请求下位机重新发送数据！")
        elif message_type == 3:
            print("【校验】数据校验成功！执行数据处理程序！")
        elif message_type == 'process_data_error':
            print(f"【处理】处理客户端数据时出错: {A}")
        elif message_type == 11:
            print("【报警】报警：主备风机都关闭！")
        elif message_type == 12:
            print("【报警】甲烷浓度过高，断电开采设备！")
        elif message_type == 13:
            print("【警告】温度过高或氧气浓度过低，开启主备风机！")
        elif message_type == 14:
            print("【警告】时间误差过大，要求下位机校时！")


# 启动服务器
server = Server()
server.start()
