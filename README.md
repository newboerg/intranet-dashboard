# Intranet Dashboard

A lightweight self-hosted dashboard for Docker and LAN services. It discovers running Docker containers, shows published ports as clickable links, and allows manual service entries for macvlan, host-network, DNS aliases, routers, switches, VMs, and other external services.

## Features

- Automatic discovery of running Docker containers and published host ports
- Manual services from `config/services.yaml`
- UI-based service editing
- Add external services through the UI
- Favorites
- Groups
- Hide and unhide services
- Delete manual entries
- Comments per service
- Multi-language UI via YAML language files
- Designed for Synology DSM and generic Docker hosts
- Docker API access through `docker-socket-proxy`

## Quick start

Create a project directory:

```bash
mkdir -p intranet-dashboard/config/lang && cd intranet-dashboard
```

Copy `compose.example.yaml` to `compose.yaml`, `.env.example` to `.env`, and `config/services.example.yaml` to `config/services.yaml`.

Start the dashboard:

```bash
sudo docker compose up -d
```

Open the local backend:

```text
http://127.0.0.1:8999
```

For Synology DSM, put a DSM Reverse Proxy in front of it and route your LAN hostname, for example `http://intranet.lan`, to `http://127.0.0.1:8999`.

## Docker Compose

Use `compose.example.yaml` as the starting point. Replace this image placeholder with your published image:

```text
ghcr.io/OWNER/intranet-dashboard:latest
```

Recommended runtime settings are in `.env.example`.

## Manual services

The active config file is:

```text
config/services.yaml
```

Example:

```yaml
services:
  - name: "Jellyfin"
    container: "jellyfin"
    group: "Media"
    favorite: true
    note: "Example Docker service with custom DNS name"
    urls:
      - name: "Web UI"
        url: "http://jellyfin.lan:8096"
```

## macvlan and host-network services

macvlan and host-network containers often do not have useful Docker port mappings. Add or edit their URL through the UI, or define them manually in `config/services.yaml`.

Example:

```yaml
services:
  - name: "Home Assistant"
    container: "homeassistant"
    group: "Smart Home"
    disable_auto_links: true
    urls:
      - name: "Web UI"
        url: "http://homeassistant.lan:8123"
```

## Language files

Language files live in:

```text
config/lang/
```

Set the active language in Compose or `.env`:

```text
LANGUAGE=de-de
```

## Synology DSM reverse proxy

Create a Reverse Proxy rule in DSM:

```text
Source: HTTP, hostname intranet.lan, port 80
Target: HTTP, hostname 127.0.0.1, port 8999
```

The dashboard container should remain bound to `127.0.0.1:8999` unless you intentionally want direct LAN access.

## Security notes

This dashboard is intended for private LAN use only. Do not publish it directly to the internet.

Do not commit or publish:

- `config/services.yaml`
- backups of `services.yaml`
- private screenshots
- internal hostnames, IPs, domains, or comments

## License

MIT License. See `LICENSE`.
