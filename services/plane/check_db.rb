puts "Trackers in DB: #{Tracker.count}"
Tracker.all.each { |t| puts "  #{t.id}: #{t.name}" }

puts "\nStatuses in DB: #{IssueStatus.count}"
IssueStatus.all.each { |s| puts "  #{s.id}: #{s.name}" }

puts "\nPriorities in DB: #{IssuePriority.count}"
IssuePriority.all.each { |p| puts "  #{p.id}: #{p.name}" }

puts "\nProjects in DB: #{Project.count}"
Project.all.each { |p| puts "  #{p.id}: #{p.identifier} - trackers: #{p.tracker_ids.join(',')}" }
