# Intranet Dashboard

A lightweight self-hosted dashboard for Docker-based home lab and intranet services.

It discovers running Docker containers, shows published ports as clickable links, and lets you manage additional manual services such as `macvlan`, `host` network, router, NAS, VM, printer, or other LAN services through a persistent `services.yaml` file.

Docker image:

```text
newboerg/intranet-dashboard:latest
```

---

## Features

- Automatic discovery of running Docker containers
- Automatic links for published Docker host ports
- Manual services for `macvlan`, `host` network and external LAN services
- Add, edit, delete and hide services from the web UI
- Restore hidden services per group
- Favorites section
- Groups and comments
- Search box
- Multi-language UI
- Built-in language files inside the Docker image
- Persistent configuration via `/config/services.yaml`
- Works on Synology DSM, Linux servers and other Docker hosts

---

## Important Security Note

This dashboard is intended for trusted private networks only.

Do not expose it directly to the public internet.

For automatic Docker container discovery, the container needs access to the Docker API. The simple setup mounts the Docker socket read-only:

```text
/var/run/docker.sock:/var/run/docker.sock:ro
```

For stricter production setups, use a Docker socket proxy.

---

## Quick Start with Docker Hub Image

This command uses the published Docker image:

```text
newboerg/intranet-dashboard:latest
```

Replace these values before running:

```text
DASHBOARD_HOST_IP=your Docker host IP or DNS name
DASHBOARD_PORT=the external web port you want to use
CONFIG_DIR=the persistent config directory on your host
```

Example values:

```text
DASHBOARD_HOST_IP=192.168.1.10
DASHBOARD_PORT=9999
CONFIG_DIR=/volume1/docker/intranet-dashboard/config
```

One-line start command:

```bash
DASHBOARD_HOST_IP=192.168.1.10 DASHBOARD_PORT=9999 CONFIG_DIR=/volume1/docker/intranet-dashboard/config; sudo mkdir -p "$CONFIG_DIR"; [ -f "$CONFIG_DIR/services.yaml" ] || printf '%s\n' 'services: []' | sudo tee "$CONFIG_DIR/services.yaml" >/dev/null; sudo docker rm -f intranet-dashboard 2>/dev/null || true; sudo docker run -d --name intranet-dashboard --restart unless-stopped -p "${DASHBOARD_PORT}:8080" -v "$CONFIG_DIR:/config" -v /var/run/docker.sock:/var/run/docker.sock:ro -e CONFIG_PATH=/config/services.yaml -e DOCKER_HOST=unix:///var/run/docker.sock -e LANGUAGE=en-en -e BASE_HOST="$DASHBOARD_HOST_IP" -e REFRESH_SECONDS=300 -e PORT=8080 newboerg/intranet-dashboard:latest
```

Open the dashboard:

```text
http://192.168.1.10:9999
```

Use your own IP address, hostname and port.

---

## Synology DSM Example

On Synology DSM, a typical config directory could be:

```text
/volume1/docker/intranet-dashboard/config
```

One-line Synology example:

```bash
DASHBOARD_HOST_IP=192.168.1.10 DASHBOARD_PORT=9999 CONFIG_DIR=/volume1/docker/intranet-dashboard/config; sudo mkdir -p "$CONFIG_DIR"; [ -f "$CONFIG_DIR/services.yaml" ] || printf '%s\n' 'services: []' | sudo tee "$CONFIG_DIR/services.yaml" >/dev/null; sudo docker rm -f intranet-dashboard 2>/dev/null || true; sudo docker run -d --name intranet-dashboard --restart unless-stopped -p "${DASHBOARD_PORT}:8080" -v "$CONFIG_DIR:/config" -v /var/run/docker.sock:/var/run/docker.sock:ro -e CONFIG_PATH=/config/services.yaml -e DOCKER_HOST=unix:///var/run/docker.sock -e LANGUAGE=en-en -e BASE_HOST="$DASHBOARD_HOST_IP" -e REFRESH_SECONDS=300 -e PORT=8080 newboerg/intranet-dashboard:latest
```

Then open:

```text
http://192.168.1.10:9999
```

---

## Required Volume Mapping

Only one persistent config directory is required:

```text
Host directory                         Container path
/path/to/intranet-dashboard/config  ->  /config
```

The main persistent file is:

```text
/config/services.yaml
```

The quick-start command creates this minimal file automatically if it does not exist:

```yaml
services: []
```

Language files are already included in the Docker image under:

```text
/app/lang
```

You do not need to mount language files.

Optional language overrides can be placed here:

```text
/config/lang
```

---

## Port Mapping

The app listens inside the container on port `8080`.

To expose it as `9999` on the Docker host:

```text
Host port 9999 -> Container port 8080
```

Docker notation:

```text
9999:8080
```

Browser URL:

```text
http://YOUR_DOCKER_HOST_IP:9999
```

---

## Environment Variables

| Variable | Example | Description |
|---|---|---|
| `CONFIG_PATH` | `/config/services.yaml` | Path to the service configuration file inside the container |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker API endpoint |
| `LANGUAGE` | `en-en` | UI language |
| `BASE_HOST` | `192.168.1.10` | Hostname or IP used for automatically generated links |
| `REFRESH_SECONDS` | `300` | Browser auto-refresh interval |
| `PORT` | `8080` | Internal app port |
| `DEFAULT_PROTOCOL` | `http` | Default protocol for generated links |
| `URL_CHECK_TIMEOUT` | `3` | Timeout for URL reachability checks |

---

## Supported Languages

The Docker image includes language files.

Examples:

```text
de-de
en-en
fr-fr
es-es
it-it
pt-br
nl-nl
pl-pl
cs-cz
sv-se
da-dk
fi-fi
no-nb
tr-tr
ru-ru
uk-ua
zh-cn
ja-jp
ko-kr
ar-sa
hi-in
id-id
vi-vn
```

Set the language with:

```text
LANGUAGE=en-en
```

or for German:

```text
LANGUAGE=de-de
```

---

## Docker Compose Example

Create a directory:

```bash
mkdir -p intranet-dashboard/config
```

Create `intranet-dashboard/config/services.yaml`:

```yaml
services: []
```

Create `compose.yaml`:

```yaml
services:
  intranet-dashboard:
    image: newboerg/intranet-dashboard:latest
    container_name: intranet-dashboard
    restart: unless-stopped
    ports:
      - "9999:8080"
    volumes:
      - ./config:/config
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      CONFIG_PATH: /config/services.yaml
      DOCKER_HOST: unix:///var/run/docker.sock
      LANGUAGE: en-en
      BASE_HOST: 192.168.1.10
      REFRESH_SECONDS: "300"
      PORT: "8080"
```

Start:

```bash
sudo docker compose up -d
```

Open:

```text
http://192.168.1.10:9999
```

---

## Manual Services

Manual services are stored in:

```text
/config/services.yaml
```

This is useful for:

- `macvlan` containers
- `host` network containers
- services with custom DNS names
- routers
- switches
- printers
- VMs
- NAS apps
- external LAN services

Example:

```yaml
services:
  - name: "Router"
    group: "Network"
    favorite: true
    note: "Example external service"
    urls:
      - name: "Web UI"
        url: "http://192.168.1.1"

  - name: "Jellyfin"
    container: "jellyfin"
    group: "Media"
    note: "Example Docker service with custom DNS name"
    urls:
      - name: "Web UI"
        url: "http://jellyfin.lan:8096"

  - name: "Home Assistant"
    container: "homeassistant"
    group: "Smart Home"
    note: "Example macvlan or host-network service"
    disable_auto_links: true
    urls:
      - name: "Web UI"
        url: "http://homeassistant.lan:8123"
```

No container restart is required after editing `services.yaml`. Reload the browser page.

---

## Service Fields

| Field | Required | Description |
|---|---:|---|
| `name` | Yes | Display name |
| `container` | No | Docker container name to associate this entry with |
| `group` | No | Dashboard group |
| `favorite` | No | `true` or `false` |
| `note` | No | Comment shown on the card |
| `urls` | No | List of links |
| `hide` | No | Hide the service when `true` |
| `disable_auto_links` | No | Disable automatically generated Docker port links |

---

## UI Management

The dashboard UI supports:

- Add service
- Edit service
- Change group
- Mark as favorite
- Hide service
- Restore hidden services
- Delete service config entries
- Search services

When adding a new service through the UI, the dashboard checks whether the target is reachable.

When editing an existing service, the URL can be empty and no reachability check is enforced. This is useful for automatically discovered `host` or `macvlan` containers where you only want to add metadata first.

---

## macvlan and host-network Containers

Docker often cannot provide useful published port mappings for `macvlan` or `host` network services.

For these services, use manual entries in `services.yaml` or edit the automatically discovered card in the UI.

Example:

```yaml
services:
  - name: "Service Name"
    container: "container-name"
    group: "Network"
    urls:
      - name: "Web UI"
        url: "http://service.example.local:8080"
```

---

## Stop and Remove

```bash
sudo docker rm -f intranet-dashboard
```

The persistent configuration remains on the host in your config directory.

---

## Update

Pull the newest image and recreate the container:

```bash
DASHBOARD_HOST_IP=192.168.1.10 DASHBOARD_PORT=9999 CONFIG_DIR=/volume1/docker/intranet-dashboard/config; sudo docker pull newboerg/intranet-dashboard:latest; sudo docker rm -f intranet-dashboard 2>/dev/null || true; sudo mkdir -p "$CONFIG_DIR"; [ -f "$CONFIG_DIR/services.yaml" ] || printf '%s\n' 'services: []' | sudo tee "$CONFIG_DIR/services.yaml" >/dev/null; sudo docker run -d --name intranet-dashboard --restart unless-stopped -p "${DASHBOARD_PORT}:8080" -v "$CONFIG_DIR:/config" -v /var/run/docker.sock:/var/run/docker.sock:ro -e CONFIG_PATH=/config/services.yaml -e DOCKER_HOST=unix:///var/run/docker.sock -e LANGUAGE=en-en -e BASE_HOST="$DASHBOARD_HOST_IP" -e REFRESH_SECONDS=300 -e PORT=8080 newboerg/intranet-dashboard:latest
```

---

## Build Locally from GitHub

Clone the repository:

```bash
git clone https://github.com/newboerg/intranet-dashboard.git intranet-dashboard
```

Build and run locally:

```bash
cd intranet-dashboard && mkdir -p config && [ -f config/services.yaml ] || printf '%s\n' 'services: []' > config/services.yaml && sudo docker build -t intranet-dashboard:local . && sudo docker run -d --name intranet-dashboard --restart unless-stopped -p 9999:8080 -v "$(pwd)/config:/config" -v /var/run/docker.sock:/var/run/docker.sock:ro -e CONFIG_PATH=/config/services.yaml -e DOCKER_HOST=unix:///var/run/docker.sock -e LANGUAGE=en-en -e BASE_HOST=192.168.1.10 -e REFRESH_SECONDS=300 -e PORT=8080 intranet-dashboard:local
```

Open:

```text
http://192.168.1.10:9999
```

---

## Troubleshooting

Check if the container is running:

```bash
sudo docker ps --filter "name=intranet-dashboard"
```

Check logs:

```bash
sudo docker logs --tail=100 intranet-dashboard
```

Test locally on the Docker host:

```bash
curl -I http://127.0.0.1:9999
```

Check Docker socket access:

```bash
sudo docker exec intranet-dashboard sh -c 'ls -l /var/run/docker.sock'
```

Check config file:

```bash
sudo docker exec intranet-dashboard sh -c 'cat /config/services.yaml'
```

If the dashboard shows an error like:

```text
Error while fetching server API version
```

then the container cannot access Docker. Make sure this mount exists:

```text
/var/run/docker.sock:/var/run/docker.sock:ro
```

and this environment variable is set:

```text
DOCKER_HOST=unix:///var/run/docker.sock
```

---

## License

MIT License.
