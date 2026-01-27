# Full Redmine setup - create trackers, statuses, priorities, and configure project

# Create Trackers if they don't exist
['Bug', 'Feature', 'Support', 'Task'].each_with_index do |name, i|
  tracker = Tracker.find_or_create_by(name: name) do |t|
    t.default_status_id = 1
    t.is_in_roadmap = true
  end
  puts "Tracker: #{tracker.id} - #{tracker.name}"
end

# Create Issue Statuses if they don't exist
statuses = [
  { name: 'New', is_closed: false },
  { name: 'In Progress', is_closed: false },
  { name: 'Resolved', is_closed: false },
  { name: 'Closed', is_closed: true },
  { name: 'Rejected', is_closed: true }
]

statuses.each do |s|
  status = IssueStatus.find_or_create_by(name: s[:name]) do |st|
    st.is_closed = s[:is_closed]
  end
  puts "Status: #{status.id} - #{status.name} (closed: #{status.is_closed})"
end

# Update default status for trackers
default_status = IssueStatus.find_by(name: 'New')
if default_status
  Tracker.all.each do |t|
    t.default_status = default_status
    t.save
  end
  puts "Set default status to 'New' for all trackers"
end

# Create Issue Priorities if they don't exist
priorities = ['Low', 'Normal', 'High', 'Urgent', 'Immediate']
priorities.each_with_index do |name, i|
  priority = IssuePriority.find_or_create_by(name: name) do |p|
    p.position = i + 1
    p.is_default = (name == 'Normal')
    p.active = true
  end
  puts "Priority: #{priority.id} - #{priority.name} (default: #{priority.is_default})"
end

# Configure project with trackers
project = Project.find_by(identifier: 'devops-requests')
if project
  project.trackers = Tracker.all
  project.save!
  puts "\nProject 'devops-requests' configured with #{project.trackers.count} trackers"
  puts "Trackers: #{project.trackers.map(&:name).join(', ')}"
else
  puts "Project not found!"
end

puts "\nSetup complete!"
