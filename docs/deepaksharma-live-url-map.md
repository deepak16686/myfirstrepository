# deepaksharma.live URL map

Generated from `nginx-proxy/portal.conf` on 2026-05-04 after removing Vault from the public route list.
Validated again on 2026-05-05 after expanding the DevOps Portal registry to all public project sub-services.

| Tool | Public URL | Upstream | Access |
|---|---|---|---|
| Brandmatik | https://brandmatik.deepaksharma.live | `http://brandmatik-api-gateway:8000` | App/native auth or public app |
| Brandmatik Analytics | https://brandmatik-analytics.deepaksharma.live | `http://brandmatik-analytics-service:8006` | App/native auth or public app |
| Brandmatik Business | https://brandmatik-business.deepaksharma.live | `http://brandmatik-business-service:8004` | App/native auth or public app |
| Brandmatik Content | https://brandmatik-content.deepaksharma.live | `http://brandmatik-content-generator:8003` | App/native auth or public app |
| Brandmatik Feedback | https://brandmatik-feedback.deepaksharma.live | `http://brandmatik-feedback-service:8007` | App/native auth or public app |
| Brandmatik Mock | https://brandmatik-mock.deepaksharma.live | `http://brandmatik-mock-social-poster:8010` | App/native auth or public app |
| Brandmatik Notification | https://brandmatik-notification.deepaksharma.live | `http://brandmatik-notification-service:8008` | App/native auth or public app |
| Brandmatik Posting | https://brandmatik-posting.deepaksharma.live | `http://brandmatik-posting-service:8005` | App/native auth or public app |
| Brandmatik Qdrant | https://brandmatik-qdrant.deepaksharma.live | `http://brandmatik-qdrant:6333` | Basic auth |
| Brandmatik Scoring | https://brandmatik-scoring.deepaksharma.live | `http://brandmatik-scoring-engine:8002` | App/native auth or public app |
| Brandmatik Trend | https://brandmatik-trend.deepaksharma.live | `http://brandmatik-trend-collector:8001` | App/native auth or public app |
| Cadvisor | https://cadvisor.deepaksharma.live | `http://cadvisor:8080` | Basic auth |
| Chaos Ai | https://chaos-ai.deepaksharma.live | `http://chaos-ai-engine:8084` | App/native auth or public app |
| Chaos Auth | https://chaos-auth.deepaksharma.live | `http://chaos-auth-service:8081` | App/native auth or public app |
| Chaos Credentials | https://chaos-credentials.deepaksharma.live | `http://chaos-credentials-dashboard:9091` | Basic auth |
| Chaos Experiment | https://chaos-experiment.deepaksharma.live | `http://chaos-experiment-engine:8082` | App/native auth or public app |
| Chaos Grafana | https://chaos-grafana.deepaksharma.live | `http://chaos-grafana:3000` | App/native auth or public app |
| Chaos Minio | https://chaos-minio.deepaksharma.live | `http://chaos-minio:9001` | App/native auth or public app |
| Chaos Nats | https://chaos-nats.deepaksharma.live | `http://chaos-nats:8222` | Basic auth |
| Chaos Notify | https://chaos-notify.deepaksharma.live | `http://chaos-notification-service:8086` | App/native auth or public app |
| Chaos Platform | https://chaos-platform.deepaksharma.live | `http://chaos-api-gateway:8080` | App/native auth or public app |
| Chaos Portal | https://chaos-portal.deepaksharma.live | `http://chaos-portal-ui:3001` | App/native auth or public app |
| Chaos Prometheus | https://chaos-prometheus.deepaksharma.live | `http://chaos-prometheus:9090` | Basic auth |
| Chaos Report | https://chaos-report.deepaksharma.live | `http://chaos-report-service:8085` | App/native auth or public app |
| Chaos Target1 | https://chaos-target1.deepaksharma.live | `http://chaos-target-app-1:8090` | App/native auth or public app |
| Chaos Target2 | https://chaos-target2.deepaksharma.live | `http://chaos-target-app-2:8090` | App/native auth or public app |
| Chaos Target3 | https://chaos-target3.deepaksharma.live | `http://chaos-target-app-3:8090` | App/native auth or public app |
| Chaos Telemetry | https://chaos-telemetry.deepaksharma.live | `http://chaos-telemetry-aggregator:8083` | App/native auth or public app |
| Chatbot Legacy Alias | https://chatbot.deepaksharma.live | `http://devops-tools-backend:8003` | Redirects to unified DevOps Portal |
| Chromadb | https://chromadb.deepaksharma.live | `http://chromadb:8000` | Basic auth |
| Chromadb Admin | https://chromadb-admin.deepaksharma.live | `http://chromadb-admin:3000` | Basic auth |
| Dcgm Exporter | https://dcgm-exporter.deepaksharma.live | `http://dcgm-exporter:9400` | Basic auth |
| Gitea | https://gitea.deepaksharma.live | `http://gitea-server:3000` | App/native auth or public app |
| Gitlab | https://gitlab.deepaksharma.live | `http://gitlab-server:80` | App/native auth or public app |
| Grafana | https://grafana.deepaksharma.live | `http://grafana:3000` | App/native auth or public app |
| Jaeger | https://jaeger.deepaksharma.live | `http://jaeger:16686` | Basic auth |
| Jenkins | https://jenkins.deepaksharma.live | `http://jenkins-master:8080` | App/native auth or public app |
| Jira | https://jira.deepaksharma.live | `http://jira:8080` | App/native auth or public app |
| Loki | https://loki.deepaksharma.live | `http://loki:3100` | Basic auth |
| Mailhog | https://mailhog.deepaksharma.live | `http://taskflow-mailhog:8025` | Basic auth |
| Minio | https://minio.deepaksharma.live | `http://minio:9001` | App/native auth or public app |
| Nexus | https://nexus.deepaksharma.live | `http://ai-nexus:8081` | App/native auth or public app |
| Nexus Docker | https://nexus-docker.deepaksharma.live | `http://ai-nexus:5001` | App/native auth or public app |
| Node Exporter | https://node-exporter.deepaksharma.live | `http://node-exporter:9100` | Basic auth |
| Ollama | https://ollama.deepaksharma.live | `http://ollama:11434` | Basic auth |
| Portal API | https://api.deepaksharma.live | `http://devops-tools-backend:8003` | App/native auth or public app |
| Portal Front Door | https://deepaksharma.live | `http://devops-tools-backend:8003` | App/native auth or public app |
| Portal Front Door (Www) | https://www.deepaksharma.live | `http://devops-tools-backend:8003` | App/native auth or public app |
| Prometheus | https://prometheus.deepaksharma.live | `http://prometheus:9090` | Basic auth |
| Promtail | https://promtail.deepaksharma.live | `http://promtail:9080` | Basic auth |
| Qdrant | https://qdrant.deepaksharma.live | `http://qdrant:6333` | Basic auth |
| Redmine | https://redmine.deepaksharma.live | `http://redmine:3000` | App/native auth or public app |
| Sonarqube | https://sonarqube.deepaksharma.live | `http://ai-sonarqube:9000` | App/native auth or public app |
| Splunk | https://splunk.deepaksharma.live | `http://ai-splunk:8000` | App/native auth or public app |
| Taskflow | https://taskflow.deepaksharma.live | `http://taskflow-api-gateway:8080` | App/native auth or public app |
| Taskflow Auth | https://taskflow-auth.deepaksharma.live | `http://taskflow-auth-service:8080` | App/native auth or public app |
| Taskflow Notify | https://taskflow-notify.deepaksharma.live | `http://taskflow-notification-service:8080` | App/native auth or public app |
| Taskflow Task | https://taskflow-task.deepaksharma.live | `http://taskflow-task-service:8080` | App/native auth or public app |
| Trivy | https://trivy.deepaksharma.live | `http://trivy-server:8080` | Basic auth |

Removed from public routing: `vault.deepaksharma.live` and `/vault/`.
