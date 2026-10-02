export type Role = "admin" | "engineer" | "team_leader" | "viewer";
export interface User {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  active: boolean;
}
export interface Element {
  type: "text" | "qr";
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  font_size: number;
  content: string;
}
export interface Template {
  id: number;
  name: string;
  width_mm: number;
  height_mm: number;
  elements: Element[];
  render_mode: "bounded" | "legacy";
  active: boolean;
}
export interface Printer {
  id: number;
  name: string;
  host: string;
  port: number;
  protocol: string;
  dpi: number;
  active: boolean;
  location: string;
  side: string;
  group: string;
}
export interface Product {
  id: number;
  product_code: string;
  description: string;
  qr_content: string;
  text_content: string;
  text2: string;
  text3: string;
  text4: string;
  side: string;
  highlight_right: boolean;
  template_id: number | null;
  preferred_printer_id: number | null;
  active: boolean;
}
export interface Settings {
  default_quantity: number;
  max_quantity: number;
  reason_required: boolean;
  reasons: string[];
}
export interface Job {
  id: string;
  created_at: string;
  finished_at: string | null;
  user_snapshot: User;
  product_snapshot: Partial<Product>;
  template_snapshot: Partial<Template>;
  printer_snapshot: Partial<Printer>;
  quantity: number;
  reason: string;
  note: string;
  reference: string;
  status: "queued" | "sent" | "failed";
  error: string | null;
  zpl?: string;
  zpl_hash: string | null;
  original_job_id: string | null;
  delivery_message: string;
}
export interface PrintRequest {
  product_id: number;
  printer_id: number;
  quantity: number;
  reason: string;
  note: string;
  reference: string;
  idempotency_key: string;
}
export interface Preview {
  svg: string;
  zpl: string;
  preview_note: string;
}
export interface ImportReport {
  templates_create: string[];
  templates_existing: string[];
  products_create: string[];
  products_skip: string[];
  warnings: string[];
  errors: string[];
}
export interface ImportRun {
  id: string;
  source_hash: string;
  report: ImportReport;
  executed_at?: string;
}
