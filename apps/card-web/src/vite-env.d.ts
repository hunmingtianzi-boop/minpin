/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_ENABLE_BLANK_ENTERPRISE_TEMPLATE?: string;
  readonly VITE_ENABLE_CARD_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
