# Server_Maneger

# Command
```
sudo mysql -u root -p < server_gpu_database.sql
gunicorn --bind 0.0.0.0:8000 app_mysql:app
```

flask
gunicorn
mysql-connector-python
pandas
sqlalchemy
