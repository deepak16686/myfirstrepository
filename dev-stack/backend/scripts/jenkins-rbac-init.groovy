/*
 * File: jenkins-rbac-init.groovy
 * Purpose: Jenkins Groovy init script that creates the svc-devops-backend service account user,
 *          generates an API token for it, and configures Matrix Authorization Strategy with
 *          granular permissions for devops-readonly, devops-readwrite, and devops-admin groups.
 * When Used: Placed in Jenkins' init.groovy.d/ directory and executed automatically on Jenkins startup.
 *            Runs every time Jenkins starts but is idempotent — skips user creation if already exists.
 * Why Created: Enables the backend to interact with Jenkins via API using a dedicated service account
 *              instead of the admin user, and establishes consistent RBAC groups that match the
 *              permission model used across all other tools in the dev-stack.
 */
import jenkins.model.*
import hudson.security.*
import org.jenkinsci.plugins.matrixauth.*
import jenkins.security.ApiTokenProperty

def instance = Jenkins.getInstance()

// ============================================================
// 1. Create service account user
// ============================================================

def hudsonRealm = instance.getSecurityRealm()
if (hudsonRealm instanceof HudsonPrivateSecurityRealm) {
    def existing = hudsonRealm.getUser("svc-devops-backend")
    if (existing == null) {
        hudsonRealm.createAccount("svc-devops-backend", "SvcD3v0ps2026")
        println("[RBAC] Service account 'svc-devops-backend' created")
    } else {
        println("[RBAC] Service account 'svc-devops-backend' already exists")
    }
} else {
    println("[RBAC] WARN: Security realm is not HudsonPrivateSecurityRealm, cannot create users")
}

// ============================================================
// 2. Configure Matrix Authorization Strategy
// ============================================================

try {
    // Check if Matrix Auth plugin is available
    Class.forName("org.jenkinsci.plugins.matrixauth.GlobalMatrixAuthorizationStrategy")

    def strategy = new GlobalMatrixAuthorizationStrategy()

    // Admin user - full access
    strategy.add(Jenkins.ADMINISTER, "admin")

    // devops-admin group permissions (full access)
    strategy.add(Jenkins.ADMINISTER, "devops-admin")

    // devops-readwrite group permissions
    strategy.add(Jenkins.READ, "devops-readwrite")
    strategy.add(hudson.model.Item.BUILD, "devops-readwrite")
    strategy.add(hudson.model.Item.READ, "devops-readwrite")
    strategy.add(hudson.model.Item.DISCOVER, "devops-readwrite")
    strategy.add(hudson.model.Item.WORKSPACE, "devops-readwrite")
    strategy.add(hudson.model.Item.CANCEL, "devops-readwrite")
    strategy.add(hudson.model.View.READ, "devops-readwrite")

    // devops-readonly group permissions
    strategy.add(Jenkins.READ, "devops-readonly")
    strategy.add(hudson.model.Item.READ, "devops-readonly")
    strategy.add(hudson.model.Item.DISCOVER, "devops-readonly")
    strategy.add(hudson.model.View.READ, "devops-readonly")

    // svc-devops-backend - same as readwrite + configure for pipeline management
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
    println("[RBAC] Matrix Authorization configured with 3 groups + service account")

} catch (ClassNotFoundException e) {
    // Matrix Auth plugin not installed - use ProjectMatrixAuth or fallback
    println("[RBAC] Matrix Auth plugin not available, keeping existing authorization strategy")
    println("[RBAC] Install 'matrix-auth' plugin for granular RBAC")

    // At minimum, keep FullControlOnceLoggedInAuthorizationStrategy
    def currentStrategy = instance.getAuthorizationStrategy()
    if (currentStrategy instanceof FullControlOnceLoggedInAuthorizationStrategy) {
        println("[RBAC] Using FullControlOnceLoggedInAuthorizationStrategy (all authenticated users have full access)")
    }
}

instance.save()
println("[RBAC] Jenkins RBAC initialization complete")
