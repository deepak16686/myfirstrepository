/*
 * jenkins-rbac-init.groovy — creates svc-devops-backend user + Matrix Authorization RBAC.
 * Placed in init.groovy.d/ — runs on every Jenkins startup (idempotent).
 */
import jenkins.model.*
import hudson.security.*
import org.jenkinsci.plugins.matrixauth.*
import jenkins.security.ApiTokenProperty

def instance = Jenkins.getInstance()

def hudsonRealm = instance.getSecurityRealm()
if (hudsonRealm instanceof HudsonPrivateSecurityRealm) {
    def existing = hudsonRealm.getUser("svc-devops-backend")
    if (existing == null) {
        hudsonRealm.createAccount("svc-devops-backend", "SvcD3v0ps2026")
        println("[RBAC] Service account 'svc-devops-backend' created")
    } else {
        println("[RBAC] Service account 'svc-devops-backend' already exists")
    }
}

try {
    Class.forName("org.jenkinsci.plugins.matrixauth.GlobalMatrixAuthorizationStrategy")
    def strategy = new GlobalMatrixAuthorizationStrategy()

    strategy.add(Jenkins.ADMINISTER, "admin")
    strategy.add(Jenkins.ADMINISTER, "devops-admin")

    strategy.add(Jenkins.READ, "devops-readwrite")
    strategy.add(hudson.model.Item.BUILD, "devops-readwrite")
    strategy.add(hudson.model.Item.READ, "devops-readwrite")
    strategy.add(hudson.model.Item.DISCOVER, "devops-readwrite")
    strategy.add(hudson.model.Item.WORKSPACE, "devops-readwrite")
    strategy.add(hudson.model.Item.CANCEL, "devops-readwrite")
    strategy.add(hudson.model.View.READ, "devops-readwrite")

    strategy.add(Jenkins.READ, "devops-readonly")
    strategy.add(hudson.model.Item.READ, "devops-readonly")
    strategy.add(hudson.model.Item.DISCOVER, "devops-readonly")
    strategy.add(hudson.model.View.READ, "devops-readonly")

    strategy.add(Jenkins.READ, "svc-devops-backend")
    strategy.add(hudson.model.Item.BUILD, "svc-devops-backend")
    strategy.add(hudson.model.Item.READ, "svc-devops-backend")
    strategy.add(hudson.model.Item.DISCOVER, "svc-devops-backend")
    strategy.add(hudson.model.Item.WORKSPACE, "svc-devops-backend")
    strategy.add(hudson.model.Item.CANCEL, "svc-devops-backend")
    strategy.add(hudson.model.Item.CONFIGURE, "svc-devops-backend")
    strategy.add(hudson.model.Item.CREATE, "svc-devops-backend")
    strategy.add(hudson.model.View.READ, "svc-devops-backend")

    instance.setAuthorizationStrategy(strategy)
    println("[RBAC] Matrix Authorization configured")
} catch (ClassNotFoundException e) {
    println("[RBAC] Matrix Auth plugin not available — install 'matrix-auth' plugin for granular RBAC")
}

instance.save()
println("[RBAC] Jenkins RBAC initialization complete")
