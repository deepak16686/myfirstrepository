from open_webui.utils.plugin import load_tool_module_by_id

module, _ = load_tool_module_by_id("nexus_docker_images")

print("=== PYTHON ===")
print(module.list_docker_images("python"))
print()
print("=== NODE ===")
print(module.list_docker_images("node"))
print()
print("=== NGINX ===")
print(module.list_docker_images("nginx"))
print()
print("=== REDIS ===")
print(module.list_docker_images("redis"))
print()
print("=== MAVEN ===")
print(module.list_docker_images("maven"))
