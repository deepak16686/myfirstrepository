from open_webui.utils.plugin import load_tool_module_by_id
import traceback

try:
    module, _ = load_tool_module_by_id("gitlab_pipeline_generator")
    result = module.get_pipeline_template("node", "compile")
    print("SUCCESS:", result)
except Exception as e:
    print("ERROR:", e)
    traceback.print_exc()
