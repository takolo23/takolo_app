export interface Contact {
  id: string;
  name: string;
  phoneE164: string;
  consentGranted: boolean;
  consentGrantedAt: string | null;
  consentSource: string | null;
  optedOutAt: string | null;
  lastInboundAt: string | null;
  customFields: Record<string, string>;
  tags: { tag: Tag }[];
  consentEvents?: {
    id: string;
    action: string;
    source: string;
    occurredAt: string;
  }[];
  messages?: Message[];
  inboundMessages?: Inbound[];
}
export interface Tag {
  id: string;
  name: string;
}
export interface Template {
  id: string;
  name: string;
  language: string;
  bodyText: string;
  variables: string[];
  status: string;
  category: string;
  supported: boolean;
  optOutIncluded: boolean;
}
export interface Segment {
  id: string;
  name: string;
  filters: {
    tagIds: string[];
    tagMode: "all" | "any";
    fields: {
      key: string;
      operator: "equals" | "contains" | "exists";
      value: string;
    }[];
  };
  total?: number;
  contacts?: Contact[];
}
export interface Campaign {
  id: string;
  name: string;
  status: keyof typeof import("@takolo/shared").campaignLabels;
  dryRun: boolean;
  scheduledAt: string | null;
  templateId: string;
  segmentId: string;
  template: Template;
  segment: Segment;
  variableMapping: Record<
    string,
    { source: "name" | "phone" | "field" | "literal"; value: string }
  >;
}
export interface Message {
  id: string;
  kind: string;
  status: keyof typeof import("@takolo/shared").messageLabels;
  phoneE164: string;
  dryRun: boolean;
  lastError: string | null;
  lastErrorCode: string | null;
  nextAttemptAt: string;
  createdAt: string;
  attempts: number;
  payload: unknown;
  providerMessageId: string | null;
  contact?: { id?: string; name: string };
  campaign?: { id: string; name: string } | null;
  dispatchAttempts?: {
    id: string;
    number: number;
    outcome: string;
    httpStatus: number | null;
    errorCode: string | null;
    errorMessage: string | null;
    startedAt: string;
    finishedAt: string | null;
  }[];
}
export interface Inbound {
  id: string;
  text: string | null;
  type: string;
  occurredAt: string;
  contact?: { id: string; name: string; phoneE164: string };
}
export interface Bot {
  enabled: boolean;
  greetingText: string;
  cooldownSecs: number;
}
export interface Settings {
  workspace: {
    id: string;
    name: string;
    sendingState: string;
    pauseReason: string | null;
    dryRun: boolean;
    messagesPerMinute: number;
    botConfig: Bot | null;
  };
  globalDryRun: boolean;
  maximumPerMinute: number;
  webhookUrl: string;
  meta: {
    tokenConfigured: boolean;
    appSecretConfigured: boolean;
    verifyTokenConfigured: boolean;
    phoneIdConfigured: boolean;
    businessIdConfigured: boolean;
    graphVersion: string;
  };
}
export interface Auth {
  user: {
    id: string;
    name: string;
    email: string;
    memberships: {
      workspaceId: string;
      role: string;
      workspace: { id: string; name: string };
    }[];
  };
  workspaceId: string;
  role: string;
  csrfToken: string;
}
export interface Audit {
  id: string;
  action: string;
  entityType: string;
  entityId: string | null;
  createdAt: string;
  details: Record<string, unknown>;
}
export interface Count {
  status: string;
  _count: { _all: number };
}
export interface Metrics {
  contacts: number;
  eligible: number;
  campaigns: Count[];
  states: Count[];
  errors: { errorCode: string | null; _count: { _all: number } }[];
  accepted: number;
  delivered: number;
  read: number;
  deliveryRate: number;
  readRate: number;
}
