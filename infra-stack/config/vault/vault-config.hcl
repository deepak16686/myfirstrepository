storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

telemetry {
  # Allow Prometheus to scrape /v1/sys/metrics without a Vault token
  unauthenticated_metrics_access = true
  disable_hostname = true
}

disable_mlock = true
api_addr      = "http://0.0.0.0:8200"
ui            = true
