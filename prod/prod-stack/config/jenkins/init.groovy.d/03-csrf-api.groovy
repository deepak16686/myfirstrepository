import jenkins.model.*
import hudson.security.csrf.DefaultCrumbIssuer

def instance = Jenkins.getInstance()

// Enable crumb issuer but exclude API calls for easier automation
def crumbIssuer = new DefaultCrumbIssuer(true)
instance.setCrumbIssuer(crumbIssuer)

// Mark setup as complete
instance.setInstallState(jenkins.install.InstallState.INITIAL_SETUP_COMPLETED)

instance.save()
println("[INIT] CSRF protection enabled, setup wizard marked complete")
