import atexit
import base64
import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import BytesIO, StringIO

import matplotlib.pyplot as plt
import mysql.connector
import pandas as pd
import paramiko
from flask import Flask, jsonify, redirect, request, send_from_directory
from sqlalchemy import create_engine

app = Flask(__name__)


# サーバーの情報を外部のJSONファイルから読み込む関数
def load_servers_from_json(json_file):
    with open(json_file, "r") as file:
        return json.load(file)["servers"]


# 外部JSONファイルからサーバー情報をロード
servers = load_servers_from_json("server_list.json")


# MySQL接続設定
def get_mysql_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",  # MySQLのユーザー名
        password="hvrl",  # MySQLのパスワード
        database="Server_GPU_Usage",  # データベース名
    )


def get_mysql_connection_for_pandas():
    # SQLAlchemyの接続URIを作成
    connection_string = "mysql+mysqlconnector://root:hvrl@localhost/Server_GPU_Usage"
    engine = create_engine(connection_string)
    return engine


def fetch_memory_usage(server_name):
    connection = get_mysql_connection_for_pandas()
    # query = """
    #     SELECT timestamp, gpu_index, gpu_name, memory_usage, memory_capacity
    #     FROM gpu_usage
    #     WHERE host_name = %s AND timestamp >= NOW() - INTERVAL 3 HOUR
    #     AND MOD(MINUTE(timestamp), 5) = 0
    #     ORDER BY timestamp;
    # """
    # query = """
    #     SELECT timestamp, gpu_index, gpu_name, memory_usage, memory_capacity
    #     FROM gpu_usage
    #     WHERE host_name = %s AND timestamp >= NOW() - INTERVAL 24 HOUR
    #     ORDER BY timestamp;
    # """
    query = """
        SELECT timestamp, gpu_index, gpu_name, memory_usage, memory_capacity
        FROM gpu_usage
        WHERE host_name = %s AND timestamp >= NOW() - INTERVAL 1 YEAR
        ORDER BY timestamp;
    """
    df = pd.read_sql(query, connection, params=(server_name,))
    # connection.close()
    return df


def plot_memory_usage(df, save_path):
    plt.figure(figsize=(10, 5))

    # GPUごとに異なる色でプロット
    unique_gpus = df["gpu_index"].unique()
    colors = plt.cm.get_cmap("tab10", len(unique_gpus))  # 色のマップを取得

    for i, gpu in enumerate(unique_gpus):
        gpu_data = df[df["gpu_index"] == gpu]
        memory_usage_ratio = (
            gpu_data["memory_usage"] / gpu_data["memory_capacity"]
        ) * 100
        gpu_name = gpu_data["gpu_name"].iloc[0]
        _label = f"{gpu}: {gpu_name}"

        plt.plot(
            gpu_data["timestamp"],
            memory_usage_ratio,
            marker="o",
            linestyle="-",
            color=colors(i),
            label=_label,
        )

    plt.title(f"Memory Usage Ratio for All GPUs")
    plt.xlabel("Time")
    plt.ylabel("Memory Usage Ratio (%)")
    plt.xticks(rotation=45)
    plt.ylim([-5, 105])
    plt.legend()
    plt.grid()
    plt.tight_layout()
    plt.savefig(save_path)  # 画像を保存
    plt.close()  # グラフを閉じる
    # plt.show()


def fetch_gpu_temp(server_name):
    connection = get_mysql_connection_for_pandas()
    # query = """
    #     SELECT timestamp, gpu_index, gpu_name, memory_usage, memory_capacity
    #     FROM gpu_usage
    #     WHERE host_name = %s AND timestamp >= NOW() - INTERVAL 3 HOUR
    #     AND MOD(MINUTE(timestamp), 5) = 0
    #     ORDER BY timestamp;
    # """
    # query = """
    #     SELECT timestamp, gpu_index, gpu_name, memory_usage, memory_capacity
    #     FROM gpu_usage
    #     WHERE host_name = %s AND timestamp >= NOW() - INTERVAL 24 HOUR
    #     ORDER BY timestamp;
    # """
    query = """
        SELECT timestamp, gpu_index, gpu_name, temperature
        FROM gpu_usage
        WHERE host_name = %s AND timestamp >= NOW() - INTERVAL 3 MONTH
        ORDER BY timestamp;
    """
    df = pd.read_sql(query, connection, params=(server_name,))
    # connection.close()
    return df


def plot_gpu_temp(df, save_path):
    plt.figure(figsize=(10, 5))

    # GPUごとに異なる色でプロット
    unique_gpus = df["gpu_index"].unique()
    colors = plt.cm.get_cmap("Set2", len(unique_gpus))  # 色のマップを取得

    for i, gpu in enumerate(unique_gpus):
        gpu_data = df[df["gpu_index"] == gpu]
        gpu_name = gpu_data["gpu_name"].iloc[0]
        _label = f"{gpu}: {gpu_name}"

        plt.plot(
            gpu_data["timestamp"],
            gpu_data["temperature"],
            marker="o",
            linestyle="-",
            color=colors(i),
            label=_label,
        )

    plt.title(f"Temperature for All GPUs")
    plt.xlabel("Time")
    plt.ylabel("Temperature (°C)")
    plt.xticks(rotation=45)
    plt.ylim([10, 110])
    plt.legend()
    plt.grid()
    plt.tight_layout()
    plt.savefig(save_path)  # 画像を保存
    plt.close()


# SSH経由でnvidia-smiを実行して結果を取得する関数
def execute_nvidia_smi(Name, hostip, username, password):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostip, username=username, password=password)

        command = "nvidia-smi"
        # command = "nvidia-smi --query-gpu=index,name,fan.speed,temperature.gpu,power.draw,power.limit,memory.used,memory.total,utilization.gpu,timestamp --format=csv,noheader,nounits"
        stdin, stdout, stderr = client.exec_command(command)
        result = stdout.read().decode("utf-8").strip()
        client.close()

        result_str = "\n".join(result.split("\n")).lower()  # 小文字に変換して検索
        if "fail" in result_str:
            raise Exception(f"Command output contains 'fail' for {Name}")
        if "error" in result_str:
            raise Exception(f"Command output contains 'error' for {Name}")
        if "detected" in result_str:
            raise Exception(f"Command output contains 'no gpu detected' for {Name}")

        return {
            "Name": Name,
            "hostip": hostip,
            "output": result,
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


# SSH経由でnvidia-smiを実行して結果を取得する関数
def execute_df(Name, hostip, username, password):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostip, username=username, password=password)

        command = "df -h"
        stdin, stdout, stderr = client.exec_command(command)
        result = stdout.read().decode("utf-8").strip()
        client.close()

        result_str = "\n".join(result.split("\n")).lower()  # 小文字に変換して検索
        if "fail" in result_str:
            raise Exception(f"Command output contains 'fail' for {Name}")
        if "error" in result_str:
            raise Exception(f"Command output contains 'error' for {Name}")
        if "detected" in result_str:
            raise Exception(f"Command output contains 'no gpu detected' for {Name}")

        return {
            "Name": Name,
            "hostip": hostip,
            "output": result,
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


# 複数のサーバーにnvidia-smiを並列で実行する関数
def get_all_gpu_status():
    results = []
    with ThreadPoolExecutor(max_workers=len(servers)) as executor:
        futures = [
            executor.submit(
                execute_nvidia_smi,
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


def get_all_storage():
    results = []
    with ThreadPoolExecutor(max_workers=len(servers)) as executor:
        futures = [
            executor.submit(
                execute_df,
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


# ルートにアクセスされたときに /status にリダイレクト
@app.route("/")
def index():
    return redirect("/status")


# リクエストされたときにGPU情報を更新
@app.route("/update_gpu_status", methods=["POST"])
def update_gpu_status():
    results = get_all_gpu_status()
    return jsonify(results), 200


# # ブラウザでアクセスされたときに全サーバーのGPU情報を表示
# @app.route("/status", methods=["GET"])
# def status():
#     results = get_all_gpu_status()

#     html_content = "<h1>GPU Status of Multiple Servers</h1>"
#     for result in results:
#         if "error" in result:
#             html_content += f"<h2>{result['Name']}: {result['hostip']}</h2>"
#             html_content += f"<p style='color:red;'>Error: {result['error']}</p>"
#         else:
#             html_content += f"<h2>{result['Name']}: {result['hostip']}</h2>"
#             html_content += f"<pre>{result['nvidia_smi_output']}</pre>"
#             html_content += f"<p>Last Update: {result['timestamp']}</p>"

#     return html_content


# ブラウザでアクセスされたときに全サーバーのGPU情報を表示
@app.route("/status", methods=["GET"])
def status():
    # staticフォルダ内の画像をすべて削除（作成から1時間以上経過したもの）
    static_dir = "static"  # 画像を保存しているディレクトリ
    current_time = time.time()  # 現在の時刻（UNIXタイムスタンプ）
    one_hour_in_seconds = 600  # 1時間を秒に変換

    for filename in os.listdir(static_dir):
        file_path = os.path.join(static_dir, filename)
        if os.path.isfile(file_path):
            file_mtime = os.path.getmtime(file_path)  # ファイルの最終変更時刻を取得
            if current_time - file_mtime > one_hour_in_seconds:
                os.remove(file_path)  # ファイルを削除

    results_gpu = get_all_gpu_status()
    results_df = get_all_storage()

    html_content = "<h1>GPU Status of Multiple Servers</h1>"
    for i in range(len(results_gpu)):
        result = results_gpu[i]
        server_name = result["Name"]
        html_content += f"<h2>{result['Name']}: {result['hostip']}</h2>"
        if "error" in result:
            html_content += f"<p style='color:red;'>Error: {result['error']}</p>"
        else:
            html_content += f"<pre>{result['output']}</pre>"
            # html_content += f"<p>Last Update: {result['timestamp']}</p>"

        result = results_df[i]
        if "error" in result:
            html_content += f"<p style='color:red;'>Error: {result['error']}</p>"
        else:
            html_content += f"<pre>{result['output']}</pre>"
            html_content += f"<p>Last Update: {result['timestamp']}</p>"

        # グラフを生成して画像として保存
        memory_usage_df = fetch_memory_usage(server_name)  # GPU名を指定
        # print(memory_usage_df)
        if not memory_usage_df.empty:

            # server_name = "example_server"  # サーバー名を適宜取得
            timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            file_name = f"{timestamp}-{server_name}"
            # file_path = os.path.join(static_dir, file_name)
            save_path = f"static/{file_name}_memory_usage.png"
            plot_memory_usage(memory_usage_df, save_path)

            # HTMLに画像を追加
            html_content += f"<img src='/{save_path}' alt='Memory Usage Graph for {server_name}' /><br>"
        else:
            print(f"No Memory Usage graph: {server_name}")

        temperature_df = fetch_gpu_temp(server_name)
        if not temperature_df.empty:

            # server_name = "example_server"  # サーバー名を適宜取得
            timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            file_name = f"{timestamp}-{server_name}"
            # file_path = os.path.join(static_dir, file_name)
            save_path = f"static/{file_name}_temperature.png"
            plot_gpu_temp(temperature_df, save_path)

            # HTMLに画像を追加
            html_content += f"<img src='/{save_path}' alt='GPU Temperature Graph for {server_name}' /><br>"
        else:
            print(f"No Temperature graph: {server_name}")

    return html_content


# Flaskサーバーの実行
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
