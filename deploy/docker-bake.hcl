variable "REGISTRY" {
  default = "local"
}

variable "IMAGE_NAMESPACE" {
  default = "elk-mcp-agent"
}

variable "VERSION" {
  default = "dev"
}

target "common" {
  platforms = ["linux/amd64"]
}

target "agent" {
  inherits = ["common"]
  context = "."
  dockerfile = "agent/Dockerfile"
  tags = [
    "${REGISTRY}/${IMAGE_NAMESPACE}/agent:${VERSION}",
    "${REGISTRY}/${IMAGE_NAMESPACE}/agent:latest",
  ]
}

target "mcp_server" {
  inherits = ["common"]
  context = "."
  dockerfile = "mcp_server/Dockerfile"
  tags = [
    "${REGISTRY}/${IMAGE_NAMESPACE}/mcp-server:${VERSION}",
    "${REGISTRY}/${IMAGE_NAMESPACE}/mcp-server:latest",
  ]
}

group "images" {
  targets = ["agent", "mcp_server"]
}

group "default" {
  targets = ["agent", "mcp_server"]
}

group "release" {
  targets = ["agent", "mcp_server"]
}
