# Server_Maneger

# Command
## Install
```
# install
sudo apt update
sudo apt install mysql-server
```

## Run
```
# when using
# データベースとテーブルを制作．最初に１回だけ行う．
mysql -u root -p < server_gpu_database.sql

# app_mysql.pyを実行
gunicorn --bind 0.0.0.0:8000 app_mysql:app

＃collect_gpu_data.pyを実行
python3 collect_gpu_data.py

# mysqlを実行
mysql -u root -p
```

# DL-Box7で実行中
```
# screenを使ってバックグラウンドで実行中
screen -ls
screen -r ServerManeger                 # app_mysql.pyを実行中
screen -r ServerManeger_collect_data    # collect_gpu_data.pyを実行中
```

```mysql -u root -p```を実行後に以下のコマンドなどでデータベースを確認可能.MySQLのパスワードはhvrlアカウントのパスワードと一緒．
```
USE Server_GPU_Usage;
SELECT * FROM gpu_usage WHERE host_name = 'DL-Box1';
```
データベースの容量
```
SELECT table_name AS "Table", 
       ROUND((data_length + index_length) / 1024 / 1024, 2) AS "Size (MB)"
FROM information_schema.tables
WHERE table_schema = 'Server_GPU_Usage'
ORDER BY (data_length + index_length) DESC;
```
