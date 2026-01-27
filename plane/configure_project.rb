# Configure the devops-requests project with trackers, statuses, etc.

project = Project.find_by(identifier: 'devops-requests')
if project.nil?
  puts "Project not found!"
  exit 1
end

# Enable all available trackers for the project
all_trackers = Tracker.all
project.trackers = all_trackers
puts "Enabled #{all_trackers.count} trackers: #{all_trackers.map(&:name).join(', ')}"

# Enable all issue statuses
IssueStatus.all.each do |status|
  puts "Status available: #{status.id} - #{status.name}"
end

# Enable all priorities
IssuePriority.all.each do |priority|
  puts "Priority available: #{priority.id} - #{priority.name}"
end

project.save!
puts "Project configured successfully!"

# Show current trackers
puts "Project trackers: #{project.trackers.map(&:name).join(', ')}"
