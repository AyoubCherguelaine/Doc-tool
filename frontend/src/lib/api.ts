import { getUploadSizeError } from "./upload-limits";

const BASE = (
  process.env.NEXT_PUBLIC_API_URL || "/api"
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const TOKEN_KEY = "docuchat_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(TOKEN_KEY, token);
  }
}

export function clearToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export async function api<T = unknown>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers = new Headers(opts.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const isMultipart =
    typeof FormData !== "undefined" && opts.body instanceof FormData;
  if (!isMultipart) headers.set("Content-Type", "application/json");

  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers,
    credentials: "include",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let msg = text;
    try {
      msg = JSON.parse(text).detail || JSON.parse(text).message || text;
    } catch {
      msg = text || res.statusText;
    }
    throw new ApiError(res.status, msg);
  }

  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as unknown as T;
  }
  return res.json() as Promise<T>;
}

export interface LoginPayload {
  email: string;
  password: string;
}
export interface RegisterPayload extends LoginPayload {
  name: string;
}

export interface AuthResponse {
  accessToken: string;
  user: import("./types").User;
}

export function login(p: LoginPayload) {
  return api<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(p),
  });
}

export function register(p: RegisterPayload) {
  return api<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(p),
  });
}

export function fetchMe() {
  return api<import("./types").User>("/auth/me", { method: "GET" });
}

export function fetchDocuments() {
  return api<import("./types").Document[]>("/documents", { method: "GET" });
}

export interface SemanticOcrBlock {
  id: string;
  type: string;
  content: unknown;
  ocr_text: string;
  bbox: [number, number, number, number];
  page_number: number;
  reading_order: number;
  continues_previous_block: boolean;
  previous_block_id?: string;
  [field: string]: unknown;
}

export interface AdvancedOcrResult {
  status: string;
  filename: string;
  total_pages: number;
  processed_pages: number;
  block_count: number;
  coordinate_system: string;
  ocr_text: string;
  pages: { page_number: number; block_count: number; blocks: SemanticOcrBlock[] }[];
  blocks: SemanticOcrBlock[];
  model?: string;
}

export interface AdvancedOcrParams {
  file?: File | Blob;
  document_id?: string;
  start_page?: number;
  end_page?: number;
  language?: "auto" | "ar" | "en" | "mixed";
  model?: string;
}

export async function extractAdvancedOcr(payload: AdvancedOcrParams | FormData) {
  if (typeof FormData !== "undefined" && payload instanceof FormData) {
    const file = payload.get("file");
    const error = file instanceof Blob ? getUploadSizeError(file) : null;
    if (error) throw new ApiError(413, error);
    return api<AdvancedOcrResult>("/v1/ocr/advanced", {
      method: "POST",
      body: payload,
    });
  }

  const params = payload as AdvancedOcrParams;
  if (params.file) {
    const error = getUploadSizeError(params.file);
    if (error) throw new ApiError(413, error);
    const formData = new FormData();
    formData.append("file", params.file);
    if (params.start_page !== undefined) {
      formData.append("start_page", String(params.start_page));
    }
    if (params.end_page !== undefined) {
      formData.append("end_page", String(params.end_page));
    }
    if (params.language) {
      formData.append("language", params.language);
    }
    if (params.model) {
      formData.append("model", params.model);
    }
    return api<AdvancedOcrResult>("/v1/ocr/advanced", {
      method: "POST",
      body: formData,
    });
  }

  return api<AdvancedOcrResult>("/v1/ocr/advanced", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function uploadDocument(file: File, options?: { maxPages?: number }) {
  const error = getUploadSizeError(file);
  if (error) throw new ApiError(413, error);
  const form = new FormData();
  form.append("file", file);
  if (options?.maxPages) {
    form.append("max_pages", options.maxPages.toString());
  }
  return api<{
    id: string;
    filename: string;
    pageCount: number;
    chunkCount: number;
  }>("/documents/upload", { method: "POST", body: form });
}

export function fetchDocumentSessions(docId: string) {
  return api<import("./types").ChatSession[]>(`/documents/${docId}/sessions`, {
    method: "GET",
  });
}

export function createSession(documentId: string, title?: string) {
  return api<{ id: string; title: string; documentId: string }>(`/sessions`, {
    method: "POST",
    body: JSON.stringify({ documentId, title }),
  });
}

export function fetchSession(id: string) {
  return api<{
    id: string;
    title: string;
    document: import("./types").Document;
    messages: import("./types").Message[];
  }>(`/sessions/${id}`, { method: "GET" });
}

export async function* streamChat(
  sessionId: string,
  message: string,
  mode: import("./types").ChatMode = "conversational",
  options: {
    model?: string;
    responseStyle?: string;
    signal?: AbortSignal;
  } = {},
): AsyncGenerator<string, void, unknown> {
  const token = getToken();
  const res = await fetch(`${BASE}/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token ?? ""}`,
    },
    body: JSON.stringify({
      message,
      mode,
      model: options.model,
      responseStyle: options.responseStyle,
    }),
    signal: options.signal,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text || res.statusText);
  }

  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      yield decoder.decode(value, { stream: true });
    }
    const tail = decoder.decode();
    if (tail) yield tail;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export function fetchCapabilities() {
  return api<{
    models: string[];
    defaultModel: string;
    formats: string[];
    maxUploadMB: number;
    maxPages: number;
  }>("/capabilities");
}

export function fetchAgentCapabilities() {
  return api<{
    modes: { value: string; name: string; description: string }[];
  }>("/capabilities/agents");
}

export interface DocumentOutline {
  documentId: string;
  filename: string;
  pageCount: number;
  headings: { text: string; page: number; level: number; fontSize?: number; bold?: boolean }[];
}

export function fetchDocumentOutline(documentId: string) {
  return api<DocumentOutline>(`/documents/${documentId}/outline`);
}

export function fetchPage(documentId: string, page: number) {
  return api<{
    page: number;
    totalPages: number;
    text: string;
    filename: string;
  }>(`/documents/${documentId}/pages/${page}`);
}

export function fetchSessions() {
  return api<import("./types").ChatSession[]>("/sessions");
}

export function analyzeWithGoogleAI(
  documentId: string,
  options: { task?: "comprehensive" | "entities" | "layout" | "tables"; model?: string } = {}
) {
  return api<{
    documentId: string;
    filename: string;
    task: string;
    result: string;
    success: boolean;
    iterations: number;
    steps: Array<{ thought?: string; action?: string; observation?: string }>;
  }>(`/documents/${documentId}/google-ai`, {
    method: "POST",
    body: JSON.stringify({
      task: options.task || "comprehensive",
      model: options.model,
    }),
  });
}

export interface DocumentAIServiceResponse {
  documentId: string;
  filename: string;
  service: string;
  model?: string;
  guardianEnabled?: boolean;
  guardian?: {
    enabled: boolean;
    mode: string;
    creditsCharged: number;
    description: string;
  };
  result: string;
  data?: any;
  creditsDeducted?: number;
  creditsRemaining?: number;
  success: boolean;
  iterations: number;
  steps: Array<{ thought?: string; action?: string; observation?: string }>;
}

export function analyzeReceipt(documentId: string, options: { model?: string } = {}) {
  return api<DocumentAIServiceResponse>(`/documents/${documentId}/receipt`, {
    method: "POST",
    body: JSON.stringify({ model: options.model }),
  });
}

export function analyzeResume(documentId: string, options: { model?: string } = {}) {
  return api<DocumentAIServiceResponse>(`/documents/${documentId}/resume`, {
    method: "POST",
    body: JSON.stringify({ model: options.model }),
  });
}

export function auditCompliance(documentId: string, options: { model?: string } = {}) {
  return api<DocumentAIServiceResponse>(`/documents/${documentId}/compliance`, {
    method: "POST",
    body: JSON.stringify({ model: options.model }),
  });
}

export function parseFormFields(documentId: string, options: { model?: string } = {}) {
  return api<DocumentAIServiceResponse>(`/documents/${documentId}/form-parser`, {
    method: "POST",
    body: JSON.stringify({ model: options.model }),
  });
}

export function redactSensitivePII(documentId: string, options: { model?: string } = {}) {
  return api<DocumentAIServiceResponse>(`/documents/${documentId}/redaction`, {
    method: "POST",
    body: JSON.stringify({ model: options.model }),
  });
}

export function classifyDocument(documentId: string, options: { model?: string } = {}) {
  return api<DocumentAIServiceResponse>(`/documents/${documentId}/classifier`, {
    method: "POST",
    body: JSON.stringify({ model: options.model }),
  });
}

export function analyzeFinancialStatement(documentId: string, options: { model?: string } = {}) {
  return api<DocumentAIServiceResponse>(`/documents/${documentId}/financial-statement`, {
    method: "POST",
    body: JSON.stringify({ model: options.model }),
  });
}

export function translateDocument(documentId: string, options: { model?: string } = {}) {
  return api<DocumentAIServiceResponse>(`/documents/${documentId}/translation`, {
    method: "POST",
    body: JSON.stringify({ model: options.model }),
  });
}

export function auditAnomalies(documentId: string, options: { model?: string } = {}) {
  return api<DocumentAIServiceResponse>(`/documents/${documentId}/anomaly-audit`, {
    method: "POST",
    body: JSON.stringify({ model: options.model }),
  });
}

export function runDocumentService(
  documentId: string,
  serviceKey: string,
  options: { model?: string; guardian?: boolean } = {},
) {
  const serviceEndpoints: Record<string, string> = {
    receipt: `/documents/${documentId}/receipt`,
    resume: `/documents/${documentId}/resume`,
    compliance: `/documents/${documentId}/compliance`,
    form_parser: `/documents/${documentId}/form-parser`,
    comparison: `/documents/${documentId}/comparison`,
    factcheck: `/documents/${documentId}/factcheck`,
    invoice: `/documents/${documentId}/invoice`,
    contract: `/documents/${documentId}/contract`,
    google_ai: `/documents/${documentId}/google-ai`,
    redaction: `/documents/${documentId}/redaction`,
    classifier: `/documents/${documentId}/classifier`,
    financial_statement: `/documents/${documentId}/financial-statement`,
    translation: `/documents/${documentId}/translation`,
    anomaly_audit: `/documents/${documentId}/anomaly-audit`,
  };
  const endpoint = serviceEndpoints[serviceKey] || `/documents/${documentId}/workflow`;
  return api<DocumentAIServiceResponse>(endpoint, {
    method: "POST",
    body: JSON.stringify({
      model: options.model,
      guardian: options.guardian !== undefined ? options.guardian : true,
    }),
  });
}

// ---------------------------------------------------------------------------
// Company Billing, API Keys, and Enterprise Quota
// ---------------------------------------------------------------------------

export interface CompanyAccountInfo {
  id: string;
  companyName: string;
  planTier: string;
  isFreeTrialOnly: boolean;
  totalCredits: number;
  usedCredits: number;
  remainingCredits: number;
  apiKeyPrefix: string;
  apiKey: string;
  rawApiKey?: string;
  createdAt: string;
}

export type CompanyAccount = CompanyAccountInfo;

export interface ServicePricingItem {
  id: string;
  name: string;
  credits: number;
  llmTier: string;
  category: string;
  description: string;
}

export interface PricingCatalogResponse {
  plan: string;
  initialCredits: number;
  freeTrialAvailableOnly: boolean;
  services: ServicePricingItem[];
}

export interface ApiUsageLogItem {
  id: string;
  serviceName: string;
  creditsCost: number;
  documentId: string | null;
  requestSummary: string | null;
  status: string;
  createdAt: string;
}

export interface CompanyUsageResponse {
  companyId: string;
  totalCredits: number;
  usedCredits: number;
  remainingCredits: number;
  logs: ApiUsageLogItem[];
}

export function fetchCompanyAccount() {
  return api<CompanyAccountInfo>("/company/account");
}

export interface WorkspaceInfo {
  id: string;
  name: string;
  userId: string;
  userName?: string;
  userEmail?: string;
  planTier: string;
  totalCredits: number;
  usedCredits: number;
  remainingCredits: number;
  apiKeyPrefix: string;
  apiKey: string;
  rawApiKey?: string;
  createdAt: string;
  status: "active" | "suspended";
}

export function fetchWorkspace() {
  return api<WorkspaceInfo>("/workspace");
}

export function updateWorkspace(name: string) {
  return api<{ status: string; id: string; name: string; message: string }>("/workspace", {
    method: "PUT",
    body: JSON.stringify({ name }),
  });
}

export function regenerateCompanyApiKey() {
  return api<{
    apiKey: string;
    apiKeyPrefix: string;
    remainingCredits: number;
    planTier: string;
  }>("/company/api-key/regenerate", {
    method: "POST",
  });
}

export function fetchCompanyPricing() {
  return api<PricingCatalogResponse>("/company/pricing");
}

export function fetchCompanyUsage() {
  return api<CompanyUsageResponse>("/company/usage");
}

export interface ModelPricing {
  input_per_million: number;
  output_per_million: number;
  cached_input_per_million?: number;
}

export interface ModelTokenCredits {
  input_per_million: number;
  output_per_million: number;
  cached_input_per_million?: number;
}

export interface AvailableModelItem {
  id: string;
  name: string;
  description: string;
  provider?: string;
  credit_cost: number;
  cost_usd?: number;
  cost_usd_formatted?: string;
  pricing?: ModelPricing;
  token_credits?: ModelTokenCredits;
  speed_tier?: string;
  reasoning_tier?: string;
  context_window?: number;
  status?: string;
  is_default: boolean;
  capabilities?: string[];
  conversion_formula?: string;
}

export interface AvailableModelsResponse {
  object: string;
  data: AvailableModelItem[];
  default_model: string;
  total_available: number;
  credit_price_usd?: number;
  conversion_formula?: string;
  allowed_models?: string[];
}

export interface ServiceCostCalculationResponse {
  model_id: string;
  model_name: string;
  base_service_credits: number;
  model_credit_cost: number;
  model_delta: number;
  guardian?: boolean;
  guardian_fee?: number;
  guardian_discount?: number;
  total_credits: number;
  total_cost_usd: number;
  total_cost_usd_formatted: string;
  credit_price_usd: number;
  conversion_formula: string;
}

export interface ModelSettingResponse {
  currentModel?: string;
  current_model?: string;
  modelDetails?: AvailableModelItem;
  model_details?: AvailableModelItem;
  defaultModel?: string;
  default_model?: string;
  allowedModels?: string[];
  allowed_models?: string[];
  creditPriceUsd?: number;
  conversionFormula?: string;
}

export interface GuardianSettingResponse {
  guardian: boolean;
  guardianFeeCredits: number;
  mode: "guardian_verification" | "direct_return";
  description: string;
}

export function fetchAvailableModels() {
  return api<AvailableModelsResponse>("/models");
}

export function fetchModelSetting() {
  return api<ModelSettingResponse>("/settings/model");
}

export function updateModelSetting(model: string) {
  return api<ModelSettingResponse>("/settings/model", {
    method: "POST",
    body: JSON.stringify({ model }),
  });
}

export function fetchGuardianSetting() {
  return api<GuardianSettingResponse>("/settings/guardian");
}

export function updateGuardianSetting(enabled: boolean) {
  return api<GuardianSettingResponse>("/settings/guardian", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

export function calculateServiceCost(service: string, model?: string, guardian?: boolean) {
  return api<ServiceCostCalculationResponse>("/services/calculate-cost", {
    method: "POST",
    body: JSON.stringify({
      service,
      model,
      guardian: guardian !== undefined ? guardian : true,
    }),
  });
}

export interface PlaygroundPreset {
  id: string;
  name: string;
  category: string;
  description: string;
  recommended_model: string;
  default_temperature: number;
  default_system_prompt?: string;
  default_query: string;
  default_schema: any;
  sample_text: string;
}

export interface PlaygroundPresetsResponse {
  presets: Record<string, PlaygroundPreset>;
  models: Array<{ id: string; name: string; description: string }>;
  defaultModel: string;
}

export interface PlaygroundRunPayload {
  service: string;
  document_id?: string;
  text_content?: string;
  system_prompt?: string;
  user_prompt?: string;
  schema_override?: any;
  model?: string;
  temperature?: number;
  output_format?: "json" | "markdown" | "auto";
  guardian?: boolean;
}

export interface PlaygroundRunResult {
  success: boolean;
  service: string;
  model: string;
  guardianEnabled?: boolean;
  guardian?: {
    enabled: boolean;
    mode: string;
    creditsCharged: number;
    description: string;
  };
  temperature?: number;
  documentId?: string;
  filename?: string;
  latencyMs: number;
  creditsDeducted: number;
  creditsRemaining: number;
  result: string;
  data?: any;
  raw?: string;
  iterations: number;
  steps: Array<{ thought?: string; action?: string; observation?: string }>;
  error?: string;
  schemaUsed?: any;
  promptUsed?: string;
}

export function fetchPlaygroundPresets() {
  return api<PlaygroundPresetsResponse>("/playground/presets");
}

export function runPlayground(payload: PlaygroundRunPayload) {
  return api<PlaygroundRunResult>("/playground/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface EphemeralDocumentStatusResponse {
  status: "active" | "expired";
  documentId: string;
  filename: string;
  fileSize: number;
  mimeType: string;
  pageCount: number;
  chunkCount: number;
  ttlMinutes: number;
  remainingSeconds: number;
  isExpired: boolean;
  createdAt: string;
  lastAccessedAt: string;
  expiresAt: string;
}

export function fetchDocumentStatus(docId: string) {
  return api<EphemeralDocumentStatusResponse>(`/v1/documents/${docId}/status`, {
    method: "GET",
  });
}

export function deleteDocumentSession(docId: string) {
  return api<{ status: string; documentId: string; message: string }>(`/v1/documents/${docId}`, {
    method: "DELETE",
  });
}
