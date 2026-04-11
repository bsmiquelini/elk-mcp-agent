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

target "ollama" {
  inherits = ["common"]
  context = "."
  dockerfile = "ollama/Dockerfile"
  args = {
    OLLAMA_PRELOAD_MODEL = "qwen2.5:7b"
  }
  tags = [
    "${REGISTRY}/${IMAGE_NAMESPACE}/ollama:${VERSION}",
    "${REGISTRY}/${IMAGE_NAMESPACE}/ollama:latest",
  ]
}

group "images" {
  targets = ["agent", "mcp_server", "ollama"]
}

group "default" {
  targets = ["agent", "mcp_server", "ollama"]
}

group "release" {
  targets = ["agent", "mcp_server", "ollama"]
}
