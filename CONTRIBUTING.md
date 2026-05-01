# Contributing

Thanks for considering a contribution.

## Development basics

Use a private `config/services.yaml` for local testing and keep it out of git.

Run locally with Docker Compose:

```bash
sudo docker compose up -d --build
```

Check logs:

```bash
sudo docker compose logs --tail=100 intranet-dashboard
```

## Pull requests

Keep changes focused. Update language files when adding or changing visible UI text. Do not include private IP addresses, hostnames, screenshots, or service lists.
