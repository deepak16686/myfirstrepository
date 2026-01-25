from open_webui.utils.plugin import load_tool_module_by_id
module, _ = load_tool_module_by_id("nexus_docker_images")
print(module.list_docker_images("ruby"))
