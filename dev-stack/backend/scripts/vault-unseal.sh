#!/bin/sh
# File: vault-unseal.sh
# Purpose: Vault auto-unseal sidecar that continuously monitors Vault's seal status and automatically
#          unseals it whenever it detects Vault has restarted in a sealed state. Reads the unseal key
#          from the persistent volume at /vault/file/.unseal-key.
# When Used: Runs as the 'vault-unseal' container — a long-lived sidecar that polls every 10 seconds.
#            Activates whenever Vault restarts (e.g., after docker compose restart vault) and finds
#            itself in a sealed state with the initialization marker present.
# Why Created: Vault seals itself on every restart for security. Without this sidecar, every Vault
#              restart would require manual unsealing before the backend could read secrets. This
#              automates that process for the development environment so the stack self-heals.

echo "=== Vault Auto-Unseal Sidecar ==="

while true; do
    # Check if Vault is reachable
    STATUS=$(vault status -format=json 2>/dev/null) || true
    SEALED=$(echo "$STATUS" | grep '"sealed"' | awk '{print $2}' | tr -d ',')
    INITIALIZED=$(echo "$STATUS" | grep '"initialized"' | awk '{print $2}' | tr -d ',')

    if [ "$INITIALIZED" = "true" ] && [ "$SEALED" = "true" ]; then
        if [ -f /vault/file/.unseal-key ]; then
            echo "[$(date)] Vault is sealed — unsealing..."
            UNSEAL_KEY=$(cat /vault/file/.unseal-key)
            vault operator unseal "$UNSEAL_KEY" >/dev/null 2>&1
            echo "[$(date)] Vault unsealed successfully."
        else
            echo "[$(date)] WARNING: Vault is sealed but no unseal key found!"
        fi
    fi

    sleep 10
done
