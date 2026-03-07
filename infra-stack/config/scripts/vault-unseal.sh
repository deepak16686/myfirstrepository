#!/bin/sh
# vault-unseal.sh — auto-unseal sidecar. Polls every 10s, unseals Vault on restart.

echo "=== Vault Auto-Unseal Sidecar ==="

while true; do
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
