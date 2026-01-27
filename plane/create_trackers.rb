# Create trackers now that statuses exist
default_status = IssueStatus.find_by(name: 'New')
puts "Default status: #{default_status.id} - #{default_status.name}"

trackers_data = [
  { name: 'Bug', position: 1 },
  { name: 'Feature', position: 2 },
  { name: 'Support', position: 3 },
  { name: 'Task', position: 4 }
]

trackers_data.each do |data|
  tracker = Tracker.find_by(name: data[:name])
  if tracker.nil?
    tracker = Tracker.new(
      name: data[:name],
      default_status_id: default_status.id,
      is_in_roadmap: true,
      position: data[:position]
    )
    if tracker.save
      puts "Created tracker: #{tracker.id} - #{tracker.name}"
    else
      puts "Failed to create #{data[:name]}: #{tracker.errors.full_messages.join(', ')}"
    end
  else
    puts "Tracker exists: #{tracker.id} - #{tracker.name}"
  end
end

# Add trackers to project
project = Project.find_by(identifier: 'devops-requests')
Tracker.all.each do |t|
  project.trackers << t unless project.trackers.include?(t)
end
project.save!
puts "\nProject trackers: #{project.trackers.reload.map(&:name).join(', ')}"
