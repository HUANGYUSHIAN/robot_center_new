/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_TMUI_EXTERNAL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
