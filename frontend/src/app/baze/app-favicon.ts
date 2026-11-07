import { BAZE_ICONS } from '../product/icons';

/** Same ratios as the shelf tile: corner radius 36% of the square, glyph 46% and centered. */
const RADIUS = 36;
const ICON = 46;
const ICON_ORIGIN = (100 - ICON) / 2;
const FALLBACK_COLOR = '#15803d';
const FALLBACK_ICON = 'lucidePackage';

/** The browser favicon for an app. The shelf tile displays this same document. */
export function renderAppFavicon(color: string, icon: string): string {
  const fill = /^#[0-9a-fA-F]{6}$/.test(color) ? color : FALLBACK_COLOR;
  const raw = BAZE_ICONS[icon as keyof typeof BAZE_ICONS] ?? BAZE_ICONS[FALLBACK_ICON];
  const body = raw.replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '');
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">` +
    `<rect width="100" height="100" rx="${RADIUS}" fill="${fill}"/>` +
    `<svg x="${ICON_ORIGIN}" y="${ICON_ORIGIN}" width="${ICON}" height="${ICON}" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">` +
    body +
    `</svg></svg>`
  );
}

export function appFaviconHref(color: string, icon: string): string {
  return `data:image/svg+xml,${encodeURIComponent(renderAppFavicon(color, icon))}`;
}
