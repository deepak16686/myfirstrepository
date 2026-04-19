#!/bin/bash
# Kubernetes Production Environment Deployment Script

echo "🚀 Deploying Production Environment to Kubernetes..."
echo ""

# Apply manifests in order
echo "📦 Creating namespace..."
kubectl apply -f manifests/00-namespace.yaml

echo ""
echo "💾 Deploying databases..."
kubectl apply -f manifests/01-postgres.yaml
kubectl apply -f manifests/02-redis.yaml

echo ""
echo "🗄️  Deploying storage..."
kubectl apply -f manifests/03-minio.yaml

echo ""
echo "🤖 Deploying AI services..."
kubectl apply -f manifests/04-chromadb.yaml
kubectl apply -f manifests/05-ollama.yaml

echo ""
echo "🔧 Deploying DevOps tools..."
kubectl apply -f manifests/06-jenkins.yaml
kubectl apply -f manifests/07-sonarqube.yaml
kubectl apply -f manifests/08-nexus.yaml
kubectl apply -f manifests/10-gitlab.yaml

echo ""
echo "📊 Deploying monitoring..."
kubectl apply -f manifests/09-prometheus-grafana.yaml

echo ""
echo "⏳ Waiting for pods to start..."
kubectl wait --for=condition=ready pod -l app=postgres -n prod-environment --timeout=120s
kubectl wait --for=condition=ready pod -l app=redis -n prod-environment --timeout=120s

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Check status with:"
echo "   kubectl get all -n prod-environment"
echo ""
echo "🌐 Access services:"
echo "   Jenkins:    http://localhost:30808"
echo "   SonarQube:  http://localhost:30900"
echo "   Nexus:      http://localhost:30810"
echo "   GitLab:     http://localhost:30929"
echo "   Grafana:    http://localhost:30300"
echo "   Prometheus: http://localhost:30909"
echo "   MinIO:      http://localhost:30900 (console: 30901)"
echo "   ChromaDB:   http://localhost:30800"
echo "   Ollama:     http://localhost:31434"
echo ""
