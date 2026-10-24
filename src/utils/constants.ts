// Common types for the application

export interface ResultType {
  status: string;
  message?: string;
  output?: string;
}

export interface GameType {
  appid: number;
  name: string;
}

// Common style definitions
export const STYLES = {
  resultBox: {
    padding: '12px',
    marginTop: '16px',
    backgroundColor: 'var(--decky-selected-ui-bg)',
    borderRadius: '8px',
    border: '1px solid var(--decky-border-color)',
    fontSize: '14px'
  },
  statusInstalled: { 
    color: '#22c55e',
    fontWeight: 'bold',
    fontSize: '14px'
  },
  statusNotInstalled: { 
    color: '#f97316',
    fontWeight: 'bold',
    fontSize: '14px'
  },
  statusSuccess: { color: "#22c55e" },
  statusError: { color: "#ef4444" },
  preWrap: { whiteSpace: "pre-wrap" as const },
  instructionCard: {
    padding: '14px',
    backgroundColor: 'var(--decky-selected-ui-bg)',
    borderRadius: '8px',
    border: '1px solid var(--decky-border-color)',
    marginTop: '8px',
    fontSize: '13px',
    lineHeight: '1.4'
  }
};

// Proxy DLL name options for OptiScaler injection
export const PROXY_DLL_OPTIONS = [
  { value: "dxgi.dll",       label: "dxgi.dll (default)",  hint: "Works for most DX12 games. Default." },
  { value: "winmm.dll",      label: "winmm.dll",      hint: "Use when dxgi.dll conflicts with an existing game file." },
  { value: "version.dll",    label: "version.dll",    hint: "Common fallback; works well with many launchers." },
  { value: "dbghelp.dll",    label: "dbghelp.dll",    hint: "Use for debug helper hook paths." },
  { value: "winhttp.dll",    label: "winhttp.dll",    hint: "Use when other DLL names conflict." },
  { value: "wininet.dll",    label: "wininet.dll",    hint: "Use when other DLL names conflict." },
  { value: "OptiScaler.asi", label: "OptiScaler.asi", hint: "For ASI loaders. Requires an ASI loader already installed in the game." },
] as const;

export type ProxyDllValue = typeof PROXY_DLL_OPTIONS[number]["value"];
export const DEFAULT_PROXY_DLL: ProxyDllValue = "dxgi.dll";

export const FSR4_VARIANT_OPTIONS = [
  {
    value: "fsr4-lite",
    label: "FSR 4.1.2 | INT8 Lite (handhelds)",
    hint: "Selects the smaller INT8 Lite model for handheld APUs, including Legion Go S. Requires a supported game and current Proton. Verify INT8 Lite in the in-game overlay.",
  },
  {
    value: "fsr4-auto",
    label: "FSR 4 | Automatic model",
    hint: "Lets upstream OptiScaler select the model supported by your GPU. Unsupported combinations may fall back to FSR 3.",
  },
] as const;

export type Fsr4VariantValue = typeof FSR4_VARIANT_OPTIONS[number]["value"];
export const DEFAULT_FSR4_VARIANT: Fsr4VariantValue = "fsr4-lite";

// Common timeout values
export const TIMEOUTS = {
  resultDisplay: 5000,  // 5 seconds
  pathCheck: 3000       // 3 seconds
};

// Message strings
export const MESSAGES = {
  modInstalled: "OptiScaler Mod Installed",
  modNotInstalled: "OptiScaler Mod Not Installed",
  installing: "Installing OptiScaler...",
  installButton: "Setup OptiScaler Mod",
  uninstalling: "Removing OptiScaler...",
  uninstallButton: "Remove OptiScaler Mod",
  installSuccess: "OptiScaler mod setup successfully!",
  uninstallSuccess: "OptiScaler mod removed successfully.",
  instructionTitle: "How to Use:",
  instructionText: "Use 'Copy launch options' for the standard direct launch-options method. If you want the wrapper commands instead, enable Manual Mode to reveal 'Copy Patch Command' and 'Copy Unpatch Command'.\n\nIn-game: Enable DLSS in graphics settings to use the selected upscaler in supported games.\n\nFor extended OptiScaler options, assign a back button to a keyboard's 'Insert' key."
};
