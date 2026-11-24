import {
  Briefcase,
  Building2,
  Handshake,
  Code,
  FileText,
  GraduationCap,
  IdCard,
  ListChecks,
  Mail,
  Newspaper,
  PenLine,
  Scale,
  Send,
  Sparkles,
  Users,
  Wand2,
  type LucideIcon,
} from "lucide-react";

export const TEMPLATE_ICONS: Record<string, LucideIcon> = {
  sparkles: Sparkles,
  briefcase: Briefcase,
  users: Users,
  mail: Mail,
  send: Send,
  "id-card": IdCard,
  code: Code,
  "graduation-cap": GraduationCap,
  "pen-line": PenLine,
  scale: Scale,
  "list-checks": ListChecks,
  newspaper: Newspaper,
  wand: Wand2,
  "file-text": FileText,
  building: Building2,
  handshake: Handshake,
};

export function TemplateIcon({ name, className }: { name: string; className?: string }) {
  const Icon = TEMPLATE_ICONS[name] ?? FileText;
  return <Icon className={className} />;
}
