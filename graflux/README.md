# Graflux

Graflux is a self-hosted stack designed for monitoring and visualization using my Arduino R4 WiFi, Grafana and InfluxDB. This folder contains the necessary configuration files and resources to deploy and manage the Graflux docker-compose stack that helps to visualize the inbound data setup from [Arduino Monitoring Projects](https://github.com/mackmoe/arduino-projects).

## Contents

- **docker-compose.yml**: The Docker Compose file to orchestrate the services in the Graflux stack.
- **Dockerfile**: Dockerfile for configuring the telegraf image used in the stack.
- **influxv2.env**: Environment variables for configuring InfluxDB v2.
- **README.md**: Documentation for the Graflux stack.
- **grafana/**: json file backups for my custom dashboards in Grafana.
- **telegraf/**: Backup for the only working Telegraf Configuration file that work on my Arduino R4 WiFi.