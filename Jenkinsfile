pipeline {
    agent any

    stages {
        stage('Clone repository') {
            steps {
                git url: 'https://github.com/deepak16686/myfirstrepository.git', branch: 'main'
            }
        }

        stage('Build') {
            steps {
                echo 'Building...'
                // Insert your build steps here
            }
        }

        stage('Test') {
            steps {
                echo 'Testing...'
                // Insert your test steps here
            }
        }
    }
}

