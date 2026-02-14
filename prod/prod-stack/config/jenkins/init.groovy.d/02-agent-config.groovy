import jenkins.model.*
import hudson.slaves.*
import hudson.model.*
import jenkins.slaves.*
import hudson.plugins.sshslaves.*

def instance = Jenkins.getInstance()

// Master: 0 executors (all builds run on agents)
instance.setNumExecutors(0)

// Enable JNLP agent port
instance.setSlaveAgentPort(50000)

// Create 3 JNLP inbound agent nodes with 'docker' label
["prod-agent-1", "prod-agent-2", "prod-agent-3"].each { agentName ->
    if (instance.getNode(agentName) != null) {
        println("[INIT] Agent '${agentName}' already exists — skipping")
        return
    }

    def launcher = new JNLPLauncher(true)  // WebSocket mode
    def retentionStrategy = new RetentionStrategy.Always()

    def node = new DumbSlave(
        agentName,                          // name
        "/home/jenkins/agent",              // remoteFS
        launcher                            // launcher
    )
    node.setNumExecutors(2)
    node.setLabelString("docker")
    node.setMode(Node.Mode.NORMAL)
    node.setRetentionStrategy(retentionStrategy)

    instance.addNode(node)
    println("[INIT] Created agent node: ${agentName} (label=docker, executors=2)")
}

instance.save()

// Print agent secrets so setup script can retrieve them
["prod-agent-1", "prod-agent-2", "prod-agent-3"].each { agentName ->
    def computer = instance.getComputer(agentName)
    if (computer != null) {
        println("[AGENT-SECRET] ${agentName}=${computer.getJnlpMac()}")
    }
}

println("[INIT] Agent configuration complete — 3 nodes created, JNLP port: 50000")
