#!/bin/bash

# 1. Setup Variables
# We use $HOME to ensure paths work correctly in Git Bash on Windows
GITLAB_HOME="$HOME/gitlab_docker"
NETWORK_NAME="gitlab-net"
GITLAB_HOSTNAME="gitlab-server"

# Ports (Change these if you have conflicts)
HTTP_PORT=8929
SSH_PORT=2224

echo "----------------------------------------------------"
echo "Starting GitLab Deployment Setup..."
echo "Data location: $GITLAB_HOME"
echo "Web Interface: http://localhost:$HTTP_PORT"
echo "----------------------------------------------------"

# 2. Create Docker Network
# This allows the Runner to communicate with the Server internally
if [ ! "$(docker network ls | grep $NETWORK_NAME)" ]; then
  echo "Creating network $NETWORK_NAME..."
  docker network create $NETWORK_NAME
else
  echo "Network $NETWORK_NAME already exists."
fi

# 3. Deploy GitLab Server
# Note: We set shm-size to 256m to prevent crashes under load
echo "Deploying GitLab Server Container..."
docker run --detach \
  --hostname $GITLAB_HOSTNAME \
  --name $GITLAB_HOSTNAME \
  --restart always \
  --publish $HTTP_PORT:80 \
  --publish $SSH_PORT:22 \
  --network $NETWORK_NAME \
  --shm-size 256m \
  --volume "$GITLAB_HOME/config:/etc/gitlab" \
  --volume "$GITLAB_HOME/logs:/var/log/gitlab" \
  --volume "$GITLAB_HOME/data:/var/opt/gitlab" \
  gitlab/gitlab-ce:latest

# 4. Deploy GitLab Runner
# We mount the docker socket so the runner can spawn new docker containers (Docker-in-Docker)
echo "Deploying GitLab Runner Container..."
docker run --detach \
  --name gitlab-runner \
  --restart always \
  --network $NETWORK_NAME \
  --volume "$GITLAB_HOME/runner-config:/etc/gitlab-runner" \
  --volume //var/run/docker.sock://var/run/docker.sock \
  gitlab/gitlab-runner:latest

echo "----------------------------------------------------"
echo "Deployment commands sent!"
echo "GitLab takes about 3-5 minutes to start completely."
echo "View logs with: docker logs -f gitlab-server"
echo "----------------------------------------------------"
