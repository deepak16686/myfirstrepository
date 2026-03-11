## Agent Plan

Project: ai-folder
Task: Restore browser-safe GitLab portal access through the shared infrastructure stack.

Agents:
- infra-agent: Inspect shared proxy and GitLab compose configuration, identify scheme mismatches, and apply the canonical fix in `infra-stack`.
- validation-agent: Verify the live redirect chain and login entrypoint before and after the change, without touching volumes or deleting containers.

Constraints:
- Use shell-oriented operations only.
- Preserve all existing bind mounts and named volumes.
- Do not replace the shared stack or delete any container data.

Deliverable:
- GitLab portal works at `http://localhost:8443/gitlab/` and redirects stay on HTTP for the local stack.
