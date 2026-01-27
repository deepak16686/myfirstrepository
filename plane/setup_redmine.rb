# Enable REST API
Setting.rest_api_enabled = 1
puts "REST API enabled: #{Setting.rest_api_enabled}"

# Create devops-requests project
project = Project.find_by(identifier: 'devops-requests')
if project.nil?
  project = Project.new
  project.name = 'DevOps Requests'
  project.identifier = 'devops-requests'
  project.description = 'Ticketing project for DevOps automation and CI/CD requests'
  project.is_public = false
  project.enabled_module_names = ['issue_tracking', 'time_tracking', 'wiki']
  if project.save
    puts "Project created: #{project.identifier}"
  else
    puts "Failed to create project: #{project.errors.full_messages.join(', ')}"
  end
else
  puts "Project already exists: #{project.identifier}"
end

# Generate API key for admin user
admin = User.find_by(login: 'admin')
if admin
  token = admin.api_token || Token.create(user: admin, action: 'api')
  puts "API Key for admin: #{token.value}"
else
  puts "Admin user not found"
end
