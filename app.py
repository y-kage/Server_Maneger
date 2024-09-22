import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import paramiko
from flask import Flask, jsonify, redirect, request

"""
-Before Running app, 
pip install flask paramiko gunicorn

-Use screen or put &at the end of the command to run background
$ screen -S ServerManeger

-Run the command to run the app
$ gunicorn --bind 0.0.0.0:8000 app:app
"""
app = Flask(__name__)

# 複数サーバーの情報（IPアドレス、ユーザー名、パスワード、SSH鍵ファイルパスなど）
servers = load_servers_from_json("server_list.json")


# 「Processes」セクション以降を削除する関数
def remove_processes_section(nvidia_smi_output):
    # 「Processes」セクション以降を削除
    return re.sub(
        r"\+--------------------\+\n\| Processes:(.|\n)*", "", nvidia_smi_output
    )


# SSH経由でnvidia-smiを実行して結果を取得する関数
def execute_nvidia_smi(hostname, username, password):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, username=username, password=password)

        # nvidia-smiコマンドを実行して、すべてのGPU情報を取得
        command = "nvidia-smi"
        # command = "nvidia-smi --query-gpu=index,name,fan.speed,temperature.gpu,power.draw,power.limit,memory.used,memory.total,utilization.gpu,timestamp --format=csv,noheader,nounits"
        stdin, stdout, stderr = client.exec_command(command)
        result = stdout.read().decode("utf-8").strip()
        result = result.split("\n")
        result = len(result)
        client.close()

        # 「Processes」セクションを削除する
        # filtered_result = remove_processes_section(result)
        # result = filtered_result

        return {
            "hostname": hostname,
            "nvidia_smi_output": result,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"Error connecting to {hostname}: {e}")
        return {"hostname": hostname, "error": str(e)}


# 複数のサーバーにnvidia-smiを並列で実行する関数
def get_all_gpu_status():
    results = []
    with ThreadPoolExecutor(max_workers=len(servers)) as executor:
        futures = [
            executor.submit(
                execute_nvidia_smi, srv["hostname"], srv["username"], srv["password"]
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


# ブラウザでアクセスされたときに全サーバーのGPU情報を表示
@app.route("/status", methods=["GET"])
def status():
    results = get_all_gpu_status()

    # サーバーごとにnvidia-smiの結果をそのまま表示
    html_content = "<h1>GPU Status of Multiple Servers</h1>"
    for result in results:
        if "error" in result:
            html_content += f"<h2>Hostname: {result['hostname']}</h2>"
            html_content += f"<p style='color:red;'>Error: {result['error']}</p>"
        else:
            html_content += f"<h2>Hostname: {result['hostname']}</h2>"
            html_content += f"<pre>{result['nvidia_smi_output']}</pre>"
            html_content += f"<p>Last Update: {result['timestamp']}</p>"

    return html_content


# Flaskサーバーの実行
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

