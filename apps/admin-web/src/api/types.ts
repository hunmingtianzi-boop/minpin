export type AdminUser = {
  id: string;
  displayName: string;
  membershipId: string;
  tenantId: string;
  companyId: string;
  role?: string;
  permissions: string[];
};

export type CompanyProfile = {
  id?: string;
  name: string;
  summary: string;
  industry: string;
  region: string;
  website: string;
  logoUrl: string;
  version?: number;
  updatedAt?: string;
};

export type CompanyProfileInput = Omit<
  CompanyProfile,
  "id" | "updatedAt"
>;

export type CardSettings = {
  id?: string;
  displayName: string;
  title: string;
  slug: string;
  avatarUrl: string;
  assistantName: string;
  welcomeMessage: string;
  suggestedQuestions: string[];
  policyVersions: {
    privacy: string;
    chatNotice: string;
    leadConsent: string;
  };
  status?: string;
  version?: number;
  updatedAt?: string;
};

export type CardSettingsInput = Omit<
  CardSettings,
  "id" | "status" | "updatedAt"
>;

export type KnowledgeStatus =
  | "draft"
  | "review_pending"
  | "published"
  | "archived"
  | string;

export type KnowledgeDocument = {
  id: string;
  title: string;
  status: KnowledgeStatus;
  version?: number;
  latestVersion?: {
    id: string;
    versionNumber: number;
    reviewStatus: string;
    chunkCount: number;
    indexedChunkCount: number;
    indexStatus?: string;
    indexErrorCode?: string;
  };
  updatedAt?: string;
};

export type KnowledgeVisibility = "public" | "authenticated" | "internal";

export type KnowledgeDocumentDetail = KnowledgeDocument & {
  rawText: string;
  visibility: KnowledgeVisibility;
  metadata: Record<string, unknown>;
  editableVersionId?: string;
};

export type KnowledgeDocumentInput = {
  title: string;
  answer: string;
  visibility: KnowledgeVisibility;
  metadata: Record<string, unknown>;
};

export type LoginInput = {
  account: string;
  credential: string;
};

export type PlatformEnterprise = {
  tenantId: string;
  tenantSlug: string;
  tenantName: string;
  companyId: string;
  companyName: string;
  status: string;
  createdAt: string;
};

export type CreatePlatformEnterpriseInput = {
  tenantSlug: string;
  tenantName: string;
  companyName: string;
  industry: string;
  adminAccount: string;
  adminDisplayName: string;
  adminPassword: string;
  initialCardTitle: string;
};

export type CreatedPlatformEnterprise = PlatformEnterprise & {
  adminUserId: string;
  adminMembershipId: string;
  initialCardId: string;
  initialCardSlug: string;
};

export type ContentStatus =
  | "draft"
  | "review_pending"
  | "published"
  | "archived"
  | string;

export type ContentVisibility = "public" | "authenticated" | "internal";

export type VersionedResource = {
  id: string;
  status: ContentStatus;
  version: number;
  publishedAt?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type Product = VersionedResource & {
  slug: string;
  name: string;
  category: string;
  summary: string;
  detail: string;
  audience: string;
  priceBoundary: string;
  imageUrl: string;
  visibility: ContentVisibility;
  sortOrder: number;
  settings: Record<string, unknown>;
};

export type ProductInput = Omit<
  Product,
  "id" | "status" | "version" | "publishedAt" | "createdAt" | "updatedAt"
>;

export type CaseStudy = VersionedResource & {
  slug: string;
  title: string;
  industry: string;
  background: string;
  solution: string;
  result: string;
  clientDisplayName: string;
  imageUrl: string;
  visibility: ContentVisibility;
  sortOrder: number;
  settings: Record<string, unknown>;
};

export type CaseStudyInput = Omit<
  CaseStudy,
  "id" | "status" | "version" | "publishedAt" | "createdAt" | "updatedAt"
>;

export type ForbiddenAction = "refuse" | "handoff" | "safe_template";

export type ForbiddenTopic = {
  id: string;
  topic: string;
  matchTerms: string[];
  action: ForbiddenAction;
  safeResponse: string;
  isActive: boolean;
  version: number;
  createdAt?: string;
  updatedAt?: string;
};

export type ForbiddenTopicInput = Omit<
  ForbiddenTopic,
  "id" | "version" | "createdAt" | "updatedAt"
>;

export type ManagedCard = VersionedResource & {
  ownerUserId: string;
  slug: string;
  displayName: string;
  title: string;
  avatarUrl: string;
  assistantName: string;
  welcomeMessage: string;
  suggestedQuestions: string[];
  policyVersions: {
    privacy: string;
    chatNotice: string;
    leadConsent: string;
  };
  shareUrl: string;
  qrUrl: string;
};

export type ManagedCardInput = {
  ownerUserId?: string;
  displayName: string;
  title: string;
  avatarUrl: string;
  assistantName: string;
  welcomeMessage: string;
  suggestedQuestions: string[];
  policyVersions: ManagedCard["policyVersions"];
};

export type PageResult<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type DashboardDailyMetric = {
  day: string;
  visits: number;
  conversations: number;
  leads: number;
};

export type DashboardOverview = {
  generatedAt: string;
  periodDays: number;
  visits: number;
  uniqueVisitors: number;
  conversations: number;
  aiAnswers: number;
  newLeads: number;
  pendingGaps: number;
  unreadNotifications: number;
  conversationRate: number;
  leadRate: number;
  daily: DashboardDailyMetric[];
};

export type Visit = {
  id: string;
  cardId: string;
  cardDisplayName: string;
  visitorId: string;
  source?: string;
  startedAt: string;
  endedAt?: string;
  durationSeconds?: number;
  conversationCount: number;
};

export type ConversationStatus = "active" | "closed" | "expired" | "blocked";

export type Conversation = {
  id: string;
  cardId: string;
  cardDisplayName: string;
  visitorId: string;
  visitId?: string;
  status: string;
  primaryIntent?: string;
  riskLevel: string;
  startedAt: string;
  lastActivityAt: string;
  messageCount: number;
  hasCurrentSummary: boolean;
};

export type ConversationCitation = {
  id: string;
  chunkId: string;
  rank: number;
  score: number;
  title: string;
  sourceType: string;
  sourceId: string;
  snapshotText: string;
};

export type ConversationAiRun = {
  provider: string;
  model: string;
  status: string;
  firstTokenLatencyMs?: number;
  totalLatencyMs: number;
  retrievalResult: Record<string, unknown>;
  safetyResult: Record<string, unknown>;
  errorCode?: string;
};

export type ConversationMessage = {
  id: string;
  role: string;
  content: string;
  status: string;
  contentRedacted: boolean;
  createdAt: string;
  citations: ConversationCitation[];
  aiRun?: ConversationAiRun;
};

export type ConversationSummary = {
  id: string;
  conversationId: string;
  summary: string;
  interests: string[];
  strength?: string;
  nextStep?: string;
  riskNotes?: string;
  sourceMessageIds: string[];
  isCurrent: boolean;
  staleAt?: string;
  createdAt: string;
  updatedAt: string;
};

export type ConversationDetail = Conversation & {
  messages: ConversationMessage[];
  currentSummary?: ConversationSummary;
};

export type LeadStatus = "new" | "viewed" | "following" | "won" | "lost" | "invalid";
export type LeadPriority = "low" | "medium" | "high";

export type Lead = {
  id: string;
  cardId: string;
  cardDisplayName: string;
  visitorId: string;
  conversationId?: string;
  ownerUserId: string;
  status: string;
  priority: string;
  maskedName: string;
  maskedContact: string;
  companyName?: string;
  interestTags: string[];
  viewedAt?: string;
  closedAt?: string;
  version: number;
  createdAt: string;
  updatedAt: string;
};

export type LeadFollowup = {
  id: string;
  actorUserId: string;
  followupType: string;
  content: string;
  nextAt?: string;
  createdAt: string;
};

export type LeadDetail = Lead & {
  name: string;
  mobile?: string;
  email?: string;
  wechat?: string;
  demand: string;
  followups: LeadFollowup[];
};

export type LeadFollowupInput = {
  followupType: "note" | "call" | "message" | "meeting" | "status_change";
  content: string;
  nextAt?: string;
};

export type KnowledgeGapStatus =
  | "pending"
  | "drafted"
  | "approved"
  | "indexing"
  | "indexed"
  | "rejected"
  | "failed";

export type KnowledgeGap = {
  id: string;
  conversationId: string;
  question: string;
  reason: string;
  status: string;
  suggestedAnswer?: string;
  occurrenceCount: number;
  lastSeenAt: string;
  approvedVersionId?: string;
  evidence: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type AdminNotification = {
  id: string;
  notificationType: string;
  title: string;
  body: string;
  resourceType?: string;
  resourceId?: string;
  readAt?: string;
  createdAt: string;
};

export type NotificationList = {
  items: AdminNotification[];
  total: number;
  unread: number;
};

export type PrivacyRequestStatus =
  | "pending"
  | "verified"
  | "in_progress"
  | "completed"
  | "rejected";

export type PrivacyRequest = {
  id: string;
  visitorId: string;
  requestType: string;
  status: string;
  verificationMethod?: string;
  handledBy?: string;
  completedAt?: string;
  evidence: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};
