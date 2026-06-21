-- Initialization script for SRE database
-- This script runs automatically when the MySQL container starts for the first time.

CREATE DATABASE IF NOT EXISTS sre_db;
USE sre_db;

CREATE TABLE IF NOT EXISTS services (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status ENUM('healthy', 'degraded', 'down') NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT INTO services (name, status) VALUES 
('auth-service', 'healthy'),
('payment-gateway', 'degraded'),
('user-profile', 'healthy');

-- Create a large 'request_logs' table to simulate a production-like database
CREATE TABLE IF NOT EXISTS request_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    service_name VARCHAR(255) NOT NULL,
    status_code INT NOT NULL,
    response_time_ms INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_service_created (service_name, created_at)
);

-- Generate 1,000,000 rows using a recursive CTE.
-- This will take a few seconds during container startup but provides a realistic testing scenario.
SET SESSION cte_max_recursion_depth = 1000000;

INSERT INTO request_logs (service_name, status_code, response_time_ms, created_at)
WITH RECURSIVE seq AS (
  SELECT 1 AS id
  UNION ALL
  SELECT id + 1 FROM seq WHERE id < 1000000
)
SELECT 
    ELT(FLOOR(1 + (RAND() * 3)), 'auth-service', 'payment-gateway', 'user-profile'),
    ELT(FLOOR(1 + (RAND() * 4)), 200, 201, 400, 500),
    FLOOR(10 + (RAND() * 1000)),
    CURRENT_TIMESTAMP - INTERVAL FLOOR(RAND() * 30) DAY
FROM seq;

-- We also grant some privileges to ensure the user can query system tables
GRANT SELECT ON performance_schema.* TO 'sre_user'@'%';
GRANT PROCESS ON *.* TO 'sre_user'@'%';
FLUSH PRIVILEGES;
