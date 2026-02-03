"""Test chat completion flow to find the NoneType error."""
import asyncio
import json

async def test_chat():
    from open_webui.models.models import Models
    from open_webui.models.tools import Tools as ToolsModel
    from open_webui.utils.plugin import load_tool_module_by_id
    from open_webui.utils.tools import get_tools

    print("Testing Chat Completion Flow")
    print("="*50)

    # Get the model
    model = Models.get_model_by_id('pipeline-assistant')
    print(f"Model: {model.name}")
    print(f"Base Model: {model.base_model_id}")
    print(f"Tool IDs: {model.meta.toolIds if model.meta else None}")

    # Try to load tools the way chat completion does
    print("\nLoading tools...")
    tool_ids = model.meta.toolIds if model.meta else []

    for tool_id in tool_ids:
        print(f"\n  Loading {tool_id}...")
        try:
            tool = ToolsModel.get_tool_by_id(tool_id)
            if tool is None:
                print(f"    ERROR: Tool not found!")
                continue

            print(f"    Tool found: {tool.name}")
            print(f"    Specs: {tool.specs}")

            # Load the module
            module, frontmatter = load_tool_module_by_id(tool.id, content=tool.content)
            print(f"    Module loaded: {type(module)}")

            # Check if valves exist
            if hasattr(module, 'Valves'):
                print(f"    Has Valves class")
            if hasattr(module, 'valves'):
                print(f"    Has valves instance: {module.valves}")

            # Test calling the tool function
            methods = [m for m in dir(module) if not m.startswith('_') and callable(getattr(module, m, None))]
            print(f"    Methods: {methods}")

            for method_name in methods:
                if method_name in ['Valves', 'UserValves']:
                    continue
                method = getattr(module, method_name)
                print(f"    Testing {method_name}...")
                try:
                    if 'pipeline' in tool_id:
                        result = method('python', 'compile')
                    else:
                        result = method('python')
                    print(f"      Result length: {len(result) if result else 0}")
                except Exception as e:
                    print(f"      ERROR: {type(e).__name__}: {e}")

        except Exception as e:
            print(f"    ERROR loading tool: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*50)
    print("Test completed")

if __name__ == "__main__":
    asyncio.run(test_chat())
