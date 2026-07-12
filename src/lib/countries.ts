// Inclusive marketplace country/region filter (client request — reflect the platform's GLOBAL
// scope instead of only UAE/KSA). The dropdown offers major markets + regions; "All Countries"
// is the global option. Region options (Europe, GCC) match any property in the group; individual
// property countries present in live data are always appended so real listings stay filterable.

const REGION_GROUPS: Record<string, string[]> = {
  "GCC Countries": [
    "United Arab Emirates",
    "UAE",
    "Saudi Arabia",
    "KSA",
    "Qatar",
    "Kuwait",
    "Bahrain",
    "Oman",
  ],
  Europe: [
    "United Kingdom",
    "UK",
    "France",
    "Germany",
    "Spain",
    "Italy",
    "Netherlands",
    "Portugal",
    "Switzerland",
    "Ireland",
    "Greece",
  ],
};

/** The standard inclusive filter options (order matters — rendered as-is). */
export const COUNTRY_FILTER_OPTIONS: string[] = [
  "United States",
  "United Kingdom",
  "Europe",
  "GCC Countries",
  "Egypt",
  "Morocco",
];

/** Options to render = the standard inclusive list + any real property countries not already
 *  covered by a listed option or region group (so live data is always filterable). */
export function marketplaceCountryOptions(dataCountries: string[]): string[] {
  const covered = new Set<string>();
  for (const opt of COUNTRY_FILTER_OPTIONS) {
    covered.add(opt);
    for (const c of REGION_GROUPS[opt] ?? []) covered.add(c);
  }
  const extra = dataCountries
    .filter((c) => c && !covered.has(c))
    .sort((a, b) => a.localeCompare(b));
  return [...COUNTRY_FILTER_OPTIONS, ...extra];
}

/** True if a property's country matches the selected filter (exact match, or region group). */
export function matchesCountryFilter(propertyCountry: string, filter: string): boolean {
  if (filter === "all") return true;
  const group = REGION_GROUPS[filter];
  if (group) return group.includes(propertyCountry);
  return propertyCountry === filter;
}
