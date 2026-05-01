import os
import html
import socket
import tempfile
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from flask import Flask, render_template_string, request, jsonify
import docker
import yaml

app = Flask(__name__)

BASE_HOST = os.getenv("BASE_HOST", "intranet.lan").strip()
DEFAULT_PROTOCOL = os.getenv("DEFAULT_PROTOCOL", "http").strip()
REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "30"))
CONFIG_PATH = os.getenv("CONFIG_PATH", "/config/services.yaml").strip()
PORT = int(os.getenv("PORT", "8080"))
URL_CHECK_TIMEOUT = float(os.getenv("URL_CHECK_TIMEOUT", "3"))

LANGUAGE = os.getenv("LANGUAGE", "de-de").strip().lower() or "de-de"
LANG_DIR = os.getenv("LANG_DIR", "/config/lang").strip()

DEFAULT_I18N = {
    "app": {
        "html_lang": "de",
        "title": "Intranet Dienste",
        "subtitle": "Laufende Container plus manuelle Dienste aus services.yaml",
        "host": "Host",
        "refresh": "Refresh",
        "timestamp": "Stand",
        "search_placeholder": "Dienst suchen...",
        "favorites_group": "★ Favoriten",
    },
    "buttons": {
        "add_service": "+ Dienst",
        "edit": "Edit",
        "cancel": "Abbrechen",
        "save": "Speichern",
        "check_save": "Prüfen & Speichern",
        "checking": "Prüfe...",
        "saving": "Speichere...",
        "ok": "OK",
        "unhide": "Einblenden",
        "close": "Schließen",
    },
    "fields": {
        "name": "Name",
        "group": "Gruppe",
        "container": "Container",
        "container_optional": "Containername optional",
        "url": "URL oder IP:Port",
        "url_optional": "URL oder IP:Port optional",
        "link_name": "Linkname",
        "note_optional": "Kommentar optional",
        "favorite": "Als Favorit markieren",
        "image": "Image",
        "network": "Network",
        "host": "Host",
        "manual_service": "Manueller Dienst",
    },
    "dialogs": {
        "add_title": "Dienst hinzufügen",
        "edit_title": "Dienst bearbeiten",
        "hidden_title": "Ausgeblendete Dienste",
        "hidden_title_group": "Ausgeblendete Dienste: {group}",
        "group_change": "{name} → Gruppe ändern",
        "edit_title_for": "{name} → Dienst bearbeiten",
        "confirm_hide": "Dienst \"{name}\" ausblenden?",
        "confirm_delete": "Dienst \"{name}\" wirklich aus services.yaml löschen?",
    },
    "placeholders": {
        "name": "z. B. Router",
        "group": "Gruppe",
        "display_name": "Anzeigename",
        "url": "192.168.2.3:14500 oder http://host:port",
        "url_optional": "leer lassen oder 192.168.2.3:14500",
        "container": "z. B. jellyfin",
        "note": "Kurzer Hinweis fürs Dashboard",
        "note_optional": "Optionaler Hinweis fürs Dashboard",
        "new_group": "Neue Gruppe",
    },
    "tooltips": {
        "show_hidden": "Ausgeblendete Dienste dieser Gruppe anzeigen",
        "toggle_favorite": "Favorit umschalten",
        "edit_service": "Dienst bearbeiten",
        "hide_service": "Dienst ausblenden",
        "delete_service": "Dienst löschen",
    },
    "messages": {
        "no_ports": "{{ ui.messages.no_ports }}",
        "all_hidden": "{{ ui.messages.all_hidden }}",
        "favorite_save_failed": "Favorit konnte nicht gespeichert werden",
        "hide_failed": "Dienst konnte nicht ausgeblendet werden",
        "delete_failed": "Dienst konnte nicht gelöscht werden",
        "service_save_failed": "Dienst konnte nicht gespeichert werden",
        "group_save_failed": "Gruppe konnte nicht gespeichert werden",
        "unhide_failed": "Dienst konnte nicht eingeblendet werden",
    },
    "server": {
        "url_empty": "URL darf nicht leer sein",
        "url_spaces": "URL darf keine Leerzeichen enthalten",
        "url_scheme": "Nur http:// und https:// URLs werden unterstützt",
        "url_host": "URL braucht einen Hostnamen oder eine IP-Adresse",
        "url_port": "Port muss zwischen 1 und 65535 liegen",
        "dns_failed": "DNS-Auflösung für {host} fehlgeschlagen",
        "timeout": "Timeout bei Verbindung zu {host}:{port}",
        "not_reachable": "{host}:{port} ist nicht erreichbar: {error}",
        "service_not_found": "Dienst wurde nicht gefunden",
        "group_empty": "Gruppe darf nicht leer sein",
        "group_too_long": "Gruppe ist zu lang",
        "auto_delete_forbidden": "Dieser automatisch erkannte Docker-Container hat keinen services.yaml-Eintrag. Verwende Ausblenden statt Löschen.",
        "name_empty": "Name darf nicht leer sein",
        "name_too_long": "Name ist zu lang",
        "not_saved": "Dienst wurde nicht gespeichert: {message}",
        "url_duplicate": "Diese URL ist bereits in services.yaml vorhanden"
    },
    "errors": {
        "docker_config_read_failed": "Docker/Config-Daten konnten nicht gelesen werden: {error}",
    },
}


def deep_merge(base, override):
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml_file(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def load_translations():
    base = deep_merge(DEFAULT_I18N, load_yaml_file(os.path.join(LANG_DIR, "de-de.yaml")))
    if LANGUAGE != "de-de":
        base = deep_merge(base, load_yaml_file(os.path.join(LANG_DIR, f"{LANGUAGE}.yaml")))
    return base


def get_i18n_value(data, path, default=None):
    current = data
    for part in str(path).split("."):
        if not isinstance(current, dict) or part not in current:
            return default if default is not None else path
        current = current[part]
    return current


def t(path, default=None, **kwargs):
    value = str(get_i18n_value(load_translations(), path, default if default is not None else path))
    try:
        return value.format(**kwargs)
    except Exception:
        return value


def is_true(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def clean_path(path):
    if not path:
        return "/"
    path = str(path).strip()
    return path if path.startswith("/") else f"/{path}"


def normalize_container_name(name):
    return str(name or "").strip().lstrip("/").lower()


def read_yaml_config():
    if not os.path.exists(CONFIG_PATH):
        return {"services": []}

    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        data = {}

    services = data.get("services", [])
    if not isinstance(services, list):
        services = []

    data["services"] = services
    return data


def write_yaml_config(data):
    directory = os.path.dirname(CONFIG_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".services.", suffix=".yaml", dir=directory)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True, default_flow_style=False)

        os.replace(tmp_path, CONFIG_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def service_container_names(service):
    raw = service.get("container")
    if not raw:
        return []

    if isinstance(raw, list):
        return [normalize_container_name(item) for item in raw if str(item).strip()]

    return [normalize_container_name(raw)]


def find_matching_service_indexes(container_name, services):
    wanted = normalize_container_name(container_name)
    matches = []

    for index, service in enumerate(services):
        if wanted in service_container_names(service):
            matches.append(index)

    return matches


def build_url(labels, internal_port, host_port):
    explicit = labels.get(f"dashboard.url.{internal_port}") or labels.get("dashboard.url")
    if explicit:
        return explicit

    protocol = labels.get(f"dashboard.protocol.{internal_port}") or labels.get("dashboard.protocol") or DEFAULT_PROTOCOL
    host = labels.get(f"dashboard.host.{internal_port}") or labels.get("dashboard.host") or BASE_HOST
    path = labels.get(f"dashboard.path.{internal_port}") or labels.get("dashboard.path") or "/"

    return f"{protocol}://{host}:{host_port}{clean_path(path)}"


def link_key(link):
    return str(link.get("url", "")).strip().lower()


def port_sort_key(link):
    try:
        return int(str(link.get("host_port", "999999")))
    except Exception:
        return 999999


def service_favorite_value(service, labels):
    if "favorite" in service:
        return is_true(service.get("favorite"))
    return is_true(labels.get("dashboard.favorite", False))


def normalize_service_url(raw_url):
    raw_url = str(raw_url or "").strip()

    if not raw_url:
        raise ValueError(t("server.url_empty"))

    if any(char.isspace() for char in raw_url):
        raise ValueError(t("server.url_spaces"))

    if "://" not in raw_url:
        raw_url = f"http://{raw_url}"

    parsed = urlsplit(raw_url)
    scheme = parsed.scheme.lower()

    if scheme not in {"http", "https"}:
        raise ValueError(t("server.url_scheme"))

    if not parsed.hostname:
        raise ValueError(t("server.url_host"))

    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise ValueError(t("server.url_port"))

    netloc = parsed.netloc
    path = parsed.path or ""

    return urlunsplit((scheme, netloc, path, parsed.query, parsed.fragment))


def check_url_reachable(url, timeout=URL_CHECK_TIMEOUT):
    parsed = urlsplit(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    if not host:
        return False, t("server.url_host")

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} ist erreichbar"
    except socket.gaierror:
        return False, t("server.dns_failed", host=host)
    except socket.timeout:
        return False, t("server.timeout", host=host, port=port)
    except OSError as exc:
        return False, t("server.not_reachable", host=host, port=port, error=exc)


def links_from_service(service):
    links = []

    for item in service.get("urls", []) or []:
        if not isinstance(item, dict):
            continue

        url = str(item.get("url", "")).strip()
        if not url:
            continue

        links.append({
            "name": str(item.get("name") or "Link"),
            "url": url,
            "host_port": str(item.get("port") or ""),
            "container_port": str(item.get("container_port") or ""),
            "proto": str(item.get("proto") or ""),
            "bind_note": str(item.get("note") or "config"),
            "source": "config",
        })

    return links


def auto_links_from_container(container):
    links = []
    seen = set()

    try:
        container.reload()
    except Exception:
        pass

    labels = container.labels or {}
    attrs = container.attrs or {}
    network = attrs.get("NetworkSettings", {}) or {}
    ports = network.get("Ports") or {}

    for private_port, bindings in ports.items():
        if not bindings:
            continue

        if "/" in private_port:
            internal_port, proto = private_port.split("/", 1)
        else:
            internal_port, proto = private_port, "tcp"

        for binding in bindings:
            host_port = str(binding.get("HostPort", "")).strip()
            host_ip = str(binding.get("HostIp", "")).strip()

            if not host_port:
                continue

            key = (host_port, internal_port, proto)
            if key in seen:
                continue

            seen.add(key)

            link_name = labels.get(f"dashboard.name.{internal_port}") or labels.get("dashboard.link_name") or f"{container.name} :{host_port}"

            if host_ip.startswith("127."):
                bind_note = "NAS-localhost"
            elif host_ip in {"0.0.0.0", "::", ""}:
                bind_note = "LAN"
            else:
                bind_note = host_ip

            links.append({
                "name": link_name,
                "url": build_url(labels, internal_port, host_port),
                "host_port": host_port,
                "container_port": internal_port,
                "proto": proto,
                "bind_note": bind_note,
                "source": "docker",
            })

    manual_ports = labels.get("dashboard.ports", "")
    for item in [p.strip() for p in manual_ports.split(",") if p.strip()]:
        host_port = item
        key = (host_port, host_port, "tcp")

        if key in seen:
            continue

        seen.add(key)

        links.append({
            "name": labels.get(f"dashboard.name.{host_port}") or f"{container.name} :{host_port}",
            "url": build_url(labels, host_port, host_port),
            "host_port": host_port,
            "container_port": host_port,
            "proto": "tcp",
            "bind_note": "label",
            "source": "label",
        })

    return sorted(links, key=port_sort_key)


def container_row(container, matching_services, service_index=None):
    labels = container.labels or {}
    attrs = container.attrs or {}
    config = attrs.get("Config", {}) or {}
    state = attrs.get("State", {}) or {}
    host_config = attrs.get("HostConfig", {}) or {}

    first_service = matching_services[0] if matching_services else {}

    name = first_service.get("name") or labels.get("dashboard.name") or container.name
    group = first_service.get("group") or labels.get("dashboard.group") or "Docker"
    favorite = service_favorite_value(first_service, labels)
    note = first_service.get("note") or labels.get("dashboard.note") or ""
    auto = not is_true(first_service.get("disable_auto_links", False)) and not is_true(labels.get("dashboard.disable_auto_links", False))

    links = []
    urls_seen = set()
    config_url = ""
    config_link_name = "Web UI"

    for service in matching_services:
        for link in links_from_service(service):
            if not config_url:
                config_url = str(link.get("url") or "")
                config_link_name = str(link.get("name") or "Web UI")
            key = link_key(link)
            if key and key not in urls_seen:
                urls_seen.add(key)
                links.append(link)

    if auto:
        for link in auto_links_from_container(container):
            key = link_key(link)
            if key and key not in urls_seen:
                urls_seen.add(key)
                links.append(link)

    return {
        "id": f"docker:{container.name}",
        "service_index": service_index,
        "has_config": service_index is not None,
        "name": name,
        "group": group,
        "favorite": favorite,
        "note": note,
        "config_url": config_url,
        "config_link_name": config_link_name,
        "container": container.name,
        "image": config.get("Image", ""),
        "status": container.status,
        "network_mode": host_config.get("NetworkMode", ""),
        "started_at": state.get("StartedAt", ""),
        "links": links,
        "has_links": len(links) > 0,
        "manual_only": False,
    }


def manual_only_rows(services, used_services):
    rows = []

    for index, service in enumerate(services):
        if index in used_services:
            continue

        if is_true(service.get("hide", False)):
            continue

        links = links_from_service(service)
        if not links:
            continue

        rows.append({
            "id": f"manual:{index}",
            "service_index": index,
            "has_config": True,
            "name": service.get("name") or "Manueller Dienst",
            "group": service.get("group") or "Manuell",
            "favorite": is_true(service.get("favorite", False)),
            "note": service.get("note") or "",
            "config_url": links[0].get("url", "") if links else "",
            "config_link_name": links[0].get("name", "Web UI") if links else "Web UI",
            "container": service.get("container") or "",
            "image": "",
            "status": "manual",
            "network_mode": "config",
            "started_at": "",
            "links": links,
            "has_links": True,
            "manual_only": True,
        })

    return rows


def read_dashboard_rows():
    cfg = read_yaml_config()
    services = cfg.get("services", [])

    client = docker.from_env()
    containers = client.containers.list(filters={"status": "running"})

    rows = []
    used_services = set()

    for container in containers:
        labels = container.labels or {}

        if is_true(labels.get("dashboard.hide", False)):
            continue

        match_indexes = find_matching_service_indexes(container.name, services)
        matching = [services[index] for index in match_indexes]

        hidden_by_config = any(is_true(service.get("hide", False)) for service in matching)
        if hidden_by_config:
            for index in match_indexes:
                used_services.add(index)
            continue

        for index in match_indexes:
            used_services.add(index)

        rows.append(container_row(container, matching, match_indexes[0] if match_indexes else None))

    rows.extend(manual_only_rows(services, used_services))

    return sorted(rows, key=lambda row: (str(row["group"]).lower(), str(row["name"]).lower()))


def read_hidden_by_group():
    cfg = read_yaml_config()
    hidden = {}

    for index, service in enumerate(cfg.get("services", [])):
        if not is_true(service.get("hide", False)):
            continue

        group = str(service.get("group") or "Manuell")
        name = str(service.get("name") or service.get("container") or "Ausgeblendeter Dienst")

        hidden.setdefault(group, []).append({
            "id": f"hidden:{index}",
            "name": name,
            "container": service.get("container") or "",
            "group": group,
            "note": service.get("note") or "",
        })

    for group in hidden:
        hidden[group] = sorted(hidden[group], key=lambda item: item["name"].lower())

    return dict(sorted(hidden.items(), key=lambda item: item[0].lower()))


def get_group_names(rows=None):
    cfg = read_yaml_config()
    groups = set()

    for service in cfg.get("services", []):
        group = str(service.get("group") or "").strip()
        if group:
            groups.add(group)

    if rows:
        for row in rows:
            group = str(row.get("group") or "").strip()
            if group:
                groups.add(group)

    groups.add("Docker")
    groups.add("System")
    groups.add("Smart Home")
    groups.add("Netzwerk")
    groups.add("Medien")
    groups.add("Manuell")

    return sorted(groups, key=lambda item: item.lower())


def service_index_from_card(card_id, container_name, services):
    card_id = str(card_id or "")

    if card_id.startswith("manual:") or card_id.startswith("hidden:"):
        index = int(card_id.split(":", 1)[1])
        if index < 0 or index >= len(services):
            raise ValueError(t("server.service_not_found"))
        return index

    normalized_container = normalize_container_name(container_name)
    match_indexes = find_matching_service_indexes(normalized_container, services)

    if match_indexes:
        return match_indexes[0]

    return None


def update_group_in_config(card_id, container_name, display_name, group):
    group = str(group or "").strip()
    if not group:
        raise ValueError(t("server.group_empty"))

    if len(group) > 64:
        raise ValueError(t("server.group_too_long"))

    cfg = read_yaml_config()
    services = cfg.setdefault("services", [])
    index = service_index_from_card(card_id, container_name, services)

    if index is not None:
        services[index]["group"] = group
    else:
        services.append({
            "name": display_name or container_name,
            "container": container_name,
            "group": group,
            "urls": [],
        })

    write_yaml_config(cfg)


def update_favorite_in_config(card_id, container_name, display_name, favorite):
    cfg = read_yaml_config()
    services = cfg.setdefault("services", [])
    favorite = bool(favorite)
    index = service_index_from_card(card_id, container_name, services)

    if index is not None:
        services[index]["favorite"] = favorite
    else:
        services.append({
            "name": display_name or container_name,
            "container": container_name,
            "group": "Docker",
            "favorite": favorite,
            "urls": [],
        })

    write_yaml_config(cfg)


def hide_service_in_config(card_id, container_name, display_name, group):
    cfg = read_yaml_config()
    services = cfg.setdefault("services", [])
    index = service_index_from_card(card_id, container_name, services)

    if index is not None:
        services[index]["hide"] = True
    else:
        services.append({
            "name": display_name or container_name,
            "container": container_name,
            "group": group or "Docker",
            "hide": True,
            "urls": [],
        })

    write_yaml_config(cfg)


def unhide_service_in_config(card_id):
    cfg = read_yaml_config()
    services = cfg.setdefault("services", [])
    index = service_index_from_card(card_id, "", services)
    services[index]["hide"] = False
    write_yaml_config(cfg)


def delete_service_from_config(card_id, container_name):
    cfg = read_yaml_config()
    services = cfg.setdefault("services", [])
    index = service_index_from_card(card_id, container_name, services)

    if index is None:
        raise ValueError(t("server.auto_delete_forbidden"))

    del services[index]
    write_yaml_config(cfg)


def create_service_in_config(payload):
    name = str(payload.get("name") or "").strip()
    group = str(payload.get("group") or "Manuell").strip() or "Manuell"
    raw_url = str(payload.get("url") or "").strip()
    link_name = str(payload.get("link_name") or "Web UI").strip() or "Web UI"
    note = str(payload.get("note") or "").strip()
    container_name = str(payload.get("container") or "").strip()
    favorite = bool(payload.get("favorite", False))

    if not name:
        raise ValueError(t("server.name_empty"))

    if len(name) > 80:
        raise ValueError(t("server.name_too_long"))

    if len(group) > 64:
        raise ValueError(t("server.group_too_long"))

    url = normalize_service_url(raw_url)
    reachable, message = check_url_reachable(url)

    if not reachable:
        raise ValueError(t("server.not_saved", message=message))

    cfg = read_yaml_config()
    services = cfg.setdefault("services", [])

    normalized_url = url.lower().rstrip("/")
    for service in services:
        for item in service.get("urls", []) or []:
            existing = str(item.get("url") or "").strip().lower().rstrip("/")
            if existing == normalized_url:
                raise ValueError(t("server.url_duplicate"))

    service = {
        "name": name,
        "group": group,
        "favorite": favorite,
    }

    if container_name:
        service["container"] = container_name

    if note:
        service["note"] = note

    service["urls"] = [{
        "name": link_name,
        "url": url,
    }]

    services.append(service)
    write_yaml_config(cfg)
    return service


def normalize_optional_edit_url(raw_url):
    raw_url = str(raw_url or "").strip()
    if not raw_url:
        return ""
    if "://" not in raw_url:
        raw_url = f"http://{raw_url}"
    return raw_url


def edit_service_in_config(payload):
    card_id = str(payload.get("id") or "").strip()
    lookup_container = str(payload.get("lookup_container") or payload.get("current_container") or "").strip()
    new_container = str(payload.get("container") or "").strip()
    display_name = str(payload.get("name") or lookup_container or new_container or "Dienst").strip()
    group = str(payload.get("group") or "Docker").strip() or "Docker"
    raw_url = str(payload.get("url") or "").strip()
    link_name = str(payload.get("link_name") or "Web UI").strip() or "Web UI"
    note = str(payload.get("note") or "").strip()
    favorite = bool(payload.get("favorite", False))

    if len(display_name) > 80:
        raise ValueError(t("server.name_too_long"))

    if len(group) > 64:
        raise ValueError(t("server.group_too_long"))

    url = normalize_optional_edit_url(raw_url)

    # Absichtlich keine Erreichbarkeitsprüfung und kein URL-Zwang hier:
    # Der Edit-Dialog ist für automatisch erkannte host/macvlan-Container und
    # manuelle Metadaten gedacht. Eine leere URL ist erlaubt; dann werden nur
    # Name/Gruppe/Kommentar/Favorit/Container gespeichert.

    cfg = read_yaml_config()
    services = cfg.setdefault("services", [])

    if url:
        normalized_url = url.lower().rstrip("/")
        for service in services:
            for item in service.get("urls", []) or []:
                existing = str(item.get("url") or "").strip().lower().rstrip("/")
                if existing == normalized_url:
                    # Der vorhandene eigene Eintrag darf editiert werden.
                    own_index = service_index_from_card(card_id, lookup_container or new_container, services)
                    if own_index is None or services[own_index] is not service:
                        raise ValueError(t("server.url_duplicate"))

    index = service_index_from_card(card_id, lookup_container or new_container, services)

    if index is None:
        service = {
            "name": display_name,
            "group": group,
            "favorite": favorite,
            "urls": [],
        }
        container_to_store = new_container or lookup_container
        if container_to_store:
            service["container"] = container_to_store
        services.append(service)
    else:
        service = services[index]
        service["name"] = display_name
        service["group"] = group
        service["favorite"] = favorite

        container_to_store = new_container or lookup_container
        if container_to_store:
            service["container"] = container_to_store
        elif "container" in service:
            service.pop("container", None)

    if note:
        service["note"] = note
    else:
        service.pop("note", None)

    urls = service.setdefault("urls", [])

    if url:
        if urls and isinstance(urls[0], dict):
            urls[0]["name"] = link_name
            urls[0]["url"] = url
        else:
            urls.insert(0, {"name": link_name, "url": url})
    else:
        # Leeres URL-Feld ist erlaubt. Falls ein primärer manueller Link existiert,
        # wird nur dieser entfernt; weitere Links bleiben erhalten.
        if urls and isinstance(urls[0], dict):
            del urls[0]

    write_yaml_config(cfg)
    return service


TEMPLATE = """
<!doctype html>
<html lang="{{ ui.app.html_lang }}">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{{ refresh_seconds }}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ ui.app.title }}</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: rgba(17, 24, 39, 0.84);
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #60a5fa;
      --ok: #34d399;
      --manual: #c084fc;
      --warn: #fbbf24;
      --error: #f87171;
      --border: rgba(148, 163, 184, 0.22);
      --menu: #111827;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(37, 99, 235, .36), transparent 32rem),
        radial-gradient(circle at top right, rgba(126, 34, 206, .28), transparent 28rem),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
    }
    header {
      max-width: 1280px;
      margin: 0 auto;
      padding: 34px 24px 12px;
    }
    .header-row {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 18px;
    }
    h1 {
      margin: 0;
      font-size: clamp(30px, 5vw, 52px);
      letter-spacing: -0.05em;
      line-height: 1;
    }
    .subtitle {
      margin-top: 12px;
      color: var(--muted);
      font-size: 15px;
    }
    .top-actions {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-shrink: 0;
    }
    .primary-button {
      border: 0;
      border-radius: 14px;
      background: var(--accent);
      color: #082f49;
      padding: 11px 14px;
      font-size: 14px;
      font-weight: 800;
      cursor: pointer;
      box-shadow: 0 12px 35px rgba(96,165,250,.25);
    }
    .search {
      margin-top: 22px;
      width: min(520px, 100%);
      border: 1px solid var(--border);
      border-radius: 14px;
      background: rgba(255,255,255,.06);
      color: var(--text);
      padding: 13px 14px;
      font-size: 15px;
      outline: none;
    }
    main {
      max-width: 1280px;
      margin: 0 auto;
      padding: 18px 24px 54px;
    }
    .group {
      margin-top: 28px;
    }
    .group-heading {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 12px;
    }
    .group h2 {
      color: var(--text);
      margin: 0;
      font-size: 17px;
      letter-spacing: .02em;
    }
    .show-hidden-button {
      border: 1px solid var(--border);
      background: rgba(255,255,255,.05);
      color: var(--muted);
      border-radius: 999px;
      cursor: pointer;
      padding: 4px 8px;
      font-size: 12px;
    }
    .show-hidden-button:hover {
      color: var(--text);
      border-color: rgba(96,165,250,.55);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(285px, 1fr));
      gap: 16px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 18px;
      box-shadow: 0 18px 55px rgba(0,0,0,0.28);
      backdrop-filter: blur(10px);
      min-height: 190px;
    }
    .card:hover {
      border-color: rgba(96,165,250,.48);
    }
    .topline {
      display: block;
    }
    .name {
      font-weight: 780;
      font-size: 19px;
      line-height: 1.18;
      overflow-wrap: anywhere;
      word-break: normal;
      margin-bottom: 10px;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }
    .actions .badge {
      margin-left: auto;
    }
    .icon-button {
      border: 0;
      background: transparent;
      color: var(--muted);
      font-size: 20px;
      line-height: 1;
      cursor: pointer;
      padding: 0 1px;
      margin-top: 0;
    }
    .icon-button:hover {
      transform: scale(1.08);
      color: var(--text);
    }
    .favorite-button {
      font-size: 24px;
      margin-top: 0;
    }
    .favorite-button.active {
      color: var(--warn);
    }
    .delete-button:hover {
      color: var(--error);
    }
    .hide-button:hover {
      color: var(--warn);
    }
    .edit-button {
      color: var(--accent);
      border: 1px solid rgba(96,165,250,.35);
      border-radius: 8px;
      font-size: 11px;
      font-weight: 850;
      letter-spacing: .03em;
      padding: 3px 5px;
      margin-top: 0;
      background: rgba(96,165,250,.10);
    }
    .edit-button:hover {
      color: var(--text);
      background: rgba(96,165,250,.22);
      border-color: rgba(96,165,250,.7);
    }
    .badge {
      font-size: 12px;
      color: #052e21;
      background: var(--ok);
      border-radius: 999px;
      padding: 4px 8px;
      font-weight: 760;
      white-space: nowrap;
    }
    .badge.manual {
      background: var(--manual);
      color: #2e1065;
    }
    .meta {
      color: var(--muted);
      font-size: 12px;
      margin-top: 9px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .note {
      color: #dbeafe;
      background: rgba(96,165,250,.1);
      border: 1px solid rgba(96,165,250,.2);
      margin-top: 11px;
      padding: 9px 10px;
      border-radius: 12px;
      font-size: 13px;
      line-height: 1.35;
    }
    .links {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 16px;
    }
    a.service {
      display: block;
      text-decoration: none;
      color: var(--text);
      background: rgba(96,165,250,0.12);
      border: 1px solid rgba(96,165,250,0.32);
      padding: 11px 12px;
      border-radius: 14px;
      transition: transform .12s ease, background .12s ease, border-color .12s ease;
    }
    a.service:hover {
      transform: translateY(-1px);
      background: rgba(96,165,250,0.20);
      border-color: rgba(96,165,250,0.65);
    }
    .url {
      color: var(--accent);
      font-size: 13px;
      margin-top: 4px;
      overflow-wrap: anywhere;
    }
    .portline {
      color: var(--muted);
      font-size: 12px;
      margin-top: 5px;
    }
    .empty {
      color: var(--warn);
      font-size: 13px;
      margin-top: 15px;
      padding: 10px;
      border: 1px dashed rgba(251,191,36,0.45);
      border-radius: 13px;
      background: rgba(251,191,36,0.08);
    }
    .empty-group {
      color: var(--muted);
      border: 1px dashed var(--border);
      border-radius: 16px;
      padding: 14px;
      background: rgba(255,255,255,.035);
      font-size: 13px;
    }
    .error {
      background: rgba(248,113,113,0.12);
      border: 1px solid rgba(248,113,113,0.35);
      border-radius: 18px;
      padding: 16px;
      color: #fecaca;
    }
    .context-menu, .modal-card {
      background: var(--menu);
      border: 1px solid var(--border);
      box-shadow: 0 24px 70px rgba(0,0,0,.45);
    }
    .context-menu {
      position: fixed;
      z-index: 1000;
      display: none;
      width: 280px;
      border-radius: 16px;
      padding: 10px;
    }
    .context-title {
      font-size: 13px;
      color: var(--muted);
      padding: 6px 8px 10px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 8px;
      overflow-wrap: anywhere;
    }
    .menu-button {
      width: 100%;
      display: block;
      text-align: left;
      border: 0;
      border-radius: 10px;
      background: transparent;
      color: var(--text);
      padding: 9px 10px;
      cursor: pointer;
      font-size: 14px;
    }
    .menu-button:hover {
      background: rgba(96,165,250,.16);
    }
    .new-group {
      display: flex;
      gap: 6px;
      margin-top: 9px;
      border-top: 1px solid var(--border);
      padding-top: 10px;
    }
    input, textarea, select {
      border: 1px solid var(--border);
      background: rgba(255,255,255,.06);
      color: var(--text);
      border-radius: 10px;
      padding: 9px 10px;
      outline: none;
      font: inherit;
    }
    textarea { min-height: 78px; resize: vertical; }
    .new-group input { min-width: 0; flex: 1; }
    .new-group button, .secondary-button {
      border: 0;
      border-radius: 10px;
      padding: 9px 11px;
      color: #082f49;
      background: var(--accent);
      font-weight: 700;
      cursor: pointer;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 1100;
      display: none;
      align-items: center;
      justify-content: center;
      background: rgba(0,0,0,.58);
      padding: 20px;
    }
    .modal-card {
      width: min(560px, 100%);
      border-radius: 20px;
      padding: 18px;
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
    }
    .modal-header h3 {
      margin: 0;
      font-size: 20px;
    }
    .close-button {
      border: 0;
      background: transparent;
      color: var(--muted);
      font-size: 24px;
      cursor: pointer;
    }
    .form-grid {
      display: grid;
      gap: 10px;
    }
    .form-row {
      display: grid;
      gap: 6px;
    }
    .form-row label {
      color: var(--muted);
      font-size: 13px;
    }
    .checkbox-row {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 14px;
    }
    .modal-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      margin-top: 16px;
    }
    .muted-button {
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 9px 11px;
      color: var(--text);
      background: rgba(255,255,255,.06);
      font-weight: 700;
      cursor: pointer;
    }
    .modal-error {
      display: none;
      color: #fecaca;
      background: rgba(248,113,113,.12);
      border: 1px solid rgba(248,113,113,.35);
      border-radius: 12px;
      padding: 10px;
      font-size: 13px;
      margin-top: 10px;
    }
    .hidden-list {
      display: grid;
      gap: 8px;
    }
    .hidden-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,.04);
      border-radius: 12px;
      padding: 10px;
    }
    .hidden-name { font-weight: 700; }
    .hidden-meta { color: var(--muted); font-size: 12px; margin-top: 3px; }
    code { color: #bfdbfe; }
  </style>
</head>
<body>
  <header>
    <div class="header-row">
      <div>
        <h1>{{ ui.app.title }}</h1>
        <div class="subtitle">
          {{ ui.app.subtitle }} · {{ ui.app.host }}: {{ base_host }} · {{ ui.app.refresh }}: {{ refresh_seconds }}s · {{ ui.app.timestamp }}: {{ now }}
        </div>
      </div>
      <div class="top-actions">
        <button class="primary-button" id="openAddService">{{ ui.buttons.add_service }}</button>
      </div>
    </div>
    <input class="search" id="search" placeholder="{{ ui.app.search_placeholder }}" autocomplete="off">
  </header>

  <main>
    {% if error %}
      <div class="error">{{ error }}</div>
    {% else %}
      {% for group, items in grouped.items() %}
        <section class="group" data-group-section="{{ group }}">
          <div class="group-heading">
            <h2>{{ group }}</h2>
            {% if hidden_by_group.get(group) %}
              <button class="show-hidden-button" data-hidden-group="{{ group }}" title="{{ ui.tooltips.show_hidden }}">👁 {{ hidden_by_group[group]|length }}</button>
            {% endif %}
          </div>
          {% if items %}
            <div class="grid">
              {% for row in items %}
                <article class="card" data-card-id="{{ row.id }}" data-container="{{ row.container }}" data-name="{{ row.name }}" data-group="{{ row.group }}" data-favorite="{{ 'true' if row.favorite else 'false' }}" data-has-config="{{ 'true' if row.has_config else 'false' }}" data-note="{{ row.note }}" data-config-url="{{ row.config_url }}" data-config-link-name="{{ row.config_link_name }}" data-search="{{ (row.name ~ ' ' ~ row.group ~ ' ' ~ row.container ~ ' ' ~ row.image)|lower }}">
                  <div class="topline">
                    <div class="name">{{ row.name }}</div>
                    <div class="actions">
                      <button class="icon-button favorite-button {% if row.favorite %}active{% endif %}" title="{{ ui.tooltips.toggle_favorite }}" aria-label="{{ ui.tooltips.toggle_favorite }}">★</button>
                      <button class="icon-button edit-button" title="{{ ui.tooltips.edit_service }}" aria-label="{{ ui.tooltips.edit_service }}">{{ ui.buttons.edit }}</button>
                      <button class="icon-button hide-button" title="{{ ui.tooltips.hide_service }}" aria-label="{{ ui.tooltips.hide_service }}">◉</button>
                      {% if row.has_config %}
                        <button class="icon-button delete-button" title="{{ ui.tooltips.delete_service }}" aria-label="{{ ui.tooltips.delete_service }}">🗑</button>
                      {% endif %}
                      <div class="badge {% if row.manual_only %}manual{% endif %}">{{ row.status }}</div>
                    </div>
                  </div>

                  <div class="meta">
                    {% if row.container %}{{ ui.fields.container }}: {{ row.container }}<br>{% endif %}
                    {% if row.image %}{{ ui.fields.image }}: {{ row.image }}<br>{% endif %}
                    {{ ui.fields.network }}: {{ row.network_mode }}
                  </div>

                  {% if row.note %}
                    <div class="note">{{ row.note }}</div>
                  {% endif %}

                  {% if row.has_links %}
                    <div class="links">
                      {% for link in row.links %}
                        <a class="service" href="{{ link.url }}" target="_blank" rel="noopener noreferrer">
                          <strong>{{ link.name }}</strong>
                          <div class="url">{{ link.url }}</div>
                          <div class="portline">
                            {% if link.host_port %}
                              {{ ui.fields.host }} {{ link.host_port }}
                              {% if link.container_port %}→ {{ ui.fields.container }} {{ link.container_port }}{% endif %}
                              {% if link.proto %}/{{ link.proto }}{% endif %}
                              · {{ link.bind_note }}
                            {% else %}
                              {{ link.bind_note }}
                            {% endif %}
                          </div>
                        </a>
                      {% endfor %}
                    </div>
                  {% else %}
                    <div class="empty">
                      {{ ui.messages.no_ports }}
                    </div>
                  {% endif %}
                </article>
              {% endfor %}
            </div>
          {% else %}
            <div class="empty-group">{{ ui.messages.all_hidden }}</div>
          {% endif %}
        </section>
      {% endfor %}
    {% endif %}
  </main>

  <div class="context-menu" id="contextMenu">
    <div class="context-title" id="contextTitle"></div>
    <div id="groupButtons"></div>
    <div class="new-group">
      <input id="newGroupInput" placeholder="{{ ui.placeholders.new_group }}">
      <button id="newGroupButton">{{ ui.buttons.ok }}</button>
    </div>
  </div>

  <div class="modal-backdrop" id="addServiceModal">
    <div class="modal-card">
      <div class="modal-header">
        <h3>{{ ui.dialogs.add_title }}</h3>
        <button class="close-button" data-close-modal="addServiceModal">×</button>
      </div>
      <form id="addServiceForm" class="form-grid">
        <div class="form-row">
          <label for="serviceName">{{ ui.fields.name }}</label>
          <input id="serviceName" name="name" required placeholder="{{ ui.placeholders.name }}">
        </div>
        <div class="form-row">
          <label for="serviceGroup">{{ ui.fields.group }}</label>
          <input id="serviceGroup" name="group" list="groupList" value="Manuell" required>
          <datalist id="groupList">
            {% for group in groups %}<option value="{{ group }}">{% endfor %}
          </datalist>
        </div>
        <div class="form-row">
          <label for="serviceUrl">{{ ui.fields.url }}</label>
          <input id="serviceUrl" name="url" required placeholder="{{ ui.placeholders.url }}">
        </div>
        <div class="form-row">
          <label for="serviceLinkName">{{ ui.fields.link_name }}</label>
          <input id="serviceLinkName" name="link_name" value="Web UI">
        </div>
        <div class="form-row">
          <label for="serviceContainer">{{ ui.fields.container_optional }}</label>
          <input id="serviceContainer" name="container" placeholder="{{ ui.placeholders.container }}">
        </div>
        <div class="form-row">
          <label for="serviceNote">{{ ui.fields.note_optional }}</label>
          <textarea id="serviceNote" name="note" placeholder="{{ ui.placeholders.note }}"></textarea>
        </div>
        <label class="checkbox-row"><input type="checkbox" id="serviceFavorite" name="favorite"> {{ ui.fields.favorite }}</label>
        <div class="modal-error" id="addServiceError"></div>
        <div class="modal-actions">
          <button type="button" class="muted-button" data-close-modal="addServiceModal">{{ ui.buttons.cancel }}</button>
          <button type="submit" class="secondary-button" id="saveServiceButton">{{ ui.buttons.check_save }}</button>
        </div>
      </form>
    </div>
  </div>

  <div class="modal-backdrop" id="addressModal">
    <div class="modal-card">
      <div class="modal-header">
        <h3 id="addressModalTitle">{{ ui.dialogs.edit_title }}</h3>
        <button class="close-button" data-close-modal="addressModal">×</button>
      </div>
      <form id="addressForm" class="form-grid">
        <div class="form-row">
          <label for="editName">{{ ui.fields.name }}</label>
          <input id="editName" name="name" placeholder="{{ ui.placeholders.display_name }}">
        </div>
        <div class="form-row">
          <label for="editGroup">{{ ui.fields.group }}</label>
          <input id="editGroup" name="group" list="groupList" placeholder="{{ ui.placeholders.group }}">
        </div>
        <div class="form-row">
          <label for="editContainer">{{ ui.fields.container_optional }}</label>
          <input id="editContainer" name="container" placeholder="{{ ui.placeholders.container }}">
        </div>
        <div class="form-row">
          <label for="addressUrl">{{ ui.fields.url_optional }}</label>
          <input id="addressUrl" name="url" placeholder="{{ ui.placeholders.url_optional }}">
        </div>
        <div class="form-row">
          <label for="addressLinkName">{{ ui.fields.link_name }}</label>
          <input id="addressLinkName" name="link_name" value="Web UI">
        </div>
        <div class="form-row">
          <label for="addressNote">{{ ui.fields.note_optional }}</label>
          <textarea id="addressNote" name="note" placeholder="{{ ui.placeholders.note_optional }}"></textarea>
        </div>
        <label class="checkbox-row"><input type="checkbox" id="editFavorite" name="favorite"> {{ ui.fields.favorite }}</label>
        <div class="modal-error" id="addressError"></div>
        <div class="modal-actions">
          <button type="button" class="muted-button" data-close-modal="addressModal">{{ ui.buttons.cancel }}</button>
          <button type="submit" class="secondary-button" id="saveAddressButton">{{ ui.buttons.save }}</button>
        </div>
      </form>
    </div>
  </div>

  <div class="modal-backdrop" id="hiddenModal">
    <div class="modal-card">
      <div class="modal-header">
        <h3 id="hiddenModalTitle">{{ ui.dialogs.hidden_title }}</h3>
        <button class="close-button" data-close-modal="hiddenModal">×</button>
      </div>
      <div class="hidden-list" id="hiddenList"></div>
    </div>
  </div>

  <script>
    const groups = {{ groups|tojson }};
    const hiddenByGroup = {{ hidden_by_group|tojson }};
    const ui = {{ ui|tojson }};
    const search = document.getElementById("search");
    const menu = document.getElementById("contextMenu");
    const contextTitle = document.getElementById("contextTitle");
    const groupButtons = document.getElementById("groupButtons");
    const newGroupInput = document.getElementById("newGroupInput");
    const newGroupButton = document.getElementById("newGroupButton");
    const addServiceModal = document.getElementById("addServiceModal");
    const hiddenModal = document.getElementById("hiddenModal");
    const addServiceForm = document.getElementById("addServiceForm");
    const addServiceError = document.getElementById("addServiceError");
    const saveServiceButton = document.getElementById("saveServiceButton");
    const addressForm = document.getElementById("addressForm");
    const addressError = document.getElementById("addressError");
    const saveAddressButton = document.getElementById("saveAddressButton");
    const addressModalTitle = document.getElementById("addressModalTitle");
    let activeCard = null;
    let activeAddressCard = null;

    search.addEventListener("input", () => {
      const query = search.value.trim().toLowerCase();
      document.querySelectorAll(".card").forEach(card => {
        card.style.display = card.dataset.search.includes(query) ? "" : "none";
      });
      document.querySelectorAll(".group").forEach(group => {
        const cards = [...group.querySelectorAll(".card")];
        const visible = cards.length === 0 || cards.some(card => card.style.display !== "none");
        group.style.display = visible ? "" : "none";
      });
    });

    document.getElementById("openAddService").addEventListener("click", () => openModal("addServiceModal"));

    document.querySelectorAll("[data-close-modal]").forEach(button => {
      button.addEventListener("click", () => closeModal(button.dataset.closeModal));
    });

    document.querySelectorAll(".modal-backdrop").forEach(backdrop => {
      backdrop.addEventListener("click", event => {
        if (event.target === backdrop) {
          backdrop.style.display = "none";
        }
      });
    });

    document.querySelectorAll(".card").forEach(card => {
      card.addEventListener("contextmenu", event => {
        event.preventDefault();
        activeCard = card;
        openMenu(event.clientX, event.clientY, card);
      });
    });

    document.querySelectorAll(".favorite-button").forEach(button => {
      button.addEventListener("click", async event => {
        event.preventDefault();
        event.stopPropagation();
        const card = button.closest(".card");
        await postAndReload("/api/favorite", {
          id: card.dataset.cardId,
          container: card.dataset.container,
          name: card.dataset.name,
          favorite: card.dataset.favorite !== "true"
        }, ui.messages.favorite_save_failed);
      });
    });

    document.querySelectorAll(".edit-button").forEach(button => {
      button.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        const card = button.closest(".card");
        openAddressModal(card);
      });
    });

    document.querySelectorAll(".hide-button").forEach(button => {
      button.addEventListener("click", async event => {
        event.preventDefault();
        event.stopPropagation();
        const card = button.closest(".card");
        if (!confirm(ui.dialogs.confirm_hide.replace("{name}", card.dataset.name))) return;
        await postAndReload("/api/hide", {
          id: card.dataset.cardId,
          container: card.dataset.container,
          name: card.dataset.name,
          group: card.dataset.group
        }, ui.messages.hide_failed);
      });
    });

    document.querySelectorAll(".delete-button").forEach(button => {
      button.addEventListener("click", async event => {
        event.preventDefault();
        event.stopPropagation();
        const card = button.closest(".card");
        if (!confirm(ui.dialogs.confirm_delete.replace("{name}", card.dataset.name))) return;
        await postAndReload("/api/delete", {
          id: card.dataset.cardId,
          container: card.dataset.container
        }, ui.messages.delete_failed);
      });
    });

    document.querySelectorAll(".show-hidden-button").forEach(button => {
      button.addEventListener("click", () => openHiddenModal(button.dataset.hiddenGroup));
    });

    document.addEventListener("click", event => {
      if (!menu.contains(event.target)) {
        closeMenu();
      }
    });

    document.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        closeMenu();
        closeModal("addServiceModal");
        closeModal("addressModal");
        closeModal("hiddenModal");
      }
    });

    addServiceForm.addEventListener("submit", async event => {
      event.preventDefault();
      addServiceError.style.display = "none";
      saveServiceButton.disabled = true;
      saveServiceButton.textContent = ui.buttons.checking;

      const formData = new FormData(addServiceForm);
      const payload = Object.fromEntries(formData.entries());
      payload.favorite = document.getElementById("serviceFavorite").checked;

      const response = await fetch("/api/service", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        addServiceError.textContent = data.error || ui.messages.service_save_failed;
        addServiceError.style.display = "block";
        saveServiceButton.disabled = false;
        saveServiceButton.textContent = ui.buttons.check_save;
        return;
      }

      window.location.reload();
    });

    addressForm.addEventListener("submit", async event => {
      event.preventDefault();
      if (!activeAddressCard) return;

      addressError.style.display = "none";
      saveAddressButton.disabled = true;
      saveAddressButton.textContent = ui.buttons.saving;

      const formData = new FormData(addressForm);
      const payload = Object.fromEntries(formData.entries());
      payload.id = activeAddressCard.dataset.cardId;
      payload.lookup_container = activeAddressCard.dataset.container;
      payload.favorite = document.getElementById("editFavorite").checked;

      const response = await fetch("/api/address", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        addressError.textContent = data.error || ui.messages.service_save_failed;
        addressError.style.display = "block";
        saveAddressButton.disabled = false;
        saveAddressButton.textContent = ui.buttons.save;
        return;
      }

      window.location.reload();
    });

    function openAddressModal(card) {
      activeAddressCard = card;
      addressModalTitle.textContent = ui.dialogs.edit_title_for.replace("{name}", card.dataset.name);
      document.getElementById("editName").value = card.dataset.name || "";
      document.getElementById("editGroup").value = card.dataset.group || "Docker";
      document.getElementById("editContainer").value = card.dataset.container || "";
      document.getElementById("addressUrl").value = card.dataset.configUrl || "";
      document.getElementById("addressLinkName").value = card.dataset.configLinkName || "Web UI";
      document.getElementById("addressNote").value = card.dataset.note || "";
      document.getElementById("editFavorite").checked = card.dataset.favorite === "true";
      addressError.style.display = "none";
      saveAddressButton.disabled = false;
      saveAddressButton.textContent = ui.buttons.save;
      openModal("addressModal");
      setTimeout(() => document.getElementById("editName").focus(), 50);
    }

    function openModal(id) {
      document.getElementById(id).style.display = "flex";
    }

    function closeModal(id) {
      document.getElementById(id).style.display = "none";
    }

    function openMenu(x, y, card) {
      contextTitle.textContent = ui.dialogs.group_change.replace("{name}", card.dataset.name);
      groupButtons.innerHTML = "";

      groups.forEach(group => {
        const button = document.createElement("button");
        button.className = "menu-button";
        button.textContent = group === card.dataset.group ? `✓ ${group}` : group;
        button.addEventListener("click", () => setGroup(group));
        groupButtons.appendChild(button);
      });

      newGroupInput.value = "";
      menu.style.display = "block";

      const rect = menu.getBoundingClientRect();
      const left = Math.min(x, window.innerWidth - rect.width - 12);
      const top = Math.min(y, window.innerHeight - rect.height - 12);

      menu.style.left = `${Math.max(12, left)}px`;
      menu.style.top = `${Math.max(12, top)}px`;
    }

    function closeMenu() {
      menu.style.display = "none";
      activeCard = null;
    }

    async function setGroup(group) {
      if (!activeCard || !group.trim()) return;
      await postAndReload("/api/group", {
        id: activeCard.dataset.cardId,
        container: activeCard.dataset.container,
        name: activeCard.dataset.name,
        group: group.trim()
      }, ui.messages.group_save_failed);
    }

    newGroupButton.addEventListener("click", () => setGroup(newGroupInput.value));

    newGroupInput.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        setGroup(newGroupInput.value);
      }
    });

    async function postAndReload(url, payload, fallbackError) {
      const response = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        alert(data.error || fallbackError);
        return;
      }

      window.location.reload();
    }

    function openHiddenModal(group) {
      const list = hiddenByGroup[group] || [];
      document.getElementById("hiddenModalTitle").textContent = ui.dialogs.hidden_title_group.replace("{group}", group);
      const hiddenList = document.getElementById("hiddenList");
      hiddenList.innerHTML = "";

      list.forEach(item => {
        const row = document.createElement("div");
        row.className = "hidden-item";

        const text = document.createElement("div");
        const title = document.createElement("div");
        title.className = "hidden-name";
        title.textContent = item.name;
        const meta = document.createElement("div");
        meta.className = "hidden-meta";
        meta.textContent = item.container ? `${ui.fields.container}: ${item.container}` : item.note || ui.fields.manual_service;
        text.appendChild(title);
        text.appendChild(meta);

        const button = document.createElement("button");
        button.className = "secondary-button";
        button.textContent = ui.buttons.unhide;
        button.addEventListener("click", async () => {
          await postAndReload("/api/unhide", {id: item.id}, ui.messages.unhide_failed);
        });

        row.appendChild(text);
        row.appendChild(button);
        hiddenList.appendChild(row);
      });

      openModal("hiddenModal");
    }
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    try:
        rows = read_dashboard_rows()
        hidden_by_group = read_hidden_by_group()

        grouped = {}
        favorite_rows = [row for row in rows if row.get("favorite")]

        if favorite_rows:
            grouped[get_i18n_value(load_translations(), "app.favorites_group", "★ Favoriten")] = favorite_rows

        for row in rows:
            grouped.setdefault(row["group"], []).append(row)

        for group in hidden_by_group:
            grouped.setdefault(group, [])

        return render_template_string(
            TEMPLATE,
            rows=rows,
            grouped=grouped,
            hidden_by_group=hidden_by_group,
            groups=get_group_names(rows),
            ui=load_translations(),
            language=LANGUAGE,
            error=None,
            base_host=BASE_HOST,
            refresh_seconds=REFRESH_SECONDS,
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    except Exception as exc:
        return render_template_string(
            TEMPLATE,
            rows=[],
            grouped={},
            hidden_by_group={},
            groups=get_group_names([]),
            ui=load_translations(),
            language=LANGUAGE,
            error=t("errors.docker_config_read_failed", error=html.escape(str(exc))),
            base_host=BASE_HOST,
            refresh_seconds=REFRESH_SECONDS,
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ), 500


@app.post("/api/group")
def api_group():
    try:
        payload = request.get_json(force=True) or {}
        update_group_in_config(
            str(payload.get("id") or ""),
            str(payload.get("container") or ""),
            str(payload.get("name") or ""),
            str(payload.get("group") or ""),
        )
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/favorite")
def api_favorite():
    try:
        payload = request.get_json(force=True) or {}
        update_favorite_in_config(
            str(payload.get("id") or ""),
            str(payload.get("container") or ""),
            str(payload.get("name") or ""),
            bool(payload.get("favorite", False)),
        )
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/service")
def api_service():
    try:
        payload = request.get_json(force=True) or {}
        service = create_service_in_config(payload)
        return jsonify({"ok": True, "service": service})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/address")
def api_address():
    try:
        payload = request.get_json(force=True) or {}
        service = edit_service_in_config(payload)
        return jsonify({"ok": True, "service": service})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/delete")
def api_delete():
    try:
        payload = request.get_json(force=True) or {}
        delete_service_from_config(str(payload.get("id") or ""), str(payload.get("container") or ""))
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/hide")
def api_hide():
    try:
        payload = request.get_json(force=True) or {}
        hide_service_in_config(
            str(payload.get("id") or ""),
            str(payload.get("container") or ""),
            str(payload.get("name") or ""),
            str(payload.get("group") or "Docker"),
        )
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/unhide")
def api_unhide():
    try:
        payload = request.get_json(force=True) or {}
        unhide_service_in_config(str(payload.get("id") or ""))
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
