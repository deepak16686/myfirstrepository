# Fix tracker IDs and associate with project

# Reload trackers with IDs
Tracker.all.each do |t|
  puts "Tracker #{t.id}: #{t.name}, default_status_id: #{t.default_status_id}"
  if t.default_status_id.nil?
    t.default_status_id = 1
    t.save!
    puts "  -> Fixed default_status_id"
  end
end

# Associate trackers with project using direct SQL if needed
project = Project.find_by(identifier: 'devops-requests')
if project
  # Add trackers directly
  Tracker.all.each do |tracker|
    unless project.trackers.include?(tracker)
      project.trackers << tracker
      puts "Added tracker #{tracker.name} to project"
    end
  end
  project.save!
  project.reload
  puts "\nProject trackers after fix: #{project.trackers.map(&:name).join(', ')}"
  puts "Tracker count: #{project.trackers.count}"
end

# Verify issue can be created
puts "\nTest creating issue..."
issue = Issue.new(
  project: project,
  tracker: Tracker.first,
  subject: 'Test Issue',
  description: 'Test',
  author: User.find_by(login: 'admin'),
  priority: IssuePriority.default,
  status: IssueStatus.first
)
if issue.save
  puts "Test issue created successfully with ID: #{issue.id}"
  puts "Deleting test issue..."
  issue.destroy
else
  puts "Failed to create test issue: #{issue.errors.full_messages.join(', ')}"
end
