# deepaksharma.live public routing

Generated from `nginx-proxy/portal.conf` on 2026-05-04.

Tailscale Funnel public URL: `https://deepak-desktop.tailac51e7.ts.net`

Tailscale Funnel currently supports public service names under the tailnet `*.ts.net` domain, so GoDaddy custom-domain mapping is implemented as GoDaddy HTTPS forwarding to the `.ts.net` path router, not as direct CNAME-to-Funnel TLS.

GoDaddy setup: create each entry below under DNS > Forwarding > Add Forwarding. Use `Permanent 301`, `Forward only`, and the destination URL shown. GoDaddy will create/update the forwarding DNS records.

| Source | GoDaddy name | Destination | Current DNS | Notes |
|---|---:|---|---:|---|
| api.deepaksharma.live | api | https://deepak-desktop.tailac51e7.ts.net/ | False |  |
| brandmatik-analytics.deepaksharma.live | brandmatik-analytics | https://deepak-desktop.tailac51e7.ts.net/brandmatik-analytics/ | False |  |
| brandmatik-business.deepaksharma.live | brandmatik-business | https://deepak-desktop.tailac51e7.ts.net/brandmatik-business/ | False |  |
| brandmatik-content.deepaksharma.live | brandmatik-content | https://deepak-desktop.tailac51e7.ts.net/brandmatik-content/ | False |  |
| brandmatik-feedback.deepaksharma.live | brandmatik-feedback | https://deepak-desktop.tailac51e7.ts.net/brandmatik-feedback/ | False |  |
| brandmatik-mock.deepaksharma.live | brandmatik-mock | https://deepak-desktop.tailac51e7.ts.net/brandmatik-mock/ | False |  |
| brandmatik-notification.deepaksharma.live | brandmatik-notification | https://deepak-desktop.tailac51e7.ts.net/brandmatik-notification/ | False |  |
| brandmatik-posting.deepaksharma.live | brandmatik-posting | https://deepak-desktop.tailac51e7.ts.net/brandmatik-posting/ | False |  |
| brandmatik-qdrant.deepaksharma.live | brandmatik-qdrant | https://deepak-desktop.tailac51e7.ts.net/brandmatik-qdrant/ | False | nginx basic auth required on path route |
| brandmatik-scoring.deepaksharma.live | brandmatik-scoring | https://deepak-desktop.tailac51e7.ts.net/brandmatik-scoring/ | False |  |
| brandmatik-trend.deepaksharma.live | brandmatik-trend | https://deepak-desktop.tailac51e7.ts.net/brandmatik-trend/ | False |  |
| brandmatik.deepaksharma.live | brandmatik | https://deepak-desktop.tailac51e7.ts.net/brandmatik/ | True |  |
| cadvisor.deepaksharma.live | cadvisor | https://deepak-desktop.tailac51e7.ts.net/cadvisor/ | False | nginx basic auth required on path route |
| chaos-ai.deepaksharma.live | chaos-ai | https://deepak-desktop.tailac51e7.ts.net/chaos-ai/ | False |  |
| chaos-auth.deepaksharma.live | chaos-auth | https://deepak-desktop.tailac51e7.ts.net/chaos-auth/ | False |  |
| chaos-credentials.deepaksharma.live | chaos-credentials | https://deepak-desktop.tailac51e7.ts.net/chaos-credentials/ | False | nginx basic auth required on path route |
| chaos-experiment.deepaksharma.live | chaos-experiment | https://deepak-desktop.tailac51e7.ts.net/chaos-experiment/ | False |  |
| chaos-grafana.deepaksharma.live | chaos-grafana | https://deepak-desktop.tailac51e7.ts.net/chaos-grafana/ | False |  |
| chaos-minio.deepaksharma.live | chaos-minio | https://deepak-desktop.tailac51e7.ts.net/chaos-minio/ | False |  |
| chaos-nats.deepaksharma.live | chaos-nats | https://deepak-desktop.tailac51e7.ts.net/chaos-nats/ | False | nginx basic auth required on path route |
| chaos-notify.deepaksharma.live | chaos-notify | https://deepak-desktop.tailac51e7.ts.net/chaos-notify/ | False |  |
| chaos-platform.deepaksharma.live | chaos-platform | https://deepak-desktop.tailac51e7.ts.net/chaos-platform/ | False |  |
| chaos-portal.deepaksharma.live | chaos-portal | https://deepak-desktop.tailac51e7.ts.net/chaos-portal/ | False |  |
| chaos-prometheus.deepaksharma.live | chaos-prometheus | https://deepak-desktop.tailac51e7.ts.net/chaos-prometheus/ | False | nginx basic auth required on path route |
| chaos-report.deepaksharma.live | chaos-report | https://deepak-desktop.tailac51e7.ts.net/chaos-report/ | False |  |
| chaos-target1.deepaksharma.live | chaos-target1 | https://deepak-desktop.tailac51e7.ts.net/chaos-target1/ | False |  |
| chaos-target2.deepaksharma.live | chaos-target2 | https://deepak-desktop.tailac51e7.ts.net/chaos-target2/ | False |  |
| chaos-target3.deepaksharma.live | chaos-target3 | https://deepak-desktop.tailac51e7.ts.net/chaos-target3/ | False |  |
| chaos-telemetry.deepaksharma.live | chaos-telemetry | https://deepak-desktop.tailac51e7.ts.net/chaos-telemetry/ | False |  |
| chatbot.deepaksharma.live | chatbot | https://deepak-desktop.tailac51e7.ts.net/chatbot/ | False |  |
| chromadb-admin.deepaksharma.live | chromadb-admin | https://deepak-desktop.tailac51e7.ts.net/chromadb-admin/ | False | nginx basic auth required on path route |
| chromadb.deepaksharma.live | chromadb | https://deepak-desktop.tailac51e7.ts.net/chromadb/ | False | nginx basic auth required on path route |
| dcgm-exporter.deepaksharma.live | dcgm-exporter | https://deepak-desktop.tailac51e7.ts.net/dcgm-exporter/ | False | nginx basic auth required on path route |
| deepaksharma.live | @ | https://deepak-desktop.tailac51e7.ts.net/ | True |  |
| gitea.deepaksharma.live | gitea | https://deepak-desktop.tailac51e7.ts.net/gitea/ | False |  |
| gitlab.deepaksharma.live | gitlab | https://deepak-desktop.tailac51e7.ts.net/gitlab/ | True |  |
| grafana.deepaksharma.live | grafana | https://deepak-desktop.tailac51e7.ts.net/grafana/ | True |  |
| jaeger.deepaksharma.live | jaeger | https://deepak-desktop.tailac51e7.ts.net/jaeger/ | True | nginx basic auth required on path route |
| jenkins.deepaksharma.live | jenkins | https://deepak-desktop.tailac51e7.ts.net/jenkins/ | True |  |
| jira.deepaksharma.live | jira | https://deepak-desktop.tailac51e7.ts.net/jira/ | False |  |
| loki.deepaksharma.live | loki | https://deepak-desktop.tailac51e7.ts.net/loki/ | False | nginx basic auth required on path route |
| mailhog.deepaksharma.live | mailhog | https://deepak-desktop.tailac51e7.ts.net/mailhog/ | False | nginx basic auth required on path route |
| minio.deepaksharma.live | minio | https://deepak-desktop.tailac51e7.ts.net/minio/ | True |  |
| nexus-docker.deepaksharma.live | nexus-docker | https://deepak-desktop.tailac51e7.ts.net/nexus-docker/ | False |  |
| nexus.deepaksharma.live | nexus | https://deepak-desktop.tailac51e7.ts.net/nexus/ | True |  |
| node-exporter.deepaksharma.live | node-exporter | https://deepak-desktop.tailac51e7.ts.net/node-exporter/ | False | nginx basic auth required on path route |
| ollama.deepaksharma.live | ollama | https://deepak-desktop.tailac51e7.ts.net/ollama/ | False | nginx basic auth required on path route |
| prometheus.deepaksharma.live | prometheus | https://deepak-desktop.tailac51e7.ts.net/prometheus/ | True | nginx basic auth required on path route |
| qdrant.deepaksharma.live | qdrant | https://deepak-desktop.tailac51e7.ts.net/qdrant/ | False | nginx basic auth required on path route |
| redmine.deepaksharma.live | redmine | https://deepak-desktop.tailac51e7.ts.net/redmine/ | False |  |
| sonarqube.deepaksharma.live | sonarqube | https://deepak-desktop.tailac51e7.ts.net/sonarqube/ | True |  |
| splunk.deepaksharma.live | splunk | https://deepak-desktop.tailac51e7.ts.net/splunk/ | True |  |
| taskflow-auth.deepaksharma.live | taskflow-auth | https://deepak-desktop.tailac51e7.ts.net/taskflow-auth/ | False |  |
| taskflow-notify.deepaksharma.live | taskflow-notify | https://deepak-desktop.tailac51e7.ts.net/taskflow-notify/ | False |  |
| taskflow-task.deepaksharma.live | taskflow-task | https://deepak-desktop.tailac51e7.ts.net/taskflow-task/ | False |  |
| taskflow.deepaksharma.live | taskflow | https://deepak-desktop.tailac51e7.ts.net/taskflow/ | False |  |
| trivy.deepaksharma.live | trivy | https://deepak-desktop.tailac51e7.ts.net/trivy/ | False | nginx basic auth required on path route |
| vault.deepaksharma.live | vault | https://deepak-desktop.tailac51e7.ts.net/vault/ | True |  |
| www.deepaksharma.live | www | https://deepak-desktop.tailac51e7.ts.net/ | True |  |

Non-HTTP backing services such as PostgreSQL and Redis are intentionally not listed for public Funnel exposure.
