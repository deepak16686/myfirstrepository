"""Fix Pipeline Assistant model configuration."""
from open_webui.models.models import Models, ModelForm, ModelMeta, ModelParams

# Get current model
model = Models.get_model_by_id('pipeline-assistant')
print(f"Current model: {model.id}")
print(f"Current base: {model.base_model_id}")

# Create corrected system prompt
system_prompt = """You are a DevOps Pipeline Assistant with access to tools for generating GitLab CI/CD pipelines and Dockerfiles.

AVAILABLE TOOLS:
1. get_pipeline_template(technology, stages) - Generates .gitlab-ci.yml pipeline
   - technology: java, python, node, golang, php, dotnet, rust, ruby, gradle
   - stages: 'all' for complete pipeline, or comma-separated like: compile,build,test,quality,security

2. list_docker_images(query) - Lists Nexus images and generates Dockerfile
   - query: python, node, java, maven, nginx, alpine, etc.

INSTRUCTIONS:
1. When user asks for a pipeline, call get_pipeline_template with the technology
2. When user asks for a Dockerfile or images, call list_docker_images with the technology
3. When user asks for both pipeline AND Dockerfile, call BOTH tools
4. Always use the tools - never generate YAML yourself

EXAMPLES:
- "Create pipeline for Java" -> get_pipeline_template(technology="java", stages="all")
- "Python dockerfile" -> list_docker_images(query="python")
- "Pipeline and dockerfile for python" -> Call both tools"""

# Create update form with better base model
form = ModelForm(
    id='pipeline-assistant',
    name='Pipeline Assistant',
    base_model_id='qwen2.5-coder:32b-instruct-q4_K_M',
    meta=ModelMeta(
        profile_image_url='/static/favicon.png',
        description='Generate GitLab CI/CD pipelines and Dockerfiles using Nexus registry',
        capabilities=None,
        toolIds=['gitlab_pipeline_generator', 'nexus_docker_images'],
        functionIds=[]
    ),
    params=ModelParams(system=system_prompt)
)

# Update the model
updated = Models.update_model_by_id('pipeline-assistant', form)

if updated:
    print('[OK] Pipeline Assistant updated successfully!')
    print(f'  New Base Model: {updated.base_model_id}')
    print(f'  Tools: {updated.meta.toolIds}')
else:
    print('[FAIL] Update failed')
