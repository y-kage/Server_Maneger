CREATE DATABASE IF NOT EXISTS Server_GPU_Usage;

USE Server_GPU_Usage;

CREATE TABLE gpu_usage (
    id INT AUTO_INCREMENT PRIMARY KEY,
    host_name VARCHAR(100),
    host_ip VARCHAR(100),
    gpu_index INT,
    gpu_name VARCHAR(100),
    fan_speed INT,
    temperature INT,
    power_usage INT,
    power_capacity INT,
    memory_usage INT,
    memory_capacity INT,
    gpu_utilization INT,
    timestamp DATETIME
);
