export enum Mode {
  DEV = "development",
  PROD = "production",
}

interface WithEnvMode {
  readonly env: {
    readonly MODE: Mode;
  };
}

export const mode = (import.meta as unknown as WithEnvMode).env.MODE;

declare const __API_PATH__: string;
export const API_PATH = __API_PATH__;

declare const __API_URL__: string;
export const API_URL = __API_URL__;

declare const __API_HOST__: string;
export const API_HOST = __API_HOST__;

declare const __API_PREFIX_PATH__: string;
export const API_PREFIX_PATH = __API_PREFIX_PATH__;

declare const __WS_API_URL__: string;
export const WS_API_URL = __WS_API_URL__;

declare const __APP_BASE_PATH__: string;
export const APP_BASE_PATH = __APP_BASE_PATH__;

