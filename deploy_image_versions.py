from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.utils.plugin import load_tool_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from open_webui.config import CACHE_DIR

USER_ID = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"
TOOL_ID = "nexus_image_versions"

with open("/tmp/image_versions_content.py", "r") as f:
    raw_content = f.read()

content = replace_imports(raw_content)

meta = ToolMeta(description="Search Docker images in Nexus registry and show last 5 latest versions")
form = ToolForm(id=TOOL_ID, name="Nexus Image Versions", content=content, meta=meta, access_control=None)

existing = Tools.get_tool_by_id(TOOL_ID)
if existing:
    Tools.delete_tool_by_id(TOOL_ID)

module, frontmatter = load_tool_module_by_id(TOOL_ID, content=form.content)
form.meta.manifest = frontmatter
specs = get_tool_specs(module)
tool = Tools.insert_new_tool(USER_ID, form, specs)
(CACHE_DIR / "tools" / TOOL_ID).mkdir(parents=True, exist_ok=True)
print({"created": bool(tool), "id": TOOL_ID, "specs": specs})
