# Kubernetes NodePort Map — All DevOps Tools
# Docker Desktop Single-Node Cluster
# Access: http://localhost:<NodePort>

## Core Platform
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30003 | DevOps Tools Backend   | devops-tools   | FastAPI Backend API        |
| 30434 | Ollama                 | ollama         | AI Model Server            |
| 30805 | ChromaDB               | chromadb       | Vector Database            |
| 30801 | ChromaDB Admin         | chromadb       | ChromaDB Web Admin         |
| 30379 | Redis                  | redis          | Cache / Session Store      |
| 30400 | PostgreSQL             | default        | Primary Database           |
| 30831 | Vault                  | vault          | Secrets Management         |
| 30830 | Vault UI               | vault          | Vault Web Interface        |

## Source Control
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30200 | GitLab                 | gitlab         | GitLab CE                  |
| 30201 | Gitea HTTP             | gitea          | Gitea Git Server           |
| 30202 | Gitea SSH              | gitea          | Gitea SSH                  |
| 30203 | Gogs                   | gogs           | Lightweight Git            |
| 30204 | Forgejo                | forgejo        | Gitea Fork                 |
| 30205 | OneDev                 | onedev         | Git + CI/CD                |

## CI/CD
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30800 | Jenkins                | jenkins        | Jenkins LTS                |
| 30210 | Drone CI               | drone          | Lightweight CI             |
| 30211 | Woodpecker CI          | woodpecker     | Drone Fork                 |
| 30212 | Tekton Dashboard       | tekton         | Cloud-Native CI/CD         |
| 30213 | Argo Workflows         | argo-workflows | Workflow Engine            |
| 30237 | Atlantis               | atlantis       | Terraform Automation       |

## GitOps & Orchestration
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 32169 | ArgoCD                 | argocd         | GitOps Controller          |
| 30231 | Rancher                | rancher        | K8s Management             |
| 30232 | Kubernetes Dashboard   | k8s-dashboard  | Cluster Dashboard          |
| 30777 | Portainer              | portainer      | Container Management       |

## Artifact Management
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30810 | Nexus                  | nexus          | Artifact Repository        |
| 30220 | Artifactory            | artifactory    | JFrog Artifactory          |
| 30870 | Harbor                 | harbor         | Container Registry         |
| 30221 | Docker Registry        | docker-registry| Private Docker Registry    |
| 30222 | Verdaccio              | verdaccio      | npm Registry               |
| 30224 | Zot                    | zot            | OCI Registry               |

## Monitoring
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30090 | Prometheus             | default        | Metrics                    |
| 30909 | Prometheus (Stack)     | monitoring     | Kube-Prometheus Stack      |
| 30300 | Grafana                | default        | Dashboards                 |
| 30301 | Grafana (Stack)        | monitoring     | Kube-Prometheus Grafana    |
| 30093 | Alertmanager           | monitoring     | Alert Routing              |
| 30240 | Thanos                 | thanos         | Long-term Metrics          |
| 30241 | Mimir                  | mimir          | Metrics Backend            |
| 30242 | VictoriaMetrics        | victoriametrics| Fast Metrics               |
| 30243 | Zabbix                 | zabbix         | Network Monitoring         |
| 30244 | Nagios                 | nagios         | Infrastructure Monitoring  |
| 30245 | Icinga                 | icinga         | Monitoring                 |
| 30246 | Uptime Kuma            | uptime-kuma    | Uptime Monitoring          |
| 30082 | cAdvisor               | cadvisor       | Container Metrics          |

## Logging
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30920 | Elasticsearch          | logging        | Log Storage                |
| 30560 | Kibana                 | logging        | Log Visualization          |
| 30311 | Loki                   | loki           | Log Aggregation            |
| 30253 | Graylog                | graylog        | Log Management             |
| 30250 | Logstash               | logstash       | Log Processing             |
| 30255 | OpenSearch Dashboards  | opensearch     | OpenSearch UI              |
| 30850 | Splunk Web             | splunk         | Splunk Enterprise          |
| 30851 | Splunk HEC             | splunk         | HTTP Event Collector       |

## Tracing & APM
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30686 | Jaeger UI              | jaeger         | Distributed Tracing        |
| 30268 | Jaeger Collector       | jaeger         | Trace Collection           |
| 30260 | Zipkin                 | zipkin         | Distributed Tracing        |
| 30261 | SigNoz                 | signoz         | Observability Platform     |
| 30263 | Tempo                  | tempo          | Trace Backend              |
| 30265 | Elastic APM            | elastic-apm    | APM Server                 |
| 30264 | Sentry                 | sentry         | Error Tracking             |

## Security & Scanning
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30820 | SonarQube              | sonarqube      | Code Quality               |
| 30271 | Anchore                | anchore        | Container Scanning         |
| 30272 | DefectDojo             | defectdojo     | Vulnerability Management   |
| 30273 | OWASP ZAP              | owasp-zap      | Security Scanner           |

## Identity & Access
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30290 | Keycloak               | keycloak       | Identity Management        |
| 30280 | Conjur                 | conjur         | Secrets Management         |
| 30281 | Infisical              | infisical      | Secrets Management         |

## Service Mesh & API Gateway
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30310 | APISIX                 | apisix         | API Gateway                |
| 30296 | Nginx Ingress          | nginx-ingress  | Ingress Controller         |
| 30298 | Kong Proxy             | kong           | API Gateway                |
| 30312 | HAProxy                | haproxy        | Load Balancer              |
| 30316 | Linkerd Dashboard      | linkerd        | Service Mesh               |
| 30314 | Envoy                  | default        | Service Proxy              |

## Databases & Messaging
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30400 | PostgreSQL             | default        | Relational DB              |
| 30401 | MySQL                  | mysql          | Relational DB              |
| 30404 | RabbitMQ               | rabbitmq       | Message Broker             |
| 30408 | NATS                   | nats           | Messaging                  |
| 30409 | etcd                   | etcd-cluster   | Key-Value Store            |
| 30840 | MinIO Console          | minio          | Object Storage UI          |
| 30841 | MinIO API              | minio          | Object Storage             |

## Project Management
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30180 | Jira                   | jira           | Issue Tracking             |
| 30091 | Redmine                | redmine        | Project Management         |

## Documentation & Collaboration
| Port  | Service                | Namespace      | Notes                     |
|-------|------------------------|----------------|---------------------------|
| 30500 | Wiki.js                | wikijs         | Wiki                       |
| 30501 | BookStack              | bookstack      | Documentation              |
| 30502 | Outline                | outline        | Knowledge Base             |
| 30504 | Rocket.Chat            | rocketchat     | Team Chat                  |
| 30505 | Backstage              | backstage      | Developer Portal           |
| 30323 | Mattermost             | mattermost     | Team Messaging             |
