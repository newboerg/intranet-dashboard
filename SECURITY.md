# Security Policy

## Intended use

This dashboard is intended for trusted private networks only. Do not expose it directly to the public internet.

## Docker socket access

The dashboard should access Docker only through `tecnativa/docker-socket-proxy`. Avoid mounting `/var/run/docker.sock` directly into the dashboard container.

## Private configuration

Do not publish `config/services.yaml`, backups, screenshots with internal hostnames, or private notes. Use `config/services.example.yaml` for public examples.

## Reporting security issues

Please report security issues privately to the project maintainer. Do not open a public issue with exploit details before a fix is available.
