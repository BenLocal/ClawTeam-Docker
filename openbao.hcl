# OpenBao runs only with CLAWTEAM_OPENBAO=1. It listens on loopback; Nginx
# publishes the Web UI at /ui/ and the API at /v1/ on the shared port.
ui            = true
disable_mlock = true
api_addr      = "http://127.0.0.1:8200"
cluster_addr  = "http://127.0.0.1:8201"

storage "raft" {
  path    = "/home/node/.openbao/data"
  node_id = "clawteam"
}

listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = true
}
