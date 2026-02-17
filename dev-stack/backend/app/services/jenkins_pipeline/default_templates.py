"""
Default Jenkinsfile and Dockerfile templates for various languages.

Provides built-in templates for Java, Python, Node.js, and Go.
Uses Jenkins Declarative Pipeline syntax with Docker Pipeline plugin.
"""
from typing import Dict, Any


def _get_default_jenkinsfile(analysis: Dict[str, Any], agent_label: str = "docker") -> str:
    """Get default Jenkinsfile template based on detected language"""
    language = analysis.get("language", "java")

    templates = {
        "java": _get_java_jenkinsfile_template,
        "kotlin": _get_java_jenkinsfile_template,
        "scala": _get_scala_jenkinsfile_template,
        "python": _get_python_jenkinsfile_template,
        "django": _get_python_jenkinsfile_template,
        "flask": _get_python_jenkinsfile_template,
        "fastapi": _get_python_jenkinsfile_template,
        "javascript": _get_nodejs_jenkinsfile_template,
        "typescript": _get_nodejs_jenkinsfile_template,
        "go": _get_go_jenkinsfile_template,
        "golang": _get_go_jenkinsfile_template,
        "rust": _get_rust_jenkinsfile_template,
        "ruby": _get_ruby_jenkinsfile_template,
        "php": _get_php_jenkinsfile_template,
        "csharp": _get_csharp_jenkinsfile_template,
        "dotnet": _get_csharp_jenkinsfile_template,
    }

    template_fn = templates.get(language, _get_java_jenkinsfile_template)
    return template_fn(agent_label)


def _get_default_dockerfile(analysis: Dict[str, Any]) -> str:
    """Get default Dockerfile based on detected language"""
    language = analysis.get("language", "java")

    templates = {
        "java": _get_java_dockerfile,
        "kotlin": _get_java_dockerfile,
        "scala": _get_java_dockerfile,
        "python": _get_python_dockerfile,
        "django": _get_python_dockerfile,
        "flask": _get_python_dockerfile,
        "fastapi": _get_python_dockerfile,
        "javascript": _get_nodejs_dockerfile,
        "typescript": _get_nodejs_dockerfile,
        "go": _get_go_dockerfile,
        "golang": _get_go_dockerfile,
        "rust": _get_rust_dockerfile,
        "ruby": _get_ruby_dockerfile,
        "php": _get_php_dockerfile,
        "csharp": _get_csharp_dockerfile,
        "dotnet": _get_csharp_dockerfile,
    }

    template_fn = templates.get(language, _get_java_dockerfile)
    return template_fn()


# =============================================================================
# Jenkinsfile Templates
# =============================================================================


def _get_java_jenkinsfile_template(agent_label: str = "docker") -> str:
    """Java/Maven Jenkinsfile template"""
    return f'''pipeline {{
    agent {{ label '{agent_label}' }}

    environment {{
        NEXUS_REGISTRY     = credentials('nexus-registry-url')
        NEXUS_CREDS        = credentials('nexus-credentials')
        IMAGE_NAME         = '${{env.JOB_NAME}}'.split('/').last().toLowerCase()
        IMAGE_TAG          = "1.0.${{BUILD_NUMBER}}"
        RELEASE_TAG        = "1.0.release-${{BUILD_NUMBER}}"
        SONARQUBE_URL      = credentials('sonarqube-url')
        SONAR_TOKEN        = credentials('sonar-token')
        SPLUNK_HEC_URL     = credentials('splunk-hec-url')
        SPLUNK_HEC_TOKEN   = credentials('splunk-hec-token')
        DEVOPS_BACKEND_URL = credentials('devops-backend-url')
    }}

    stages {{
        stage('Compile') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/maven:3.9-eclipse-temurin-17"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'mvn clean package -DskipTests'
                sh 'mkdir -p artifacts && find target -name "*.jar" ! -name "*-sources*" ! -name "*-javadoc*" | head -1 | xargs -I {{}} cp {{}} artifacts/app.jar'
            }}
            post {{
                success {{
                    archiveArtifacts artifacts: 'artifacts/*.jar', fingerprint: true
                    stash includes: 'artifacts/**,target/**,Dockerfile', name: 'build-output'
                }}
            }}
        }}

        stage('Build Image') {{
            steps {{
                unstash 'build-output'
                script {{
                    docker.withRegistry("http://${{NEXUS_REGISTRY}}", 'nexus-credentials') {{
                        def appImage = docker.build("${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}", "--build-arg BASE_REGISTRY=${{NEXUS_REGISTRY}} .")
                        appImage.push()
                        appImage.push('latest')
                    }}
                }}
            }}
        }}

        stage('Test Image') {{
            steps {{
                sh """
                    docker pull ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}
                    docker inspect ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}
                    echo "Image verification successful"
                """
            }}
        }}

        stage('Static Analysis') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/maven:3.9-eclipse-temurin-17"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'mvn spotbugs:check -DskipTests || true'
                sh 'mvn pmd:check -DskipTests || true'
            }}
        }}

        stage('SonarQube') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/sonarsource-sonar-scanner-cli:5"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh """
                    sonar-scanner \\
                      -Dsonar.projectKey=${{IMAGE_NAME}} \\
                      -Dsonar.sources=src/main/java \\
                      -Dsonar.java.binaries=target/classes \\
                      -Dsonar.host.url=${{SONARQUBE_URL}} \\
                      -Dsonar.login=${{SONAR_TOKEN}} || true
                """
            }}
        }}

        stage('Trivy Scan') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/aquasec-trivy:latest"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh """
                    trivy image --severity HIGH,CRITICAL \\
                      ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} || true
                """
            }}
        }}

        stage('Push Release') {{
            steps {{
                sh """
                    docker tag ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} \\
                      ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}
                    docker push ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}
                """
            }}
        }}

        stage('Notify') {{
            steps {{
                sh """
                    curl -sk -X POST "${{SPLUNK_HEC_URL}}/services/collector" \\
                      -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" \\
                      -H "Content-Type: application/json" \\
                      -d '{{"event":{{"message":"Pipeline succeeded","pipeline":"${{BUILD_NUMBER}}","project":"${{IMAGE_NAME}}","status":"SUCCESS","image":"${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}"}},"sourcetype":"jenkins:pipeline","source":"${{IMAGE_NAME}}"}}'
                """
            }}
        }}

        stage('Learn') {{
            steps {{
                sh """
                    echo "=============================================="
                    echo "REINFORCEMENT LEARNING - Recording Success"
                    echo "=============================================="
                    curl -s -X POST "${{DEVOPS_BACKEND_URL}}/api/v1/jenkins-pipeline/learn/record" \\
                      -H "Content-Type: application/json" \\
                      -d '{{"job_name":"${{JOB_NAME}}","build_number":${{BUILD_NUMBER}},"status":"success","image":"${{IMAGE_NAME}}","tag":"${{RELEASE_TAG}}"}}' \\
                      && echo "SUCCESS: Configuration recorded for RL" \\
                      || echo "Note: RL recording skipped (backend may be unavailable)"
                    echo "=============================================="
                """
            }}
        }}
    }}

    post {{
        failure {{
            sh """
                curl -sk -X POST "${{SPLUNK_HEC_URL}}/services/collector" \\
                  -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" \\
                  -H "Content-Type: application/json" \\
                  -d '{{"event":{{"message":"Pipeline failed","pipeline":"${{BUILD_NUMBER}}","project":"${{IMAGE_NAME}}","status":"FAILURE"}},"sourcetype":"jenkins:pipeline","source":"${{IMAGE_NAME}}"}}'
            """
        }}
        always {{
            cleanWs()
        }}
    }}
}}'''


def _get_python_jenkinsfile_template(agent_label: str = "docker") -> str:
    """Python Jenkinsfile template"""
    return f'''pipeline {{
    agent {{ label '{agent_label}' }}

    environment {{
        NEXUS_REGISTRY     = credentials('nexus-registry-url')
        NEXUS_CREDS        = credentials('nexus-credentials')
        IMAGE_NAME         = '${{env.JOB_NAME}}'.split('/').last().toLowerCase()
        IMAGE_TAG          = "1.0.${{BUILD_NUMBER}}"
        RELEASE_TAG        = "1.0.release-${{BUILD_NUMBER}}"
        SONARQUBE_URL      = credentials('sonarqube-url')
        SONAR_TOKEN        = credentials('sonar-token')
        SPLUNK_HEC_URL     = credentials('splunk-hec-url')
        SPLUNK_HEC_TOKEN   = credentials('splunk-hec-token')
        DEVOPS_BACKEND_URL = credentials('devops-backend-url')
    }}

    stages {{
        stage('Compile') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/python:3.11-slim"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'pip install --no-cache-dir -r requirements.txt'
                sh 'python -m py_compile $(find . -name "*.py" -not -path "./.venv/*" | head -20) || true'
            }}
            post {{
                success {{
                    stash includes: '**', name: 'build-output'
                }}
            }}
        }}

        stage('Build Image') {{
            steps {{
                unstash 'build-output'
                script {{
                    docker.withRegistry("http://${{NEXUS_REGISTRY}}", 'nexus-credentials') {{
                        def appImage = docker.build("${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}", "--build-arg BASE_REGISTRY=${{NEXUS_REGISTRY}} .")
                        appImage.push()
                        appImage.push('latest')
                    }}
                }}
            }}
        }}

        stage('Test Image') {{
            steps {{
                sh """
                    docker pull ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}
                    docker inspect ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}
                    echo "Image verification successful"
                """
            }}
        }}

        stage('Static Analysis') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/python:3.11-slim"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'pip install bandit pylint || true'
                sh 'bandit -r . -f json -o bandit-report.json || true'
                sh 'pylint **/*.py --output-format=json > pylint-report.json || true'
            }}
        }}

        stage('SonarQube') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/sonarsource-sonar-scanner-cli:5"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh """
                    sonar-scanner \\
                      -Dsonar.projectKey=${{IMAGE_NAME}} \\
                      -Dsonar.sources=. \\
                      -Dsonar.host.url=${{SONARQUBE_URL}} \\
                      -Dsonar.login=${{SONAR_TOKEN}} || true
                """
            }}
        }}

        stage('Trivy Scan') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/aquasec-trivy:latest"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh """
                    trivy image --severity HIGH,CRITICAL \\
                      ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} || true
                """
            }}
        }}

        stage('Push Release') {{
            steps {{
                sh """
                    docker tag ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} \\
                      ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}
                    docker push ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}
                """
            }}
        }}

        stage('Notify') {{
            steps {{
                sh """
                    curl -sk -X POST "${{SPLUNK_HEC_URL}}/services/collector" \\
                      -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" \\
                      -H "Content-Type: application/json" \\
                      -d '{{"event":{{"message":"Pipeline succeeded","pipeline":"${{BUILD_NUMBER}}","project":"${{IMAGE_NAME}}","status":"SUCCESS","image":"${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}"}},"sourcetype":"jenkins:pipeline","source":"${{IMAGE_NAME}}"}}'
                """
            }}
        }}

        stage('Learn') {{
            steps {{
                sh """
                    echo "=============================================="
                    echo "REINFORCEMENT LEARNING - Recording Success"
                    echo "=============================================="
                    curl -s -X POST "${{DEVOPS_BACKEND_URL}}/api/v1/jenkins-pipeline/learn/record" \\
                      -H "Content-Type: application/json" \\
                      -d '{{"job_name":"${{JOB_NAME}}","build_number":${{BUILD_NUMBER}},"status":"success","image":"${{IMAGE_NAME}}","tag":"${{RELEASE_TAG}}"}}' \\
                      && echo "SUCCESS: Configuration recorded for RL" \\
                      || echo "Note: RL recording skipped (backend may be unavailable)"
                    echo "=============================================="
                """
            }}
        }}
    }}

    post {{
        failure {{
            sh """
                curl -sk -X POST "${{SPLUNK_HEC_URL}}/services/collector" \\
                  -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" \\
                  -H "Content-Type: application/json" \\
                  -d '{{"event":{{"message":"Pipeline failed","pipeline":"${{BUILD_NUMBER}}","project":"${{IMAGE_NAME}}","status":"FAILURE"}},"sourcetype":"jenkins:pipeline","source":"${{IMAGE_NAME}}"}}'
            """
        }}
        always {{
            cleanWs()
        }}
    }}
}}'''


def _get_nodejs_jenkinsfile_template(agent_label: str = "docker") -> str:
    """Node.js Jenkinsfile template"""
    return f'''pipeline {{
    agent {{ label '{agent_label}' }}

    environment {{
        NEXUS_REGISTRY     = credentials('nexus-registry-url')
        NEXUS_CREDS        = credentials('nexus-credentials')
        IMAGE_NAME         = '${{env.JOB_NAME}}'.split('/').last().toLowerCase()
        IMAGE_TAG          = "1.0.${{BUILD_NUMBER}}"
        RELEASE_TAG        = "1.0.release-${{BUILD_NUMBER}}"
        SONARQUBE_URL      = credentials('sonarqube-url')
        SONAR_TOKEN        = credentials('sonar-token')
        SPLUNK_HEC_URL     = credentials('splunk-hec-url')
        SPLUNK_HEC_TOKEN   = credentials('splunk-hec-token')
        DEVOPS_BACKEND_URL = credentials('devops-backend-url')
    }}

    stages {{
        stage('Compile') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/node:20-alpine"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'npm ci'
                sh 'npm run build --if-present'
            }}
            post {{
                success {{
                    stash includes: 'dist/**,build/**,node_modules/**,package.json,Dockerfile', name: 'build-output'
                }}
            }}
        }}

        stage('Build Image') {{
            steps {{
                unstash 'build-output'
                script {{
                    docker.withRegistry("http://${{NEXUS_REGISTRY}}", 'nexus-credentials') {{
                        def appImage = docker.build("${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}", "--build-arg BASE_REGISTRY=${{NEXUS_REGISTRY}} .")
                        appImage.push()
                        appImage.push('latest')
                    }}
                }}
            }}
        }}

        stage('Test Image') {{
            steps {{
                sh """
                    docker pull ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}
                    docker inspect ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}
                    echo "Image verification successful"
                """
            }}
        }}

        stage('Static Analysis') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/node:20-alpine"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'npm audit || true'
                sh 'npx eslint . || true'
            }}
        }}

        stage('SonarQube') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/sonarsource-sonar-scanner-cli:5"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh """
                    sonar-scanner \\
                      -Dsonar.projectKey=${{IMAGE_NAME}} \\
                      -Dsonar.sources=src \\
                      -Dsonar.host.url=${{SONARQUBE_URL}} \\
                      -Dsonar.login=${{SONAR_TOKEN}} || true
                """
            }}
        }}

        stage('Trivy Scan') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/aquasec-trivy:latest"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh """
                    trivy image --severity HIGH,CRITICAL \\
                      ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} || true
                """
            }}
        }}

        stage('Push Release') {{
            steps {{
                sh """
                    docker tag ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} \\
                      ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}
                    docker push ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}
                """
            }}
        }}

        stage('Notify') {{
            steps {{
                sh """
                    curl -sk -X POST "${{SPLUNK_HEC_URL}}/services/collector" \\
                      -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" \\
                      -H "Content-Type: application/json" \\
                      -d '{{"event":{{"message":"Pipeline succeeded","pipeline":"${{BUILD_NUMBER}}","project":"${{IMAGE_NAME}}","status":"SUCCESS","image":"${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}"}},"sourcetype":"jenkins:pipeline","source":"${{IMAGE_NAME}}"}}'
                """
            }}
        }}

        stage('Learn') {{
            steps {{
                sh """
                    echo "=============================================="
                    echo "REINFORCEMENT LEARNING - Recording Success"
                    echo "=============================================="
                    curl -s -X POST "${{DEVOPS_BACKEND_URL}}/api/v1/jenkins-pipeline/learn/record" \\
                      -H "Content-Type: application/json" \\
                      -d '{{"job_name":"${{JOB_NAME}}","build_number":${{BUILD_NUMBER}},"status":"success","image":"${{IMAGE_NAME}}","tag":"${{RELEASE_TAG}}"}}' \\
                      && echo "SUCCESS: Configuration recorded for RL" \\
                      || echo "Note: RL recording skipped (backend may be unavailable)"
                    echo "=============================================="
                """
            }}
        }}
    }}

    post {{
        failure {{
            sh """
                curl -sk -X POST "${{SPLUNK_HEC_URL}}/services/collector" \\
                  -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" \\
                  -H "Content-Type: application/json" \\
                  -d '{{"event":{{"message":"Pipeline failed","pipeline":"${{BUILD_NUMBER}}","project":"${{IMAGE_NAME}}","status":"FAILURE"}},"sourcetype":"jenkins:pipeline","source":"${{IMAGE_NAME}}"}}'
            """
        }}
        always {{
            cleanWs()
        }}
    }}
}}'''


def _get_go_jenkinsfile_template(agent_label: str = "docker") -> str:
    """Go Jenkinsfile template"""
    return f'''pipeline {{
    agent {{ label '{agent_label}' }}

    environment {{
        NEXUS_REGISTRY     = credentials('nexus-registry-url')
        NEXUS_CREDS        = credentials('nexus-credentials')
        IMAGE_NAME         = '${{env.JOB_NAME}}'.split('/').last().toLowerCase()
        IMAGE_TAG          = "1.0.${{BUILD_NUMBER}}"
        RELEASE_TAG        = "1.0.release-${{BUILD_NUMBER}}"
        SONARQUBE_URL      = credentials('sonarqube-url')
        SONAR_TOKEN        = credentials('sonar-token')
        SPLUNK_HEC_URL     = credentials('splunk-hec-url')
        SPLUNK_HEC_TOKEN   = credentials('splunk-hec-token')
        DEVOPS_BACKEND_URL = credentials('devops-backend-url')
    }}

    stages {{
        stage('Compile') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/golang:1.22-alpine"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'CGO_ENABLED=0 GOOS=linux go build -o app .'
            }}
            post {{
                success {{
                    archiveArtifacts artifacts: 'app', fingerprint: true
                    stash includes: 'app,Dockerfile', name: 'build-output'
                }}
            }}
        }}

        stage('Build Image') {{
            steps {{
                unstash 'build-output'
                script {{
                    docker.withRegistry("http://${{NEXUS_REGISTRY}}", 'nexus-credentials') {{
                        def appImage = docker.build("${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}", "--build-arg BASE_REGISTRY=${{NEXUS_REGISTRY}} .")
                        appImage.push()
                        appImage.push('latest')
                    }}
                }}
            }}
        }}

        stage('Test Image') {{
            steps {{
                sh """
                    docker pull ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}
                    docker inspect ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}
                    echo "Image verification successful"
                """
            }}
        }}

        stage('Static Analysis') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/golang:1.22-alpine"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'go vet ./... || true'
            }}
        }}

        stage('SonarQube') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/sonarsource-sonar-scanner-cli:5"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh """
                    sonar-scanner \\
                      -Dsonar.projectKey=${{IMAGE_NAME}} \\
                      -Dsonar.sources=. \\
                      -Dsonar.host.url=${{SONARQUBE_URL}} \\
                      -Dsonar.login=${{SONAR_TOKEN}} || true
                """
            }}
        }}

        stage('Trivy Scan') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/aquasec-trivy:latest"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh """
                    trivy image --severity HIGH,CRITICAL \\
                      ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} || true
                """
            }}
        }}

        stage('Push Release') {{
            steps {{
                sh """
                    docker tag ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} \\
                      ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}
                    docker push ${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}
                """
            }}
        }}

        stage('Notify') {{
            steps {{
                sh """
                    curl -sk -X POST "${{SPLUNK_HEC_URL}}/services/collector" \\
                      -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" \\
                      -H "Content-Type: application/json" \\
                      -d '{{"event":{{"message":"Pipeline succeeded","pipeline":"${{BUILD_NUMBER}}","project":"${{IMAGE_NAME}}","status":"SUCCESS","image":"${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{RELEASE_TAG}}"}},"sourcetype":"jenkins:pipeline","source":"${{IMAGE_NAME}}"}}'
                """
            }}
        }}

        stage('Learn') {{
            steps {{
                sh """
                    echo "=============================================="
                    echo "REINFORCEMENT LEARNING - Recording Success"
                    echo "=============================================="
                    curl -s -X POST "${{DEVOPS_BACKEND_URL}}/api/v1/jenkins-pipeline/learn/record" \\
                      -H "Content-Type: application/json" \\
                      -d '{{"job_name":"${{JOB_NAME}}","build_number":${{BUILD_NUMBER}},"status":"success","image":"${{IMAGE_NAME}}","tag":"${{RELEASE_TAG}}"}}' \\
                      && echo "SUCCESS: Configuration recorded for RL" \\
                      || echo "Note: RL recording skipped (backend may be unavailable)"
                    echo "=============================================="
                """
            }}
        }}
    }}

    post {{
        failure {{
            sh """
                curl -sk -X POST "${{SPLUNK_HEC_URL}}/services/collector" \\
                  -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" \\
                  -H "Content-Type: application/json" \\
                  -d '{{"event":{{"message":"Pipeline failed","pipeline":"${{BUILD_NUMBER}}","project":"${{IMAGE_NAME}}","status":"FAILURE"}},"sourcetype":"jenkins:pipeline","source":"${{IMAGE_NAME}}"}}'
            """
        }}
        always {{
            cleanWs()
        }}
    }}
}}'''


# =============================================================================
# Dockerfile Templates
# =============================================================================


def _get_java_dockerfile() -> str:
    """Java multi-stage Dockerfile"""
    return '''ARG BASE_REGISTRY=localhost:5001

# Build stage
FROM ${BASE_REGISTRY}/apm-repo/demo/maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -B
COPY src ./src
RUN mvn clean package -DskipTests

# Runtime stage
FROM ${BASE_REGISTRY}/apm-repo/demo/eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]'''


def _get_python_dockerfile() -> str:
    """Python Dockerfile"""
    return '''ARG BASE_REGISTRY=localhost:5001

FROM ${BASE_REGISTRY}/apm-repo/demo/python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]'''


def _get_nodejs_dockerfile() -> str:
    """Node.js multi-stage Dockerfile"""
    return '''ARG BASE_REGISTRY=localhost:5001

# Build stage
FROM ${BASE_REGISTRY}/apm-repo/demo/node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build --if-present

# Runtime stage
FROM ${BASE_REGISTRY}/apm-repo/demo/nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]'''


def _get_go_dockerfile() -> str:
    """Go multi-stage Dockerfile"""
    return '''ARG BASE_REGISTRY=localhost:5001

# Build stage
FROM ${BASE_REGISTRY}/apm-repo/demo/golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o app .

# Runtime stage
FROM ${BASE_REGISTRY}/apm-repo/demo/alpine:3.18
WORKDIR /app
COPY --from=build /app/app .
EXPOSE 8080
ENTRYPOINT ["./app"]'''


# =============================================================================
# Helper: common post block for all templates
# =============================================================================

def _notify_stage() -> str:
    """Notify stage - Splunk HEC success notification"""
    return '''        stage('Notify') {
            steps {
                sh """
                    curl -sk -X POST "${SPLUNK_HEC_URL}/services/collector" \\
                      -H "Authorization: Splunk ${SPLUNK_HEC_TOKEN}" \\
                      -H "Content-Type: application/json" \\
                      -d '{"event":{"message":"Pipeline succeeded","pipeline":"${BUILD_NUMBER}","project":"${IMAGE_NAME}","status":"SUCCESS","image":"${NEXUS_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:${RELEASE_TAG}"},"sourcetype":"jenkins:pipeline","source":"${IMAGE_NAME}"}'
                """
            }
        }'''


def _learn_stage() -> str:
    """Learn stage - Record success to backend for RL"""
    return '''        stage('Learn') {
            steps {
                sh """
                    echo "=============================================="
                    echo "REINFORCEMENT LEARNING - Recording Success"
                    echo "=============================================="
                    curl -s -X POST "${DEVOPS_BACKEND_URL}/api/v1/jenkins-pipeline/learn/record" \\
                      -H "Content-Type: application/json" \\
                      -d '{"job_name":"${JOB_NAME}","build_number":${BUILD_NUMBER},"status":"success","image":"${IMAGE_NAME}","tag":"${RELEASE_TAG}"}' \\
                      && echo "SUCCESS: Configuration recorded for RL" \\
                      || echo "Note: RL recording skipped (backend may be unavailable)"
                    echo "=============================================="
                """
            }
        }'''


def _post_block() -> str:
    """Post block - failure notification safety net + workspace cleanup"""
    return '''    post {
        failure {
            sh """
                curl -sk -X POST "${SPLUNK_HEC_URL}/services/collector" \\
                  -H "Authorization: Splunk ${SPLUNK_HEC_TOKEN}" \\
                  -H "Content-Type: application/json" \\
                  -d '{"event":{"message":"Pipeline failed","pipeline":"${BUILD_NUMBER}","project":"${IMAGE_NAME}","status":"FAILURE"},"sourcetype":"jenkins:pipeline","source":"${IMAGE_NAME}"}'
            """
        }
        always {
            cleanWs()
        }
    }'''


def _env_block() -> str:
    """Common environment block for all templates"""
    return '''    environment {
        NEXUS_REGISTRY     = credentials('nexus-registry-url')
        NEXUS_CREDS        = credentials('nexus-credentials')
        IMAGE_NAME         = '${env.JOB_NAME}'.split('/').last().toLowerCase()
        IMAGE_TAG          = "1.0.${BUILD_NUMBER}"
        RELEASE_TAG        = "1.0.release-${BUILD_NUMBER}"
        SONARQUBE_URL      = credentials('sonarqube-url')
        SONAR_TOKEN        = credentials('sonar-token')
        SPLUNK_HEC_URL     = credentials('splunk-hec-url')
        SPLUNK_HEC_TOKEN   = credentials('splunk-hec-token')
        DEVOPS_BACKEND_URL = credentials('devops-backend-url')
    }'''


def _build_image_stage() -> str:
    """Common Build Image stage"""
    return '''        stage('Build Image') {
            steps {
                unstash 'build-output'
                script {
                    docker.withRegistry("http://${NEXUS_REGISTRY}", 'nexus-credentials') {
                        def appImage = docker.build("${NEXUS_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:${IMAGE_TAG}", "--build-arg BASE_REGISTRY=${NEXUS_REGISTRY} .")
                        appImage.push()
                        appImage.push('latest')
                    }
                }
            }
        }'''


def _test_image_stage() -> str:
    """Common Test Image stage"""
    return '''        stage('Test Image') {
            steps {
                sh """
                    docker pull ${NEXUS_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:${IMAGE_TAG}
                    docker inspect ${NEXUS_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:${IMAGE_TAG}
                    echo "Image verification successful"
                """
            }
        }'''


def _sonarqube_stage(sources: str = ".") -> str:
    """Common SonarQube stage"""
    return f'''        stage('SonarQube') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/sonarsource-sonar-scanner-cli:5"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh """
                    sonar-scanner \\\\
                      -Dsonar.projectKey=${{IMAGE_NAME}} \\\\
                      -Dsonar.sources={sources} \\\\
                      -Dsonar.host.url=${{SONARQUBE_URL}} \\\\
                      -Dsonar.login=${{SONAR_TOKEN}} || true
                """
            }}
        }}'''


def _trivy_stage() -> str:
    """Common Trivy Scan stage"""
    return '''        stage('Trivy Scan') {
            agent {
                docker {
                    image "${NEXUS_REGISTRY}/apm-repo/demo/aquasec-trivy:latest"
                    registryUrl "http://${NEXUS_REGISTRY}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }
            }
            steps {
                sh """
                    trivy image --severity HIGH,CRITICAL \\
                      ${NEXUS_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:${IMAGE_TAG} || true
                """
            }
        }'''


def _push_release_stage() -> str:
    """Common Push Release stage"""
    return '''        stage('Push Release') {
            steps {
                sh """
                    docker tag ${NEXUS_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:${IMAGE_TAG} \\
                      ${NEXUS_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:${RELEASE_TAG}
                    docker push ${NEXUS_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:${RELEASE_TAG}
                """
            }
        }'''


# =============================================================================
# Rust Templates
# =============================================================================


def _get_rust_jenkinsfile_template(agent_label: str = "docker") -> str:
    """Rust Jenkinsfile template"""
    return f'''pipeline {{
    agent {{ label '{agent_label}' }}

{_env_block()}

    stages {{
        stage('Compile') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/rust:1.93-slim"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'cargo build --release'
                sh 'mkdir -p build_output && cp target/release/$(basename $(pwd)) build_output/app || cp target/release/*.exe build_output/ || true'
            }}
            post {{
                success {{
                    stash includes: 'build_output/**,Dockerfile', name: 'build-output'
                }}
            }}
        }}

{_build_image_stage()}

{_test_image_stage()}

        stage('Static Analysis') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/rust:1.93-slim"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'rustup component add clippy || true'
                sh 'cargo clippy --all-targets -- -D warnings || true'
            }}
        }}

{_sonarqube_stage("src")}

{_trivy_stage()}

{_push_release_stage()}

{_notify_stage()}

{_learn_stage()}
    }}

{_post_block()}
}}'''


def _get_rust_dockerfile() -> str:
    """Rust multi-stage Dockerfile"""
    return '''ARG BASE_REGISTRY=localhost:5001

# Build stage
FROM ${BASE_REGISTRY}/apm-repo/demo/rust:1.93-slim AS build
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main() {}" > src/main.rs && cargo build --release && rm -rf src
COPY src ./src
RUN cargo build --release

# Runtime stage
FROM ${BASE_REGISTRY}/apm-repo/demo/alpine:3.18
RUN apk add --no-cache libgcc
WORKDIR /app
COPY --from=build /app/target/release/app .
EXPOSE 8080
ENTRYPOINT ["./app"]'''


# =============================================================================
# Ruby Templates
# =============================================================================


def _get_ruby_jenkinsfile_template(agent_label: str = "docker") -> str:
    """Ruby Jenkinsfile template"""
    return f'''pipeline {{
    agent {{ label '{agent_label}' }}

{_env_block()}

    stages {{
        stage('Compile') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/ruby:3.3-alpine"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'bundle install --deployment --without development test'
            }}
            post {{
                success {{
                    stash includes: '**', name: 'build-output'
                }}
            }}
        }}

{_build_image_stage()}

{_test_image_stage()}

        stage('Static Analysis') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/ruby:3.3-alpine"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'gem install brakeman --no-document || true'
                sh 'brakeman --no-pager || true'
            }}
        }}

{_sonarqube_stage(".")}

{_trivy_stage()}

{_push_release_stage()}

{_notify_stage()}

{_learn_stage()}
    }}

{_post_block()}
}}'''


def _get_ruby_dockerfile() -> str:
    """Ruby Dockerfile"""
    return '''ARG BASE_REGISTRY=localhost:5001

FROM ${BASE_REGISTRY}/apm-repo/demo/ruby:3.3-alpine
WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN bundle install --deployment --without development test
COPY . .
EXPOSE 3000
CMD ["bundle", "exec", "rails", "server", "-b", "0.0.0.0"]'''


# =============================================================================
# PHP Templates
# =============================================================================


def _get_php_jenkinsfile_template(agent_label: str = "docker") -> str:
    """PHP Jenkinsfile template"""
    return f'''pipeline {{
    agent {{ label '{agent_label}' }}

{_env_block()}

    stages {{
        stage('Compile') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/php:8.3-fpm-alpine"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'composer install --no-dev --optimize-autoloader'
            }}
            post {{
                success {{
                    stash includes: '**', name: 'build-output'
                }}
            }}
        }}

{_build_image_stage()}

{_test_image_stage()}

        stage('Static Analysis') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/php:8.3-fpm-alpine"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'vendor/bin/phpstan analyse || true'
            }}
        }}

{_sonarqube_stage(".")}

{_trivy_stage()}

{_push_release_stage()}

{_notify_stage()}

{_learn_stage()}
    }}

{_post_block()}
}}'''


def _get_php_dockerfile() -> str:
    """PHP Dockerfile"""
    return '''ARG BASE_REGISTRY=localhost:5001

FROM ${BASE_REGISTRY}/apm-repo/demo/php:8.3-fpm-alpine
WORKDIR /app
COPY composer.json composer.lock ./
RUN composer install --no-dev --optimize-autoloader
COPY . .
EXPOSE 9000
CMD ["php-fpm"]'''


# =============================================================================
# Scala Templates
# =============================================================================


def _get_scala_jenkinsfile_template(agent_label: str = "docker") -> str:
    """Scala Jenkinsfile template (uses Maven image + SBT install)"""
    return f'''pipeline {{
    agent {{ label '{agent_label}' }}

{_env_block()}

    stages {{
        stage('Compile') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/maven:3.9-eclipse-temurin-17"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'curl -fL "https://github.com/sbt/sbt/releases/download/v1.9.8/sbt-1.9.8.tgz" | tar xz -C /tmp'
                sh 'export PATH="/tmp/sbt/bin:$PATH" && sbt clean compile package'
                sh 'mkdir -p artifacts && find target -name "*.jar" | head -1 | xargs -I {{}} cp {{}} artifacts/app.jar || true'
            }}
            post {{
                success {{
                    stash includes: 'artifacts/**,target/**,Dockerfile', name: 'build-output'
                }}
            }}
        }}

{_build_image_stage()}

{_test_image_stage()}

        stage('Static Analysis') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/maven:3.9-eclipse-temurin-17"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'curl -fL "https://github.com/sbt/sbt/releases/download/v1.9.8/sbt-1.9.8.tgz" | tar xz -C /tmp'
                sh 'export PATH="/tmp/sbt/bin:$PATH" && sbt scalafmtCheck || true'
            }}
        }}

{_sonarqube_stage("src/main/scala")}

{_trivy_stage()}

{_push_release_stage()}

{_notify_stage()}

{_learn_stage()}
    }}

{_post_block()}
}}'''


def _get_scala_dockerfile() -> str:
    """Scala multi-stage Dockerfile"""
    return '''ARG BASE_REGISTRY=localhost:5001

# Build stage
FROM ${BASE_REGISTRY}/apm-repo/demo/maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
RUN curl -fL "https://github.com/sbt/sbt/releases/download/v1.9.8/sbt-1.9.8.tgz" | tar xz -C /tmp
ENV PATH="/tmp/sbt/bin:${PATH}"
COPY build.sbt project/ ./
RUN sbt update
COPY src ./src
RUN sbt package

# Runtime stage
FROM ${BASE_REGISTRY}/apm-repo/demo/eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/*/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]'''


# =============================================================================
# C#/.NET Templates
# =============================================================================


def _get_csharp_jenkinsfile_template(agent_label: str = "docker") -> str:
    """C#/.NET Jenkinsfile template"""
    return f'''pipeline {{
    agent {{ label '{agent_label}' }}

{_env_block()}

    stages {{
        stage('Compile') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/dotnet-sdk:8.0"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'dotnet restore'
                sh 'dotnet publish -c Release -o publish'
            }}
            post {{
                success {{
                    stash includes: 'publish/**,Dockerfile', name: 'build-output'
                }}
            }}
        }}

{_build_image_stage()}

{_test_image_stage()}

        stage('Static Analysis') {{
            agent {{
                docker {{
                    image "${{NEXUS_REGISTRY}}/apm-repo/demo/dotnet-sdk:8.0"
                    registryUrl "http://${{NEXUS_REGISTRY}}"
                    registryCredentialsId 'nexus-credentials'
                    reuseNode true
                }}
            }}
            steps {{
                sh 'dotnet build /p:TreatWarningsAsErrors=false || true'
            }}
        }}

{_sonarqube_stage(".")}

{_trivy_stage()}

{_push_release_stage()}

{_notify_stage()}

{_learn_stage()}
    }}

{_post_block()}
}}'''


def _get_csharp_dockerfile() -> str:
    """C#/.NET multi-stage Dockerfile"""
    return '''ARG BASE_REGISTRY=localhost:5001

# Build stage
FROM ${BASE_REGISTRY}/apm-repo/demo/dotnet-sdk:8.0 AS build
WORKDIR /app
COPY *.csproj ./
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o publish

# Runtime stage
FROM ${BASE_REGISTRY}/apm-repo/demo/dotnet-aspnet:8.0-alpine
WORKDIR /app
COPY --from=build /app/publish .
EXPOSE 8080
ENTRYPOINT ["dotnet", "app.dll"]'''
