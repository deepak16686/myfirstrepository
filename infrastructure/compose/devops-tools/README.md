# DevOps Tools Compose

This compose file runs the main portal backend and the public nginx proxy.

Run from the repository root:

```powershell
docker compose --env-file services\devops-tools-backend\.env -f infrastructure\compose\devops-tools\docker-compose.yml up -d --build
```

Important paths:

- Backend/UI build context: `services/devops-tools-backend`
- Runtime env file: `services/devops-tools-backend/.env`
- Nginx config: `infrastructure/reverse-proxy/nginx/portal.conf`
- TLS cert mount: `infrastructure/reverse-proxy/nginx/certs`
- Basic auth file: `infrastructure/reverse-proxy/nginx/htpasswd`
