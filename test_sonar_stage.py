from open_webui.utils.plugin import load_tool_module_by_id

module, _ = load_tool_module_by_id("gitlab_pipeline_generator")

print("=== SONARQUBE STAGE ===")
result = module.get_pipeline_template("sonarqube", "all")
print(result)
