-- Крепкий лёд: база и пользователь MySQL с минимальными правами и лимитами.
-- Запуск (от root):  mysql -u root -p < sql/mysql_setup.sql
-- Перед запуском замените ПРИДУМАЙТЕ_ДЛИННЫЙ_ПАРОЛЬ (и то же значение впишите в backend/.env).

CREATE DATABASE IF NOT EXISTS krepkiy_led CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Пользователь только с localhost: снаружи к базе подключиться нельзя.
CREATE USER IF NOT EXISTS 'krepkiy'@'localhost' IDENTIFIED BY '12345678';

-- Лимиты на пользователя: даже если приложение взломают или завалят запросами,
-- оно не займёт все соединения MySQL и не положит сервер для остальных.
ALTER USER 'krepkiy'@'localhost' WITH
    MAX_USER_CONNECTIONS 30
    MAX_QUERIES_PER_HOUR 360000
    MAX_UPDATES_PER_HOUR 36000
    MAX_CONNECTIONS_PER_HOUR 3600;

-- Только нужные права и только на свою базу. Никаких FILE, PROCESS, SUPER, GRANT.
-- CREATE/ALTER/INDEX/REFERENCES нужны, чтобы сервер сам создал таблицы при первом запуске;
-- после первого запуска их можно отозвать (см. ниже).
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON krepkiy_led.* TO 'krepkiy'@'localhost';
FLUSH PRIVILEGES;

-- После первого успешного запуска сервера (таблицы созданы) можно оставить только работу с данными:
-- REVOKE CREATE, ALTER, INDEX, REFERENCES ON krepkiy_led.* FROM 'krepkiy'@'localhost';
