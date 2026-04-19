/**
 * Map the lucide-react string name found in `config/tools.yaml` to the
 * actual React icon component. Every icon referenced by the registry is
 * imported here; unknown names fall back to a generic Cube.
 */
import {
  Activity,
  Boxes,
  Brain,
  CheckSquare,
  ClipboardList,
  Container,
  Cpu,
  Database,
  DatabaseZap,
  FileText,
  GitBranch,
  GitFork,
  HardDrive,
  HardHat,
  Kanban,
  KeyRound,
  Layers,
  LineChart,
  Network,
  Package,
  PlayCircle,
  Router,
  ScanSearch,
  SearchCheck,
  Send,
  Server,
  ServerCog,
  Shapes,
  ShieldCheck,
  Zap,
  ZapOff,
  type LucideIcon,
} from 'lucide-react';

/* lucide does not ship a public `GPU` glyph; alias to Cpu for DCGM. */
const iconMap: Record<string, LucideIcon> = {
  activity: Activity,
  boxes: Boxes,
  brain: Brain,
  'check-square': CheckSquare,
  'clipboard-list': ClipboardList,
  container: Container,
  cpu: Cpu,
  database: Database,
  'database-zap': DatabaseZap,
  'file-text': FileText,
  'git-branch': GitBranch,
  'git-fork': GitFork,
  gpu: Cpu,
  'hard-drive': HardDrive,
  'hard-hat': HardHat,
  kanban: Kanban,
  'key-round': KeyRound,
  layers: Layers,
  'line-chart': LineChart,
  network: Network,
  package: Package,
  'play-circle': PlayCircle,
  router: Router,
  'scan-search': ScanSearch,
  'search-check': SearchCheck,
  send: Send,
  server: Server,
  'server-cog': ServerCog,
  'shield-check': ShieldCheck,
  // VectorSquare was removed in a later lucide release — use Shapes as the
  // nearest visual equivalent.
  'vector-square': Shapes,
  zap: Zap,
  'zap-off': ZapOff,
};

/**
 * Resolve a tool.icon string to a Lucide component.
 */
export function resolveIcon(name: string | undefined | null): LucideIcon {
  if (!name) return Boxes;
  return iconMap[name] ?? Boxes;
}

/**
 * Icon for a category id — used by the sidebar and detail drawer header.
 */
export const categoryIcons: Record<string, LucideIcon> = {
  ai: Brain,
  cicd: PlayCircle,
  scm: GitBranch,
  quality: ShieldCheck,
  security: KeyRound,
  registry: Package,
  observability: LineChart,
  metrics: Activity,
  logging: FileText,
  data: Database,
  pm: Kanban,
  gateway: Router,
  platform: ServerCog,
  projects: Layers,
};
