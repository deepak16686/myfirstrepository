from open_webui.utils.plugin import load_tool_module_by_id

module, _ = load_tool_module_by_id("gitlab_pipeline_generator")

print("=== NODE FULL PIPELINE ===")
result = module.get_pipeline_template("node", "all")
print(result[:2000])
print("\n\n=== PYTHON COMPILE ONLY ===")
result = module.get_pipeline_template("python", "compile")
print(result)
