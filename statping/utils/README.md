# Bulk Import Services
You can import multiple services when Statping first loads by creating a file named services.yml in the working directory for Statping. It will insert the new service into the database, and will not be re-added on reboot. All services must be an array under the services: field.

# Dynamic Yaml
With Yaml, you can insert "anchors" to make receptive fields simple! Checkout the example below. The &tcpservice anchor will return all the fields belonging to x-tcpservice:. To reuse these fields for each service, you can insert <<: *tcpservice and thats it!

# Config with .env File
Danial Habibi edited this page on Oct 10, 2019 · 10 revisions
It may be useful to load your environment using a .env file in the root directory of your Statping server. The .env file will be automatically loaded on startup and will overwrite all values you have in config.yml.

If you have the DB_CONN environment variable set Statping will bypass all values in config.yml and will require you to have the other DB_* variables in place. You can pass in these environment variables without requiring a .env file.

# Environment Variables
This lists all environment variables that could be passed into Statping. You can see all default values in utils/env.go file under the InitEnvs() function.

## Statping Server
PORT - Set the outgoing port for the HTTP server (or use --port, default: 8080)
HOST - Bind a specific IP address to the HTTP server (or use --ip)
VERBOSE - Display more logs in verbose mode. (1 - 4)
STATPING_DIR - Set a absolute path for the root path of Statping server (logs, assets, SQL db)
DISABLE_LOGS - Disable viewing and writing to the log file (default is false)
GO_ENV - Run Statping in testmode, will bypass HTTP authentication (if set as 'test')
REMOVE_AFTER - Automatically delete records after time (default 3 months, '12h = 12 hours')
CLEANUP_INTERVAL - Interval to check for old records (default 1 hour, '1h = 1 hour')
ALLOW_REPORTS - Send Statping anonymous error reports so we can see issues (default is false)
SERVER_PORT - Port number to run Statping HTTP server on (or use -p/--port)
## Automatic SSL Certificate
With LetsEncrypt enabled, Statping will run through the SSL process and create the SSL certs in the certs folder. Read more about the SSL Process on the SSL Wiki.
LETSENCRYPT_ENABLE - Set to true to have LetsEncrypt enabled. (defaults to false)
LETSENCRYPT_HOST - Domain to generate SSL certificate
LETSENCRYPT_EMAIL - Email address that gets sent with the LetsEncrypt Request
LETSENCRYPT_LOCAL - Set for LetsEncrypt testing
## Database
DB_CONN - Database connection (sqlite, postgres, mysql) Will automatically start if set to 'sqlite'
DB_HOST - Database hostname or IP address
DB_USER - Database username
DB_PASS - Database password
DB_PORT - Database port (5432, 3306, ...)
DB_DATABASE - Database connection's database name
DB_DSN - Database DSN string (postgres, mysql, sqlite)
READ_ONLY - Run in a read only mode, this will not create, update, or delete records (false)
POSTGRES_SSLMODE - Enable Postgres SSL Mode 'ssl_mode=VALUE' (enable/disable/verify-full/verify-ca)
MAX_OPEN_CONN - Set Maximum Open Connections for database server (default: 25)
MAX_IDLE_CONN - Set Maximum Idle Connections for database server (default: 25)
MAX_LIFE_CONN - Set Maximum Life Connections for database server (default: 5 minutes)
PREFIX - Add a prefix string to each Prometheus metric (default is empty)
## Connection
BASE_PATH - Set the base URL prefix (set to 'monitor' if URL is domain.com/monitor)
PREFIX - A Prefix for each value in Prometheus /metric exporter
HTTP_PROXY - Use a HTTP Proxy for HTTP Requests
AUTH_USERNAME - HTTP Basic Authentication username
AUTH_PASSWORD - HTTP Basic Authentication password
DISABLE_HTTP - Disable HTTP server if set to true
DISABLE_COLORS - Disable colors in terminal logs if set to true
DEBUG - Enables pprof golang debugging on port 9090
LOGS_MAX_COUNT - Maximum amount of log files (defaults to 5)
LOGS_MAX_AGE - Maximum age for log files (defaults to 28 days)
LOGS_MAX_SIZE - Maximum size for log files (defaults to 16 MB)
LANGUAGE - Language to use (en, fr, it, ru, zh, de, ko, ja)
## Assets
SASS - Set the absolute path to the sass binary location (find with which sass)
USE_ASSETS - Automatically use assets from 'assets folder' (true/false)
If you have issues with Statping not loading frontend files, delete the assets folder and reboot.
## Automatic Fills
NAME - Set a name for the Statping status page
DESCRIPTION - Set a description for the Statping status page
DOMAIN - Set a URL for the Statping status page
ADMIN_USER - Username for administrator account (default: admin)
ADMIN_PASSWORD - Password for administrator account (default: admin)
API_SECRET - Set a custom API Secret for API Authentication
SAMPLE_DATA - Insert sample services, groups and more (default: true)