# File: vault-config.hcl
# Purpose: HashiCorp Vault server configuration. Configures persistent file-based storage at /vault/file,
#          a TCP listener on port 8200 with TLS disabled (internal Docker network only), and enables
#          the Vault web UI for browser-based secret management.
# When Used: Mounted into the Vault container at /vault/config/vault.hcl and read on Vault startup.
#            Vault uses this to determine storage backend, listener address, and UI availability.
# Why Created: Defines Vault's operating mode for the dev-stack — file storage (not Consul/Raft) for
#              simplicity, no TLS since traffic stays within the Docker network, and UI enabled for
#              developer convenience at http://localhost:8200/ui.

storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

disable_mlock = true
api_addr      = "http://0.0.0.0:8200"
ui            = true
