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

-- We also grant some privileges to ensure the user can query system tables
GRANT SELECT ON performance_schema.* TO 'sre_user'@'%';
GRANT PROCESS ON *.* TO 'sre_user'@'%';
FLUSH PRIVILEGES;
