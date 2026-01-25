from open_webui.utils.plugin import load_tool_module_by_id
module, _ = load_tool_module_by_id("gitlab_pipeline_generator")
print(module.get_pipeline_template("ruby", "all")[:1500])
