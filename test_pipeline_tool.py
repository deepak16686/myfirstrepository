from open_webui.utils.plugin import load_tool_module_by_id
import json

module, _ = load_tool_module_by_id("gitlab_pipeline_generator")

print("=== JAVA FULL PIPELINE ===")
result = module.get_pipeline_template("java", "all")
print(json.dumps(result, indent=2)[:2000])

print("\n=== PYTHON BUILD ONLY ===")
result = module.get_pipeline_template("python", "compile,build")
print(json.dumps(result, indent=2)[:1000])

print("\n=== NODE SINGLE STAGE ===")
result = module.get_pipeline_template("node", "compile")
print(json.dumps(result, indent=2)[:800])
