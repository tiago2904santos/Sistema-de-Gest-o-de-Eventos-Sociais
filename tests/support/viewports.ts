/** Viewports canônicos do laboratório. Acrescente aqui; os testes responsivos iteram esta lista. */
export const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  laptop: { width: 1280, height: 800 },
  tabletRetrato: { width: 1024, height: 1366 },
  tablet: { width: 768, height: 1024 },
  mobile: { width: 390, height: 844 },
  mobilePequeno: { width: 360, height: 800 },
} as const;

export type ViewportName = keyof typeof VIEWPORTS;
