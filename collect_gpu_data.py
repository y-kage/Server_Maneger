import atexit
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import mysql.connector
import paramiko
from mysql.connector import Error


def load_servers_from_json(json_file):
    with open(json_file, "r") as file:
        return json.load(file)["servers"]


servers = load_servers_from_json("server_list.json")


def get_mysql_connection():
    while True:
        try:
            connection = mysql.connector.connect(
                host="localhost",
                user="root",  # MySQLのユーザー名
                password="hvrl",  # MySQLのパスワード
                database="Server_GPU_Usage",  # データベース名
            )
            if connection.is_connected():
                print("MySQL server is up and running.")
                connection.close()
                break
        except Error as e:
            print(f"Waiting for MySQL server to start... Error: {e}")
            time.sleep(5)

    return mysql.connector.connect(
        host="localhost",
        user="root",  # MySQLのユーザー名
        password="hvrl",  # MySQLのパスワード
        database="Server_GPU_Usage",  # データベース名
    )


def insert_data_to_mysql(cursor, connection, result):
    try:
        host_name = result["Name"]
        host_ip = result["hostip"]
        nvidia_info = result["nvidia_smi_output"]
        timestamp = result["timestamp"]

        for i in range(len(nvidia_info)):
            _data = nvidia_info[i]
            _data = _data.split(",")
            for k in range(len(_data)):
                if _data[k][0] == " ":
                    _data[k] = _data[k][1:]

                if k == 1 or k == 9:
                    pass
                elif k == 4 or k == 5:
                    _data[k] = float(_data[k])
                    _data[k] = int(_data[k])
                else:
                    _data[k] = int(_data[k])
            (
                gpu_index,
                gpu_name,
                fan_speed,
                temperature,
                power_usage,
                power_capacity,
                memory_usage,
                memory_capacity,
                gpu_utilization,
                _,
            ) = _data

            # SQLクエリを作成
            sql = """
                INSERT INTO gpu_usage (
                    host_name, host_ip, gpu_index, gpu_name, fan_speed, temperature,
                    power_usage, power_capacity, memory_usage, memory_capacity,
                    gpu_utilization, timestamp
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """
            data = (
                host_name,
                host_ip,
                gpu_index,
                gpu_name,
                fan_speed,
                temperature,
                power_usage,
                power_capacity,
                memory_usage,
                memory_capacity,
                gpu_utilization,
                timestamp,
            )

            # データベースに挿入
            cursor.execute(sql, data)
            connection.commit()
    except:
        print(f"Error: Cannot insert data {host_name}")


def execute_nvidia_smi_csv(Name, hostip, username, password):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostip, username=username, password=password)

        # command = "nvidia-smi"
        command = "nvidia-smi --query-gpu=index,name,fan.speed,temperature.gpu,power.draw,power.limit,memory.used,memory.total,utilization.gpu,timestamp --format=csv,noheader,nounits"
        stdin, stdout, stderr = client.exec_command(command)
        result = stdout.read().decode("utf-8").strip()
        result = result.split("\n")
        client.close()

        result_str = "\n".join(result).lower()  # 小文字に変換して検索
        if "fail" in result_str:
            raise Exception(f"Command output contains 'fail' for {Name}")
        if "error" in result_str:
            raise Exception(f"Command output contains 'error' for {Name}")
        if "detected" in result_str:
            raise Exception(f"Command output contains 'no gpu detected' for {Name}")

        return {
            "Name": Name,
            "hostip": hostip,
            "nvidia_smi_output": result,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"Error connecting to {hostip}: {e}")
        return {
            "Name": Name,
            "hostip": hostip,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def get_all_gpu_status_csv():
    results = []
    with ThreadPoolExecutor(max_workers=len(servers)) as executor:
        futures = [
            executor.submit(
                execute_nvidia_smi_csv,
                srv["Name"],
                srv["hostip"],
                srv["username"],
                srv["password"],
            )
            for srv in servers
        ]
        for future in futures:
            results.append(future.result())

    return results


stop_event = threading.Event()


# 定期的にデータを取得してログを残す
def schedule_data_collection():
    while not stop_event.is_set():
        connection = get_mysql_connection()
        cursor = connection.cursor()
        results = get_all_gpu_status_csv()
        for result in results:
            if "error" not in result:
                # MySQLにデータを保存
                insert_data_to_mysql(cursor, connection, result)
                print(
                    f"Data inserted into MySQL for {result['Name']} at {result['timestamp']}"
                )
        cursor.close()
        connection.close()
        # time.sleep(60)
        time.sleep(1800)
        if os.path.exists("log_app_mysql.txt"):
            with open("log_app_mysql.txt", "w") as f:
                pass
        if os.path.exists("log_collect_gpu_data.txt"):
            with open("log_collect_gpu_data.txt", "w") as f:
                pass


# データ収集スレッドを開始
threading.Thread(target=schedule_data_collection, daemon=True).start()


def cleanup():
    stop_event.set()


atexit.register(cleanup)

if __name__ == "__main__":
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()
